import asyncio,hashlib,json,sqlite3,copy
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_p1_service import fixture,settled
from pathoreason.formal import StudyCreate,FormalConfiguration
from pathoreason.persistence import Conflict,Missing
from pathoreason.study_io import fetch_data,publish_artifact
from pathoreason.contracts import canonical_digest
from pathoreason.schema_adapters import snapshot


def study(s,key='study_one',turns=2):
 s.config['execution_environment']='bxn-server'
 return s.formal.create(StudyCreate(request_key=key,title='真实试验准备',objective='核对数据后按原流程开展研究',budget={'max_turns':turns,'max_wall_seconds':60}))

def formal_runtime(r):
 r.create_formal=r.create;r.prompt_formal=r.prompt
 async def configure(*args):pass
 r.configure_formal_permissions=configure


def test_study_is_new_budget_not_legacy_reset_and_native_round(fixture):
 s,conv,request,r=fixture;formal_runtime(r)
 async def case():
  prior=await s.submit(conv['id'],request);await settled(s,prior['turn']['id']);before=s.store.turn(prior['turn']['id'])
  s.config['p1_test_limits']={'max_turns':1,'max_wall_seconds':30}
  v=study(s,turns=1);cid=s.store.conversations(v.project_id)[0]['id']
  assert study(s,turns=1).project_id==v.project_id
  with pytest.raises(Conflict):study(s,turns=2)
  result=await s.submit(cid,{**request,'skill_id':'scientific-writing','artifact_ids':[]});await settled(s,result['turn']['id'])
  assert s.store.turn(result['turn']['id'])['status']=='completed'
  with s.store.connect() as db:
   cfg=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(result['turn']['config_digest'],)).fetchone()[0]);FormalConfiguration.model_validate(cfg)
   assert cfg['execution_mode']=='research' and cfg['agent']=='pathoreason-formal'
  with pytest.raises(Conflict,match='budget_exhausted'):await s.submit(cid,{**request,'request_key':'second','skill_id':None,'artifact_ids':[]})
  with pytest.raises(Conflict,match='budget_exhausted'):await s.submit(conv['id'],{**request,'request_key':'legacy_again'})
  assert s.store.turn(prior['turn']['id'])==before and len(r.calls)==2
 asyncio.run(case())


def test_formal_mode_cannot_escalate_existing_project_or_local(fixture):
 s,conv,request,r=fixture
 async def case():
  with pytest.raises(ValueError,match='formal_study_required'):await s.submit(conv['id'],{**request,'execution_mode':'research'})
 asyncio.run(case())
 with pytest.raises(Conflict,match='server_only'):s.formal.create(StudyCreate(request_key='local',title='Local',objective='test',budget={'max_turns':1,'max_wall_seconds':60}))
 assert not r.calls


def test_data_fetch_is_explicit_immutable_and_bounded(fixture):
 s,_,_,r=fixture;v=study(s);calls=[]
 class Response:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def read(self,n):return b'{"items":[]}'
 class Opener:
  def open(self,req,timeout):calls.append(req.full_url);return Response()
 receipt=fetch_data(v.project_id,'test disease',2,'inputs/source',s.config,Opener(),s.store)
 data=json.loads(receipt.read_text());assert data['status']=='downloaded' and data['scope']=='source_metadata_not_verified_training_dataset'
 assert 'Limit=2' in calls[0]
 with pytest.raises(FileExistsError):fetch_data(v.project_id,'test',2,'inputs/source',s.config,Opener(),s.store)
 with pytest.raises(ValueError):fetch_data(v.project_id,'test',2,'../escape',s.config,Opener(),s.store)
 assert len(calls)==1 and not r.calls


def test_formal_artifact_identity_context_and_handoff(fixture):
 s,_,_,r=fixture;v=study(s);root=Path(v.workspace)
 (root/'outputs/report.md').write_text('Result candidate, not independently approved.')
 artifact=publish_artifact(s,v.project_id,'outputs/report.md','报告')
 assert artifact.source_ref.adapter=='pathoreason.formal_study' and artifact.evidence_role=='not_assessed'
 record=s.domain.artifact(v.project_id,artifact.id);assert record.source.kind=='formal'
 with pytest.raises(ValueError):publish_artifact(s,v.project_id,'inputs/private.json','private')
 bundle=s.context.export(s.store.conversations(v.project_id)[0]['id']);assert bundle['payload']['version']=='pathoreason.handoff/3'
 imported=s.context.import_bundle(bundle);assert s.domain.resolve(imported['project']['id'],artifact.id).source.kind=='formal'
 raw={'schema_version':'pathoreason/1','id':'ctx_test','project_id':v.project_id,'project_revision':1,'goal':'test','constraints':[],'source_refs':[],'decision_refs':[],'active_run_refs':[],'artifact_ids':[artifact.id],'pending_items':[],'created_at':'2026-10-30T00:00:00Z'};raw['digest']=canonical_digest(raw)
 view=snapshot(raw,[artifact.model_dump(mode='json')]);assert view.schema_version=='pathoreason.context/3'
 assert not r.calls


def test_native_permissions_project_scope_once_and_durable_unknown(fixture):
 s,_,request,r=fixture;v=study(s);cid=s.store.conversations(v.project_id)[0]['id'];formal_runtime(r);r.hold=True;calls=[]
 async def call(method,path,directory=None,body=None):
  calls.append((method,path,body))
  if method=='GET':return [{'id':'per_own','sessionID':'ses_1','permission':'bash','patterns':['python train.py'],'metadata':{'command':'python train.py'}},{'id':'per_other','sessionID':'ses_other','permission':'bash','patterns':['secret']}]
  raise ConnectionError('ack lost')
 r.call=call
 async def case():
  result=await s.submit(cid,{**request,'skill_id':None,'artifact_ids':[]})
  for _ in range(30):
   if s.store.conversation(cid)['native_session']:break
   await asyncio.sleep(.02)
  assert [x.id for x in await s.formal.pending(cid)]==['per_own']
  with pytest.raises(Missing):await s.formal.reply(cid,'per_other','once')
  with pytest.raises(ConnectionError):await s.formal.reply(cid,'per_own','once')
  with pytest.raises(Conflict,match='reconciliation'):await s.formal.reply(cid,'per_own','once')
  assert sum(m=='POST' for m,_,_ in calls)==1
  await s.interrupt(result['turn']['id']);await settled(s,result['turn']['id'])
 asyncio.run(case())


def test_seedream_helper_uses_private_config_without_secret_in_request(fixture,monkeypatch):
 from pathoreason.study_io import generate_image
 s,_,_,r=fixture;v=study(s);root=Path(v.workspace)
 (root/'plans/method.md').write_text('Input -> encoder -> output; conceptual only')
 (root/'figures/request.json').write_text(json.dumps({'prompt':'Concept diagram','sources':['plans/method.md']}))
 cfgfile=s.data/'image.json';cfgfile.write_text(json.dumps({'provider':'seedream','model':'configured-model','api_key_env':'ARK_API_KEY','api_key':'TEST_ONLY_PRIVATE_VALUE','size':'2K'}));cfgfile.chmod(0o600);s.config['image_config_file']=str(cfgfile)
 monkeypatch.setattr('pathoreason.study_io.workspace',lambda pid,cfg:root)
 calls=[]
 def run(argv,**kwargs):
  calls.append((argv,kwargs));assert kwargs['env']['ARK_API_KEY']=='TEST_ONLY_PRIVATE_VALUE';assert 'TEST_ONLY_PRIVATE_VALUE' not in str(argv)
  bound=json.loads(Path(argv[argv.index('--request')+1]).read_text());assert 'TEST_ONLY_PRIVATE_VALUE' not in json.dumps(bound)
  assert bound['config']['model']=='configured-model' and bound['sources']==[str(root/'plans/method.md')]
  return SimpleNamespace(returncode=0)
 monkeypatch.setattr('pathoreason.study_io.subprocess.run',run)
 generate_image(v.project_id,'figures/request.json','figures/candidate-v1',s.config)
 assert len(calls)==1
 with pytest.raises(FileExistsError):generate_image(v.project_id,'figures/request.json','figures/candidate-v1',s.config)
 (root/'figures/request.json').write_text(json.dumps({'prompt':'x','sources':['../private']}))
 with pytest.raises(ValueError):generate_image(v.project_id,'figures/request.json','figures/candidate-v2',s.config)
 assert len(calls)==1 and not r.calls


def test_native_research_creation_does_not_grant_blanket_shell():
 from pathoreason.runtime import OpenCode
 runtime=OpenCode(Path('/tmp/nonexistent'),8522);calls=[]
 async def call(method,path,directory=None,body=None):calls.append(body);return {'id':'ses_test'}
 runtime.call=call
 asyncio.run(runtime.create_formal('/data/bxn/PathoReason/projects/prj_test','Test'))
 assert calls[0]['agent']=='pathoreason-formal'
 assert next(x for x in calls[0]['permission'] if x['permission']=='bash')['action']=='ask'
 assert not any(x['permission']=='*' and x['action']=='allow' for x in calls[0]['permission'])
 assert any(x['permission']=='read' and x['action']=='deny' for x in calls[0]['permission'])


def test_formal_attached_context_is_selected_bounded_and_verified(fixture):
 s,_,request,r=fixture;formal_runtime(r);v=study(s);root=Path(v.workspace)
 (root/'outputs/current.json').write_text('{"proposal":"CURRENT_UNIQUE_PROPOSAL"}')
 selected=publish_artifact(s,v.project_id,'outputs/current.json','Current')
 (root/'outputs/unrelated.md').write_text('UNRELATED_DECISION')
 publish_artifact(s,v.project_id,'outputs/unrelated.md','Other conversation')
 async def case():
  result=await s.submit(s.store.conversations(v.project_id)[0]['id'],{**request,'skill_id':None,'artifact_ids':[selected.id]})
  await settled(s,result['turn']['id']);row=s.store.turn(result['turn']['id'])
  prompt=s.prompt(row)
  assert 'CURRENT_UNIQUE_PROPOSAL' in prompt and 'UNRELATED_DECISION' not in prompt
  assert 'untrusted data' in prompt and selected.sha256 in prompt
  (s.data/'artifacts'/selected.relative_path).write_text('TAMPERED')
  with pytest.raises(ValueError):s.prompt(row)
 asyncio.run(case())


def test_formal_excerpt_budget_and_large_binary_omission(fixture):
 s,_,request,r=fixture;formal_runtime(r);v=study(s);root=Path(v.workspace);ids=[]
 for i in range(4):
  p=root/f'outputs/long{i}.md';p.write_text('x'*7000);ids.append(publish_artifact(s,v.project_id,str(p.relative_to(root)),f'Long {i}').id)
 p=root/'outputs/large.json';p.write_text('x'*65537);ids.append(publish_artifact(s,v.project_id,'outputs/large.json','Large').id)
 p=root/'outputs/binary.png';p.write_bytes(b'\x89PNG');ids.append(publish_artifact(s,v.project_id,'outputs/binary.png','Binary').id)
 async def case():
  result=await s.submit(s.store.conversations(v.project_id)[0]['id'],{**request,'skill_id':None,'artifact_ids':ids})
  await settled(s,result['turn']['id']);prompt=s.prompt(s.store.turn(result['turn']['id']))
  evidence=json.loads(prompt.split('resolve current references here before searching the workspace): ',1)[1].split('\nCite registered',1)[0])
  assert sum(len(a.get('content','')) for a in evidence)==18000
  assert all(a['truncated'] for a in evidence[:3])
  assert all('content_omitted' in a for a in evidence[3:])
 asyncio.run(case())
