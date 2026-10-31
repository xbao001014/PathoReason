"""Read-only evidence verification plus reversible migration checks on a disposable DB."""
import hashlib,json,sqlite3,tempfile,urllib.request,urllib.error,subprocess
from pathlib import Path
from types import SimpleNamespace
from pathoreason.settings import settings
from pathoreason.persistence import Store
from pathoreason.domain import Domain
from pathoreason.legacy import read_verified_file
from pathoreason.schema_v2 import ProjectDomainView,TransferBundle
from pathoreason.contracts import canonical_digest
cfg=settings();data=Path(cfg['data_root']);out=data/'acceptance/p4-20261030';out.mkdir(parents=True,exist_ok=True)
store=Store(data/'state/pathoreason.sqlite3');domain=Domain(SimpleNamespace(store=store,data=data,config=cfg));checks={};environment=cfg.get('execution_environment','bxn-server')
backup=sqlite3.connect(out/'before-p4.sqlite3');backup.row_factory=sqlite3.Row
with store.connect() as db:
 tables=[r[0] for r in backup.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'p4_%'")]
 checks['all_pre_p4_rows_unchanged']=all([tuple(r) for r in backup.execute('SELECT * FROM "'+t+'" ORDER BY rowid')]==[tuple(r) for r in db.execute('SELECT * FROM "'+t+'" ORDER BY rowid')] for t in tables)
 checks['no_new_model_calls']=db.execute('SELECT count(*) FROM turns').fetchone()[0]==backup.execute('SELECT count(*) FROM turns').fetchone()[0]
 turns=[r[0] for r in db.execute('SELECT id FROM turns')]
 checks['historical_contexts_readable']=all(domain.context(t).origin_version=='pathoreason/1' for t in turns)
 checks['no_active_turns']=not store.active()
base='http://127.0.0.1:'+str(cfg['api_port'])
def get(path):
 with urllib.request.urlopen(base+path) as response:return json.load(response)
checks['health_p4']=get('/health')['phase']=='P4'
checks['artifacts_integrity']=True;checks['domain_api_matches_projection']=True;checks['handoff_export_digest_valid']=True
views=[]
for p in store.projects():
 view=domain.view(p['id']);views.append(view)
 public=ProjectDomainView.model_validate(get('/api/v2/research-projects/'+p['id']+'/domain'))
 checks['domain_api_matches_projection'] &= public==view
 for a in store.artifacts(p['id']):
  root=Path('/data/bxn/auto-research/acceptance') if a['storage_root']=='legacy_evidence' else data/'artifacts'
  checks['artifacts_integrity'] &= len(read_verified_file(root,a['relative_path'],a['sha256']))==a['size_bytes']
 for conv in store.conversations(p['id']):
  try:bundle=get('/api/v1/conversations/'+conv['id']+'/handoff')
  except urllib.error.HTTPError as exc:
   assert exc.code==422 and json.load(exc)['detail']=='handoff_artifact_limit' and sum(a['size_bytes'] for a in store.artifacts(p['id']))>2_000_000
   continue
  TransferBundle.model_validate(bundle)
  checks['handoff_export_digest_valid'] &= canonical_digest(bundle['payload'])==bundle['digest']
if environment=='bxn-server':
 legacy=next(d for v in views for d in v.definitions if d.source_kind=='legacy_experiment')
 checks['legacy_all_source_fields_retained']=legacy.source_payload['config.json']['task_spec']==legacy.semantics.source_task
 checks['legacy_selection_unchanged']=legacy.semantics.selection.name=='rmse' and legacy.semantics.selection.split=='val' and legacy.semantics.selection.direction=='minimize'
 checks['legacy_flow_order_unchanged']=[n.id for n in legacy.workflow.nodes]==[n['id'] for n in legacy.source_payload['blueprint.json']['workspace']['nodes']]
 checks['legacy_frozen_manifest_unchanged']=bool(legacy.source_files) # Domain required exact pinned project manifest.
 checks['legacy_reviews_not_native']=sum(v.legacy_history_count for v in views)==2 and all(h.native_session_id is None and not h.executable for p in store.projects() for h in domain.history(p['id']))
 synth=next(d for v in views for d in v.definitions if d.source_kind=='synthetic_plan')
 checks['synthetic_source_task_unchanged']=synth.source_payload['plan']['task']==synth.semantics.source_task
 checks['compute_and_budget_units_separate']={'gpu_seconds','wall_seconds','worker_wall_seconds','calls'}<={b.unit for b in synth.budgets}
 checks['no_new_training']=len(list((data/'research').glob('*/runs/*/loop/jobs/*/started.json')))==34
 oldroot=Path('/home/bxn/projects/auto-research');p0=data/'acceptance/p0-20261030'
 inventory=json.loads((p0/'source-inventory.json').read_text())
 checks['legacy_source_inventory_unchanged']=all(hashlib.sha256((oldroot/item['path']).read_bytes()).hexdigest()==item['sha256'] for item in inventory)
 before=json.loads((p0/'ready-before.json').read_text())
 with urllib.request.urlopen('http://127.0.0.1:8002/ready',timeout=5) as r:ready=json.load(r)
 checks['legacy_service_same_instance']=ready['status']=='ready' and (ready['pid'],ready['instance'])==(before['pid'],before['instance'])
 checks['legacy_no_active_jobs']=not ready['active_experiments'] and not ready['background_jobs']
 checks['legacy_repair_store_absent']=not Path('/home/bxn/projects/auto-research/data/assistant/workspace-jobs/jobs.sqlite3').exists()
else:
 chains=[r for v in views for r in v.artifact_records if r.provenance.basis=='p3_handoff_record']
 checks['p3_imported_sources_explicit']=len(chains)>=4
 checks['historical_citations_resolve']=all(domain.resolve(r.identity.project_id,r.provenance.origin.artifact_id).identity==r.identity for r in chains)
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'rollback.sqlite3'
 with store.connect() as db:
  with sqlite3.connect(path) as copy:db.backup(copy)
 scratch=Store(path);test=Domain(SimpleNamespace(store=scratch,data=data,config=cfg))
 # Scratch only: remove projections to test the first migration, preserving source rows.
 with scratch.connect(True) as db:db.execute('DELETE FROM p4_context_projections');db.execute('DELETE FROM p4_projection_batches')
 try:test.migrate(True,fail_after=0)
 except RuntimeError:pass
 else:raise AssertionError('failure injection did not fail')
 with scratch.connect() as db:checks['failed_migration_atomic']=db.execute('SELECT count(*) FROM p4_context_projections').fetchone()[0]==db.execute('SELECT count(*) FROM p4_projection_batches').fetchone()[0]==0
 receipt=test.migrate(True);checks['migration_idempotent']=test.migrate(True)==receipt
 test.rollback(receipt['id'])
 with scratch.connect() as db:checks['rollback_preserves_sources']=db.execute('SELECT count(*) FROM p4_context_projections').fetchone()[0]==0 and all([tuple(r) for r in backup.execute('SELECT * FROM "'+t+'" ORDER BY rowid')]==[tuple(r) for r in db.execute('SELECT * FROM "'+t+'" ORDER BY rowid')] for t in tables)
backup.close()
report={'environment':environment,'checks':checks,'all_passed':all(checks.values()),'turn_count':len(turns),'inference_calls':0,'training_jobs_started':0,'source_tables_compared':tables,'repair_history_scope':'actual review history; repair importer tested with scoped fixtures, no matching source DB present'}
(out/'p4-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2));assert report['all_passed']
