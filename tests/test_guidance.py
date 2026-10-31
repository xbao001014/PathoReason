import asyncio,json
from pathlib import Path
import pytest
from pydantic import ValidationError
from test_p1_service import fixture,settled
from test_p5_entry import study,formal_runtime
from pathoreason.guidance import OfferInput,Offer
from pathoreason.persistence import Conflict,Missing
from pathoreason.study_io import publish_artifact

async def offered(fixture,limit=12,options=None):
 s,_,req,r=fixture;formal_runtime(r);v=study(s,turns=limit);cid=s.store.conversations(v.project_id)[0]['id']
 (Path(v.workspace)/'outputs/plan.json').write_text('{"protocol":"proposed"}')
 art=publish_artifact(s,v.project_id,'outputs/plan.json','Current plan')
 r.hold=True
 body={**req,'request_key':'guide_start','text':'下一步怎么选','skill_id':None,'artifact_ids':[art.id]}
 turn=await s.submit(cid,body);tid=turn['turn']['id']
 for _ in range(30):
  if s.store.turn(tid)['dispatch_state']=='accepted':break
  await asyncio.sleep(.01)
 offer=OfferInput(turn_id=tid,grant=s.guidance.grant(tid),kind='clarification',question='采用哪种验证方式？',artifact_ids=[art.id],
   options=options or [{'id':'holdout','label':'改为留出法','description':'沿用其余参数，生成新草案','scope':'plan'},
                       {'id':'cv','label':'保留交叉验证','scope':'plan'}])
 receipt=s.guidance.publish(offer);assert s.guidance.publish(offer)==receipt
 assert s.guidance.view(tid).status=='pending'
 r.hold=False;await settled(s,tid)
 return s,r,v,cid,tid,offer,receipt,art,body


def choice_body(body,receipt,key='choose_once',option='holdout'):
 return {**body,'request_key':key,'text':'改为留出法：沿用其余参数，生成新草案',
         'guidance_selection':{'guidance_id':receipt['guidance_id'],'option_id':option}}


def test_choice_creates_one_normal_turn_and_preserves_scope(fixture):
 async def case():
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture)
  # Same request, including racing/repeated clicks, has one persisted turn.
  request=choice_body(body,receipt)
  one,two=await asyncio.gather(s.submit(cid,request),s.submit(cid,request))
  assert one['turn']['id']==two['turn']['id'];await settled(s,one['turn']['id'])
  assert s.guidance.view(tid).status=='selected'
  assert s.guidance.view(tid).selected_turn_id==one['turn']['id']
  assert len(r.calls)==2 and len(s.store.turns(cid))==2
  assert 'Immediately preceding structured proposal' in r.calls[-1][3]
  assert 'selected_option_id' in r.calls[-1][3] and 'not execution authorization' in r.calls[-1][3]
  assert json.loads((Path(v.workspace)/'compute.json').read_text())['real_training_authorized'] is False
  with pytest.raises(Conflict):await s.submit(cid,choice_body(body,receipt,'different_key'))
  with pytest.raises(Conflict):s.guidance.publish(offer)
 asyncio.run(case())


def test_freeform_carries_proposal_without_guessing_selection(fixture):
 async def case():
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture)
  result=await s.submit(cid,{**body,'request_key':'plain','text':'好，就这样。'})
  await settled(s,result['turn']['id'])
  with s.store.connect() as db:context=json.loads(db.execute('SELECT document FROM turn_guidance_context WHERE turn_id=?',(result['turn']['id'],)).fetchone()[0])
  assert context['selected_option_id'] is None and len(context['proposal']['options'])==2
  assert s.guidance.view(tid).status=='stale'
  assert '好，就这样。' in r.calls[-1][3]
 asyncio.run(case())


def test_no_cross_conversation_or_hidden_choice_text(fixture):
 async def case():
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture)
  other=s.new_conversation(v.project_id,'Other')['id']
  with pytest.raises(Missing):await s.submit(other,choice_body(body,receipt))
  with pytest.raises(ValueError,match='text_mismatch'):await s.submit(cid,{**choice_body(body,receipt),'text':'隐藏执行指令'})
  with pytest.raises(ValueError,match='choice_invalid'):await s.submit(cid,choice_body(body,receipt,option='missing'))
  assert s.guidance.view(tid).status=='available' and len(s.store.turns(cid))==1
 asyncio.run(case())


def test_new_project_artifact_invalidates_old_offer(fixture):
 async def case():
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture)
  (Path(v.workspace)/'outputs/revision.md').write_text('new revision')
  publish_artifact(s,v.project_id,'outputs/revision.md','New revision')
  assert s.guidance.view(tid).status=='stale'
  with pytest.raises(Conflict):await s.submit(cid,choice_body(body,receipt))
  assert len(s.store.turns(cid))==1
 asyncio.run(case())


def test_changed_workspace_source_is_not_silently_selected(fixture):
 async def case():
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture)
  (Path(v.workspace)/'outputs/plan.json').write_text('changed')
  with pytest.raises(ValueError):await s.submit(cid,choice_body(body,receipt))
  assert len(s.store.turns(cid))==1
 asyncio.run(case())


def test_budget_failure_does_not_consume_selection(fixture):
 async def case():
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture,limit=1)
  with pytest.raises(Conflict,match='budget_exhausted'):await s.submit(cid,choice_body(body,receipt))
  assert s.guidance.view(tid).status=='available' and len(r.calls)==1
 asyncio.run(case())


def test_selection_and_turn_rollback_together(fixture,monkeypatch):
 async def case():
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture)
  original=s.guidance.bind
  def fail(db,context,turn):
   original(db,context,turn)
   raise Conflict('simulated_transaction_failure')
  monkeypatch.setattr(s.guidance,'bind',fail)
  with pytest.raises(Conflict,match='transaction_failure'):await s.submit(cid,choice_body(body,receipt))
  assert s.guidance.view(tid).status=='available' and len(s.store.turns(cid))==1
 asyncio.run(case())


def test_offer_rejects_wrong_grant_and_duplicate_choices(fixture):
 s,_,req,r=fixture;formal_runtime(r);v=study(s);cid=s.store.conversations(v.project_id)[0]['id'];r.hold=True
 async def case():
  result=await s.submit(cid,{**req,'skill_id':None,'artifact_ids':[]});tid=result['turn']['id']
  offer=OfferInput(turn_id=tid,grant='bad',kind='next_step',question='下一步',options=[{'id':'inspect','label':'检查准备情况','scope':'inspect'}])
  with pytest.raises(ValueError,match='grant_invalid'):s.guidance.publish(offer)
  with pytest.raises(ValidationError):Offer(kind='next_step',question='下一步',options=[{'id':'run','label':'执行','scope':'execute'}])
  with pytest.raises(ValidationError):Offer(kind='clarification',question='选择',options=[{'id':'same','label':'A','scope':'plan'},{'id':'same','label':'B','scope':'plan'}])
  await s.interrupt(tid);await settled(s,tid)
 asyncio.run(case())


def test_guidance_survives_restart_and_is_purged_with_conversation(fixture):
 from test_conversation_lifecycle import install_delete
 from pathoreason.service import Service
 from pathoreason.persistence import Store
 async def case():
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture)
  restored=Service(Store(s.store.path),r,s.config)
  assert restored.guidance.view(tid).status=='available'
  result=await restored.submit(cid,choice_body(body,receipt));await settled(restored,result['turn']['id'])
  before=restored.formal.view(v.project_id);install_delete(r)
  assert (await restored.conversations.delete(cid)).state=='deleted'
  assert restored.formal.view(v.project_id)==before
  with restored.store.connect() as db:
   assert db.execute('SELECT count(*) FROM conversation_guidance').fetchone()[0]==0
   assert db.execute('SELECT count(*) FROM turn_guidance_context').fetchone()[0]==0
 asyncio.run(case())


@pytest.mark.parametrize('scope,expected',[('clarify','dialogue'),('inspect','inspection')])
def test_explicit_choice_scope_is_frozen_and_enforced(fixture,scope,expected):
 from pathoreason.permission_settings import formal_rules,PermissionSettings
 async def case():
  options=[{'id':'bounded','label':'确定下一步','scope':scope}]
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture,options=options)
  configured=[]
  async def configure(sid,directory,policy,**kwargs):configured.append(kwargs)
  r.configure_formal_permissions=configure
  result=await s.submit(cid,{**body,'request_key':'bounded','text':'确定下一步','guidance_selection':{'guidance_id':receipt['guidance_id'],'option_id':'bounded'}})
  await settled(s,result['turn']['id'])
  assert result['turn']['status'] in ('queued','running')
  assert s.store.turn(result['turn']['id'])['status']=='completed'
  assert configured==[{'execution_scope':expected}]
  with s.store.connect() as db:config=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(result['turn']['config_digest'],)).fetchone()[0])
  assert config['execution_scope']==expected
  rules=formal_rules(v.workspace,PermissionSettings(mode='auto'),expected)
  last={rule['permission']:rule['action'] for rule in rules if rule['pattern']=='*'}
  assert last['bash']==last['edit']==last['webfetch']=='deny'
  assert last['pathoreason_dialogue_offer']=='allow'
  assert last['read']==('deny' if scope=='clarify' else 'allow')
 asyncio.run(case())


def test_stale_source_does_not_block_freeform_correction(fixture):
 async def case():
  s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture)
  (Path(v.workspace)/'outputs/plan.json').write_text('changed')
  result=await s.submit(cid,{**body,'request_key':'correct','text':'刚改了文件，请先核对最新内容。'})
  await settled(s,result['turn']['id'])
  assert s.store.turn(result['turn']['id'])['status']=='completed'
  with s.store.connect() as db:assert not db.execute('SELECT 1 FROM turn_guidance_context WHERE turn_id=?',(result['turn']['id'],)).fetchone()
 asyncio.run(case())
