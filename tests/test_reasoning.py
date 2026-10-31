import asyncio,json
from pathlib import Path
import pytest
from pydantic import ValidationError
from test_p1_service import fixture,settled
from test_p5_entry import study,formal_runtime
from pathoreason.api import TurnInput
from pathoreason.persistence import Conflict
from pathoreason.reasoning import configured_options
from pathoreason.runtime import OpenCode

@pytest.mark.parametrize('effort',['none','low','high','max'])
def test_effort_is_frozen_dispatched_and_idempotent(fixture,effort):
 s,conv,request,r=fixture
 async def case():
  req={**request,'reasoning_effort':effort}
  result=await s.submit(conv['id'],req);await settled(s,result['turn']['id'])
  assert s.store.turn(result['turn']['id'])['status']=='completed'
  assert r.last_effort==effort
  assert (await s.submit(conv['id'],req))['reasoning_effort']==effort
  with s.store.connect() as db:
   frozen=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(result['turn']['config_digest'],)).fetchone()[0])
  assert frozen['reasoning_effort']==effort
  with pytest.raises(Conflict):await s.submit(conv['id'],{**req,'reasoning_effort':'high' if effort!='high' else 'low'})
  assert len(r.calls)==1
 asyncio.run(case())

def test_default_and_formal_snapshot(fixture):
 s,_,request,r=fixture;formal_runtime(r);v=study(s);cid=s.store.conversations(v.project_id)[0]['id']
 async def case():
  result=await s.submit(cid,{**request,'skill_id':None,'artifact_ids':[]});await settled(s,result['turn']['id'])
  assert result['reasoning_effort']=='high' and r.last_effort=='high'
 asyncio.run(case())

def test_unsupported_and_invalid_effort_rejected_before_dispatch(fixture,monkeypatch):
 s,conv,request,r=fixture
 with pytest.raises(ValidationError):TurnInput(**{**request,'reasoning_effort':'medium'})
 monkeypatch.setattr(s,'reasoning_options',lambda:[])
 with pytest.raises(ValueError,match='reasoning_effort_not_supported'):asyncio.run(s.submit(conv['id'],{**request,'reasoning_effort':'max'}))
 assert not r.calls and not s.store.turns(conv['id'])

def test_legacy_null_effort_and_pending_recovery(fixture,monkeypatch):
 s,conv,request,r=fixture
 async def case():
  # Capture a newly queued turn, then resume with current options changed.
  monkeypatch.setattr(s,'schedule',lambda tid:None)
  result=await s.submit(conv['id'],{**request,'reasoning_effort':'max'})
  monkeypatch.setattr(s,'reasoning_options',lambda:[])
  await s.run(result['turn']['id'])
  assert r.last_effort=='max'
  # Old configurations did not contain effort; do not invent history.
  row=s.store.turn(result['turn']['id']);doc=json.loads(row['document'])
  with s.store.connect() as db:
   old=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(doc['config_digest'],)).fetchone()[0]);old.pop('reasoning_effort')
   db.execute('UPDATE runtime_configs SET document=? WHERE digest=?',(json.dumps(old),doc['config_digest']))
  assert s.view(row)['reasoning_effort'] is None
 asyncio.run(case())

@pytest.mark.parametrize('formal',[False,True])
def test_native_variant_and_stale_configuration_guard(tmp_path,formal):
 r=OpenCode(tmp_path,1);calls=[]
 async def call(method,path,directory=None,body=None):
  calls.append((method,path,body))
  if path=='/provider':return {'all':[{'id':'deepseek-direct','models':{'deepseek-v4-pro':{'variants':{'max':{'reasoningEffort':'max'}}}}}]}
  return {'permission':[{'permission':'pathoreason_research','action':'allow'}]}
 r.call=call
 async def case():
  dispatch=r.prompt_formal if formal else r.prompt
  await dispatch('ses_test','/synthetic','msg_test','deepseek-v4-pro','synthetic','max')
  payload=[body for method,path,body in calls if path.endswith('/prompt_async')][-1]
  assert payload['variant']=='max' and payload['agent']==('pathoreason-formal' if formal else 'pathoreason')
  before=len(calls)
  with pytest.raises(ValueError,match='reload_required'):await dispatch('ses_test','/synthetic','msg_next','deepseek-v4-pro','synthetic','low')
  assert not any(path.endswith('/prompt_async') for _,path,_ in calls[before:])
 asyncio.run(case())

def test_capabilities_require_configured_variants():
 config=json.loads((Path(__file__).parents[1]/'config/opencode.json').read_text())
 assert {o['model'] for o in configured_options(config)}=={'deepseek-v4-pro','deepseek-flash'}
 config['provider']['deepseek-direct']['models']['deepseek-v4-pro']['variants']['max']={}
 assert 'deepseek-v4-pro' not in [o['model'] for o in configured_options(config)]
