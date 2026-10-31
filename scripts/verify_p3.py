"""Read-only P3 verification. Does not invoke a model, compact, replay or reset budgets."""
import hashlib,json,sqlite3,sys,urllib.request
from pathlib import Path
from pathoreason.settings import settings
from pathoreason.persistence import Store
from pathoreason.legacy import read_verified_file
cfg=settings();data=Path(cfg['data_root']);out=Path(sys.argv[1]) if len(sys.argv)>1 else data/'acceptance/p3-20261030';out.mkdir(parents=True,exist_ok=True)
store=Store(data/'state/pathoreason.sqlite3');checks={};environment=cfg.get('execution_environment','bxn-server')
with urllib.request.urlopen('http://127.0.0.1:'+str(cfg['api_port'])+'/health') as r:checks['application_healthy']=json.load(r)['phase']=='P3'
with store.connect() as db:
 turns=[dict(r) for r in db.execute('SELECT * FROM turns')];ops=[json.loads(r[0]) for r in db.execute('SELECT document FROM context_operations')];bindings=[json.loads(r[0]) for r in db.execute('SELECT document FROM bindings')]
 checks['no_active_turns']=not store.active()
 checks['turn_budget_retained']=len(turns)<=cfg['p1_test_limits']['max_turns']
 checks['every_turn_has_frozen_context']=db.execute('SELECT COUNT(*) FROM context_snapshots').fetchone()[0]==len(turns)
 checks['manual_compaction_native_evidence']=any(o['status']=='completed' and o.get('native_evidence',{}).get('observed') for o in ops)
 if environment=='local':
  models={json.loads(t['document'])['model']['model'] for t in turns if t['status']=='completed'}
  checks['two_local_models_completed']={'gpt-6.1-sol','gpt-6-luna'}<=models
  checks['native_call_identity_retained']=db.execute('SELECT count(*) FROM codex_calls WHERE turn_id IS NOT NULL').fetchone()[0]==len(turns)
  checks['local_auth_bindings_only']=all(b['runtime']=='codex' and b['auth_ref']=='local_codex_login' and b['schema_version']=='pathoreason.runtime/2' for b in bindings)
  checks['automatic_and_manual_compaction_observed']=db.execute('SELECT count(*) FROM codex_compactions').fetchone()[0]>len(ops)
  checks['partial_stop_preserved']=any(t['status']=='interrupted' and t['text'] for t in turns)
  checks['mcp_read_succeeded']=sum(any(tool['name']=='pathoreason_context_read_project' and tool['status']=='completed' for tool in json.loads(t['tools'])) for t in turns)>=2
  checks['no_local_research_execution']=not db.execute("SELECT 1 FROM business_turns WHERE mode<>'discuss'").fetchone()
  checks['cross_engine_handoff_visible']=bool(db.execute("SELECT 1 FROM handoffs WHERE json_extract(document,'$.source_runtime')='opencode'").fetchone())
  checks['normal_compaction_threshold_restored']='model_auto_compact_token_limit' not in (data/'runtime/codex/config.toml').read_text()
  checks['final_turn_freezes_native_configuration']=any('native_config_digest' in json.loads(r[0]) for r in db.execute('SELECT document FROM runtime_configs'))
 else:
  checks['server_opencode_only']=all(b['runtime']=='opencode' for b in bindings)
  checks['p3_server_after_compaction']=any(t['request_key']=='p3_server_after_compaction' and t['status']=='completed' and json.loads(t['usage']).get('compaction_observed') for t in turns)
  backup=data/'acceptance/p3-20261030/before-p3.sqlite3'
  old=sqlite3.connect(backup);old.row_factory=sqlite3.Row
  previous={r['id']:dict(r) for r in old.execute('SELECT * FROM turns')};checks['old_turn_rows_unchanged']=all(next(t for t in turns if t['id']==tid)==r for tid,r in previous.items());old.close()
  checks['synthetic_training_count_unchanged']=len(list((data/'research').glob('*/runs/*/loop/jobs/*/started.json')))==34
  checks['server_limit_not_reset']=len(turns)==12 and cfg['p1_test_limits']['max_turns']==12
checks['artifact_integrity']=True
for p in store.projects():
 for a in store.artifacts(p['id']):
  root=data/'artifacts' if a['storage_root']=='pathoreason_artifacts' else Path('/data/bxn/auto-research/acceptance')
  checks['artifact_integrity'] &= len(read_verified_file(root,a['relative_path'],a['sha256']))==a['size_bytes']
report={'environment':environment,'checks':checks,'all_passed':all(checks.values()),'turn_count':len(turns),'manual_compactions':len(ops),'inference_calls_in_this_script':0,'cost_source':'not_reported_by_runtime','token_accounting':'native last request separated from cumulative usage; interrupted usage may be unknown'}
(out/'p3-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2));assert report['all_passed']
