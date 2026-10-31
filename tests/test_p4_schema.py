import asyncio,json,sqlite3,copy,hashlib
from pathlib import Path
import pytest
from test_p1_service import fixture,settled
from pathoreason import contracts as c
from pathoreason.schema_v2 import RuntimeConfiguration,ContextSnapshotV2,InvocationPolicy
from pathoreason import schema_adapters as a
from pathoreason.domain import repair_history


def test_new_context_runtime_and_additive_migration_rollback(fixture):
 s,conv,request,runtime=fixture
 async def case():
  result=await s.submit(conv['id'],request);tid=result['turn']['id'];await settled(s,tid)
  with s.store.connect() as db:
   ctx=ContextSnapshotV2.model_validate_json(db.execute('SELECT document FROM context_snapshots').fetchone()[0]);cfg=RuntimeConfiguration.model_validate_json(db.execute('SELECT document FROM runtime_configs').fetchone()[0])
   # Simulate an actual P3 row; preserve its original digest and entire text.
   old={k:v for k,v in ctx.model_dump(mode='json').items() if k not in ('digest','artifact_refs','origin_version','origin_digest')}
   old.update(schema_version='pathoreason/1',source_refs=[r['reference'] for r in old['source_refs']],active_run_refs=[],decision_refs=[]);old['digest']=c.canonical_digest(old)
   db.execute('UPDATE context_snapshots SET document=?',(json.dumps(old),))
  before=s.store.turn(tid)
  assert cfg.invocation_policy.automatic_retries==0
  projected=s.domain.context(tid);assert projected.origin_digest==old['digest'] and projected.artifact_refs[0].artifact_id=='art_test'
  with pytest.raises(RuntimeError,match='injected'):s.domain.migrate(True,fail_after=0)
  with s.store.connect() as db:assert db.execute('SELECT count(*) FROM p4_projection_batches').fetchone()[0]==0
  preview=s.domain.migrate();receipt=s.domain.migrate(True);assert preview['id']==receipt['id']
  assert s.domain.migrate(True)==receipt
  s.domain.rollback(receipt['id'])
  with s.store.connect() as db:
   assert db.execute('SELECT count(*) FROM p4_context_projections').fetchone()[0]==0
   assert json.loads(db.execute('SELECT document FROM context_snapshots').fetchone()[0])==old
  assert s.store.turn(tid)==before
 asyncio.run(case())


def test_multihop_handoff_resolves_immutable_citations_and_v1(fixture):
 s,conv,request,runtime=fixture
 first=s.context.export(conv['id']);result=s.context.import_bundle(first);second=s.context.export(result['conversation']['id']);last=s.context.import_bundle(second)
 record=s.domain.resolve(last['project']['id'],'art_test')
 assert record.provenance.origin.artifact_id=='art_test' and len(record.provenance.transfers)==2
 assert record.identity.project_id==last['project']['id']
 assert s.artifact_bytes(record.artifact.model_dump(mode='json'))==s.artifact_bytes(s.store.artifact('art_test',conv['project_id']))
 old=copy.deepcopy(first);old['payload']['version']='pathoreason.handoff/1'
 for artifact in old['payload']['artifacts']:artifact.pop('provenance')
 old['digest']=c.canonical_digest(old['payload'])
 imported=s.context.import_bundle(old);assert s.domain.resolve(imported['project']['id'],'art_test')
 assert runtime.calls==[]


def test_handoff_rejects_cross_project_duplicate_and_rolls_back(fixture,monkeypatch):
 s,conv,request,runtime=fixture;bundle=s.context.export(conv['id']);count=len(s.store.projects())
 duplicate=copy.deepcopy(bundle);duplicate['payload']['artifacts']*=2;duplicate['digest']=c.canonical_digest(duplicate['payload'])
 with pytest.raises(ValueError,match='scope'):s.context.import_bundle(duplicate)
 bad=copy.deepcopy(bundle);bad['payload']['artifacts'][0]['metadata']['project_id']='prj_other';bad['digest']=c.canonical_digest(bad['payload'])
 with pytest.raises(ValueError,match='scope'):s.context.import_bundle(bad)
 original=Path.write_bytes
 def fail(path,data):
  if path.name.startswith('art_'):raise OSError('disk full')
  return original(path,data)
 monkeypatch.setattr(Path,'write_bytes',fail)
 with pytest.raises(OSError,match='disk full'):s.context.import_bundle(bundle)
 assert len(s.store.projects())==count
 assert list((s.data/'artifacts').iterdir())==[s.data/'artifacts/result.json']


def test_legacy_repair_scoped_and_never_native(tmp_path):
 path=tmp_path/'jobs.db';ref=c.LegacyResourceRef(adapter='auto_research.experiment',resource_id='a'*32,revision='b'*64,revision_kind='manifest_sha256')
 with sqlite3.connect(path) as db:
  db.execute('CREATE TABLE jobs(id,owner,target,status,payload,answer,updated)')
  for owner,target in [('me','mine'),('other','mine'),('me','other')]:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',(owner+target,owner,json.dumps({'id':target}),'completed','{"question":"repair?"}','legacy answer',1))
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 rows=repair_history(path,project_id='prj_test',source_ref=ref,owner='me',target={'id':'mine'})
 assert len(rows)==1 and rows[0].origin=='legacy_import' and rows[0].native_session_id is None and not rows[0].executable
 assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
 assert repair_history(tmp_path/'missing',project_id='prj_test',source_ref=ref,owner='me',target={})==[]


def test_workflow_versions_preserve_definition_and_order():
 raw={'schema_version':1,'transitions':[{'from':'a','to':'z'}],'workspace':{'nodes':[{'id':'b','title':'B','kind':'gate','stages':['a'],'gateHint':'confirm'},{'id':'a','title':'A','kind':'results','stages':['z']}]},'custom':{'unknown':'preserved'}}
 view=a.workflow(raw,{'stage':'a'});assert [n.id for n in view.nodes]==['b','a'] and view.nodes[0].current
 assert view.definition['custom']==raw['custom'] and 'workspace' not in view.definition
 v2={'schema_version':2,'task':'segmentation','steps':[{'id':'fit','title':'Fit','kind':'operation'}],'workspace':[],'execution':{'custom':'preserve'}}
 projected=a.task_project_definition('test',v2,{'stage':'fit'},{});assert projected.source_payload['blueprint']==v2 and not projected.execution_authority
 with pytest.raises(ValueError,match='unsupported'):a.workflow({'schema_version':99},{})


def test_unresolved_legacy_never_guesses_validation_metric():
 task,issues=a.task_semantics({'task_kind':'regression','primary_metric':'test_rmse'})
 assert task.selection is None and issues[0].code=='legacy_selection_unresolved'
 with pytest.raises(ValueError,match='local_only'):InvocationPolicy(runtime='codex',environment='bxn-server',execution_mode='discuss',max_turns=12,max_wall_seconds=1200)


def test_task_authority_conflicts_are_visible_and_raw_fields_retained():
 task=json.loads((Path(__file__).parent/'fixtures/p4-task.json').read_text())
 config={'task_spec':task,'task_kind':'classification','primary_metric':'test_auc','label_column':'wrong','unknown_future_field':{'preserve':1}}
 semantics,issues=a.task_semantics(config)
 assert semantics.family=='regression' and semantics.selection.name=='rmse'
 assert {i.field for i in issues}=={'task_kind','primary_metric','label_column'}
 docs={'config.json':config,'state.json':{'stage':'done'},'blueprint.json':{'schema_version':1,'workspace':{'nodes':[]}}}
 projected=a.experiment_definition('old',docs,{})
 assert projected.compatibility=='conflict' and projected.source_payload==docs and not projected.execution_authority
 assert a.experiment_definition('old',docs,{}).digest==projected.digest


def test_frozen_business_context_is_used_instead_of_live_state(fixture):
 s,conv,request,runtime=fixture
 from pathoreason.business import BusinessView,BusinessAction
 raw={'schema_version':'pathoreason/1','id':'ctx_test','project_id':conv['project_id'],'project_revision':1,'goal':'frozen','constraints':[],'source_refs':[],'decision_refs':[],'active_run_refs':[],'artifact_ids':[],'pending_items':[],'created_at':'2026-10-30T00:00:00Z'}
 raw['digest']=c.canonical_digest(raw)
 business=BusinessView(project_id=conv['project_id'],status='planned',revision='f'*64,run_id='run_frozen')
 view=a.snapshot(raw,[],business.model_dump(mode='json'))
 assert view.active_run_refs[0].reference.resource_id=='run_frozen' and view.active_run_refs[0].reference.revision=='f'*64
 assert runtime.calls==[]


def test_versioned_api_handoff_wire_digest_and_project_scope(fixture,monkeypatch):
 from pathoreason.api import app
 from fastapi.testclient import TestClient
 s,conv,request,runtime=fixture;app.state.service=s
 client=TestClient(app)
 wire=client.get('/api/v1/conversations/'+conv['id']+'/handoff');assert wire.status_code==200
 bundle=wire.json();assert bundle['digest']==c.canonical_digest(bundle['payload'])
 response=client.post('/api/v1/handoffs/import',json=bundle);assert response.status_code==200
 pid=response.json()['project']['id']
 record=client.get('/api/v2/research-projects/'+pid+'/artifacts/art_test');assert record.status_code==200
 assert record.json()['identity']['project_id']==pid
 assert client.get('/api/v2/research-projects/prj_missing/artifacts/art_test').status_code==404
 assert client.get('/api/v2/research-projects/'+pid+'/domain').status_code==200
 assert runtime.calls==[]


def test_handoff_database_failure_rolls_back_whole_graph(fixture):
 s,conv,request,runtime=fixture;bundle=s.context.export(conv['id'])
 with s.store.connect() as db:
  before={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ['projects','conversations','artifacts','p4_provenance','handoffs']}
  db.execute("CREATE TRIGGER reject_provenance BEFORE INSERT ON p4_provenance BEGIN SELECT RAISE(ABORT,'injected_storage_failure'); END")
 with pytest.raises(sqlite3.IntegrityError,match='injected_storage_failure'):s.context.import_bundle(bundle)
 with s.store.connect() as db:
  assert before=={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in before}
 assert list((s.data/'artifacts').iterdir())==[s.data/'artifacts/result.json']
 assert len(list((s.data/'projects').iterdir()))==1
