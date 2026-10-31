import asyncio,base64,json,hashlib
from pathlib import Path
import pytest
from test_p1_service import fixture,settled
from pathoreason.persistence import Conflict,Store
from pathoreason.context import LocalBinding
from pathoreason.contracts import canonical_digest
from pathoreason.codex_runtime import Codex
from pathoreason.runtime import visible_response

def test_compaction_is_idempotent_and_preserves_turns_and_artifacts(fixture):
 s,conv,request,runtime=fixture;calls=[]
 async def compact(*args):calls.append(args);return {'observed':True,'source':'test_native_summary'}
 runtime.compact=compact
 async def case():
  t=await s.submit(conv['id'],request);await settled(s,t['turn']['id']);before=s.store.turns(conv['id']);artifacts=s.store.artifacts(before[0]['project_id'])
  op=await s.context.compact(conv['id'],'once',request['model']);assert op['status']=='completed'
  assert (await s.context.compact(conv['id'],'once',request['model']))==op
  assert len(calls)==1 and s.store.turns(conv['id'])==before and s.store.artifacts(before[0]['project_id'])==artifacts
  assert len(runtime.calls)==1
 asyncio.run(case())

def test_unknown_compaction_blocks_dispatch_but_allows_handoff(fixture):
 s,conv,request,runtime=fixture;s.config['context_limits']={'max_operations':2,'timeout_seconds':.01}
 async def compact(*args):await asyncio.sleep(1)
 runtime.compact=compact
 async def case():
  t=await s.submit(conv['id'],request);await settled(s,t['turn']['id'])
  op=await s.context.compact(conv['id'],'timeout',request['model']);assert op['status']=='recovery_required'
  with pytest.raises(Conflict,match='context_operation_unresolved'):await s.submit(conv['id'],{**request,'request_key':'after'})
  assert s.context.export(conv['id'])['digest'];assert len(runtime.calls)==1
 asyncio.run(case())

def test_context_guard_unknown_and_smaller_windows(fixture):
 s,conv,request,runtime=fixture;model=s.models()[0]
 with pytest.raises(Conflict,match='limit_unknown'):s.context.guard(conv['id'],{**model,'context_limit_tokens':None},1)
 with pytest.raises(Conflict,match='tool_support_unknown'):s.context.guard(conv['id'],{**model,'tool_support':'unknown'},1)
 with pytest.raises(Conflict,match='requires_compaction'):s.context.guard(conv['id'],{**model,'context_limit_tokens':1000,'input_limit_tokens':900,'output_limit_tokens':100},901)
 assert runtime.calls==[]

def test_handoff_new_project_verified_bytes_no_actions_or_native_ids(fixture):
 s,conv,request,runtime=fixture
 async def case():
  t=await s.submit(conv['id'],request);await settled(s,t['turn']['id'])
  bundle=s.context.export(conv['id']);assert 'native_session' not in json.dumps(bundle)
  result=s.context.import_bundle(bundle);new=result['conversation']['id'];assert new!=conv['id']
  assert s.store.conversation(new)['native_session'] is None and s.store.turns(new)==[]
  assert result['handoff']['research_actions_replayed']==0
  assert s.context.import_bundle(bundle)['conversation']['id']==new
  old_artifacts=s.store.artifacts(s.store.conversation(conv['id'])['project_id']);new_artifacts=s.store.artifacts(result['project']['id'])
  assert {a['sha256'] for a in old_artifacts}=={a['sha256'] for a in new_artifacts}
  assert all(s.artifact_bytes(a) for a in new_artifacts) and len(runtime.calls)==1
  # Hash is not authority: incorrect artifact bytes are rejected even if envelope digest is recomputed.
  bundle['payload']['artifacts'][0]['content_base64']=base64.b64encode(b'tamper').decode();bundle['digest']=canonical_digest(bundle['payload'])
  count=len(s.store.projects())
  with pytest.raises(ValueError,match='integrity'):s.context.import_bundle(bundle)
  assert len(s.store.projects())==count
 asyncio.run(case())

def test_codex_local_only():
 with pytest.raises(ValueError,match='local_only'):Codex({'execution_environment':'bxn-server'},None)

def test_codex_ack_loss_reconcile_and_private_event_filter(tmp_path):
 store=Store(tmp_path/'state.sqlite3');r=Codex({'execution_environment':'local','data_root':str(tmp_path)},store);r.loaded.add('session')
 async def noop(*args):pass
 r.resume=noop
 turn={'id':'native_turn','status':'completed','completedAt':1,'items':[{'id':'u','clientId':'msg_stable','type':'userMessage','content':[]},{'id':'a','type':'agentMessage','text':'public'},{'id':'reason','type':'reasoning','text':'SECRET_REASONING'},{'id':'tool','type':'mcpToolCall','server':'pathoreason_context','tool':'read_project','status':'completed','arguments':{'secret':'SECRET_ARGUMENTS'},'result':{'secret':'SECRET_OUTPUT'}}]}
 async def rpc(method,params):assert method=='thread/read';return {'thread':{'turns':[turn]}}
 r.rpc=rpc
 with store.connect(True) as db:
  db.execute('INSERT INTO codex_calls VALUES(?,?,?,?)',('msg_stable','session',None,'{}'))
  db.execute('INSERT INTO codex_usage VALUES(?,?,?)',('session','native_turn',json.dumps({'last':{'totalTokens':30},'total':{'inputTokens':100,'outputTokens':10},'modelContextWindow':1000})))
 async def case():
  response=visible_response(await r.messages('session',str(tmp_path)),'msg_stable')
  assert response['text']=='public' and response['complete']
  assert 'SECRET' not in json.dumps(response)
  assert response['usage']['context_tokens']==30 and response['usage']['cumulative_input_tokens']==100
  with store.connect() as db:assert db.execute('SELECT turn_id FROM codex_calls').fetchone()[0]=='native_turn'
 asyncio.run(case())

def test_local_binding_does_not_rewrite_p0_contract():
 b=LocalBinding(id='bind_test',project_id='prj_test',conversation_id='conv_test',runtime='codex',runtime_version='0.165',native_session_id='local',state='bound',storage_namespace='prj_test',workspace_id='prj_test',auth_ref='local_codex_login',created_at='2026-10-30T00:00:00Z')
 assert b.schema_version=='pathoreason.runtime/2'
 with pytest.raises(ValueError):LocalBinding.model_validate({**b.model_dump(),'runtime':'opencode'})
 from pathoreason.contracts import RuntimeBinding
 assert 'local_codex_login' not in RuntimeBinding.model_json_schema()['properties']['auth_ref']['enum']

def test_compaction_lost_ack_reconciles_without_second_summary(fixture):
 s,conv,request,runtime=fixture;markers=[];calls=[]
 async def marker(*args):return list(markers)
 async def compact(*args):calls.append(args);markers.append('summary_native');raise TimeoutError('ack_lost')
 runtime.compaction_marker=marker;runtime.compact=compact
 async def case():
  t=await s.submit(conv['id'],request);await settled(s,t['turn']['id'])
  op=await s.context.compact(conv['id'],'lost_ack',request['model']);assert op['status']=='recovery_required'
  s.context.mark_recovery();v=await s.context.reconcile(conv['id']);assert v.operations[0]['status']=='completed'
  assert len(calls)==1 and len(runtime.calls)==1
 asyncio.run(case())

def test_summary_failure_preserves_evidence_and_allows_explicit_retry(fixture):
 s,conv,request,runtime=fixture
 async def compact(*args):raise ValueError('provider_summary_failed')
 runtime.compact=compact
 async def case():
  t=await s.submit(conv['id'],request);await settled(s,t['turn']['id']);before=s.store.turns(conv['id'])
  op=await s.context.compact(conv['id'],'failed',request['model']);assert op['status']=='failed'
  assert s.store.turns(conv['id'])==before and s.context.export(conv['id'])['digest']
 asyncio.run(case())

def test_unknown_compaction_in_other_conversation_cannot_overlap(fixture):
 s,conv,request,runtime=fixture
 async def compact(*args):raise TimeoutError('ack_lost')
 runtime.compact=compact
 async def case():
  t=await s.submit(conv['id'],request);await settled(s,t['turn']['id'])
  await s.context.compact(conv['id'],'pending_other',request['model'])
  native=s.store.conversation(conv['id'])['native_session']
  async def status(*args):return {native:{'type':'busy'}}
  runtime.status=status
  other=s.new_conversation(s.store.conversation(conv['id'])['project_id'],'Other')
  with pytest.raises(Conflict,match='runtime_busy'):await s.submit(other['id'],{**request,'request_key':'cannot_overlap'})
  assert not s.store.turns(other['id']) and len(runtime.calls)==1
 asyncio.run(case())
