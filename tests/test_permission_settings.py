import asyncio,json
from pathlib import Path
import pytest
from pydantic import ValidationError
from test_p1_service import fixture,settled
from test_p5_entry import study,formal_runtime
from pathoreason.permission_settings import PermissionSettings,PermissionSettingsUpdate,formal_rules,ConversationPermissions
from pathoreason.persistence import Conflict
from pathoreason.runtime import OpenCode

def action(rules,tool,path='anything'):
    from fnmatch import fnmatchcase
    matches=[r['action'] for r in rules if fnmatchcase(tool,r['permission']) and fnmatchcase(path,r['pattern'])]
    return matches[-1]

def test_presets_and_custom_keep_private_file_rules():
    for mode in ['ask','auto','custom']:
        rules=formal_rules('/workspace',PermissionSettings(mode=mode,bash='deny',edit='ask',external_directory='deny'))
        assert action(rules,'bash')=={'ask':'ask','auto':'allow','custom':'deny'}[mode]
        assert action(rules,'read','/home/bxn/.config/pathoreason/credentials.env')=='deny'
        assert action(rules,'task')=='deny'
        assert action(rules,'external_directory','/workspace/file')==('deny' if mode=='custom' else 'allow')
        assert action(rules,'edit')==('allow' if mode=='auto' else 'ask')
    assert action(formal_rules('/workspace',PermissionSettings(mode='custom',edit='allow')),'edit')=='allow'
    with pytest.raises(ValidationError):PermissionSettings(mode='all',bash='allow')
    with pytest.raises(ValidationError):PermissionSettings(read='allow')

def test_settings_persist_scope_revision_and_no_model_call(fixture):
    s,ordinary,_,r=fixture;v=study(s);cid=s.store.conversations(v.project_id)[0]['id']
    other=s.new_conversation(v.project_id,'Other')['id']
    async def case():
        assert s.formal.permissions.view(cid).revision==0
        body=PermissionSettingsUpdate(expected_revision=0,settings=PermissionSettings(mode='auto'))
        saved=await s.formal.permissions.update(cid,body)
        assert saved.revision==1 and not r.calls
        assert ConversationPermissions(s.formal).view(cid)==saved
        assert s.formal.permissions.view(other).settings.mode=='ask'
        with pytest.raises(Conflict,match='revision_conflict'):await s.formal.permissions.update(cid,body)
        with pytest.raises(Conflict,match='formal_study_required'):s.formal.permissions.view(ordinary['id'])
        s.config['execution_environment']='local'
        with pytest.raises(Conflict,match='server_only'):await s.formal.permissions.update(cid,body)
    asyncio.run(case())

def test_policy_frozen_before_prompt_active_change_refused(fixture):
    s,_,request,r=fixture;formal_runtime(r);v=study(s);cid=s.store.conversations(v.project_id)[0]['id'];r.hold=True
    applied=[]
    async def configure(sid,directory,policy):applied.append(policy.model_dump())
    r.configure_formal_permissions=configure
    async def case():
        await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=0,settings=PermissionSettings(mode='auto',webfetch='deny')))
        turn=await s.submit(cid,{**request,'skill_id':None,'artifact_ids':[]})
        for _ in range(30):
            if r.calls:break
            await asyncio.sleep(.02)
        assert applied[0]['mode']=='auto' and applied[0]['webfetch']=='allow'
        with s.store.connect() as db:
            cfg=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(turn['turn']['config_digest'],)).fetchone()[0])
        assert cfg['permission_revision']==1 and cfg['permission_settings']==applied[0]
        with pytest.raises(Conflict,match='turn_active'):
            await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=1,settings=PermissionSettings()))
        await s.interrupt(turn['turn']['id']);await settled(s,turn['turn']['id'])
    asyncio.run(case())

def test_native_rule_update_is_verified_and_idempotent():
    runtime=OpenCode(Path('/tmp/nonexistent'),8522);current={'permission':[]};calls=[]
    async def call(method,path,directory=None,body=None):
        calls.append(method)
        if method=='PATCH':current['permission'].extend(body['permission'])
        return current
    runtime.call=call
    async def case():
        policy=PermissionSettings(mode='auto',bash='deny')
        await runtime.configure_formal_permissions('ses_test','/workspace',policy)
        await runtime.configure_formal_permissions('ses_test','/workspace',policy)
        assert calls==['GET','PATCH','GET','GET']
        assert action(current['permission'],'bash')=='allow'
        async def stale(*args,**kwargs):return {'permission':[]}
        runtime.call=stale
        with pytest.raises(ValueError,match='native_mismatch'):await runtime.configure_formal_permissions('ses_test','/workspace',policy)
    asyncio.run(case())

def test_always_uses_native_suggested_scope_and_no_duplicate_dispatch(fixture):
    s,_,request,r=fixture;v=study(s);cid=s.store.conversations(v.project_id)[0]['id'];formal_runtime(r);r.hold=True;calls=[]
    async def call(method,path,directory=None,body=None):
        if method=='GET':return [{'id':'per_own','sessionID':'ses_1','permission':'bash','patterns':['git status'],'always':['git status*']}]
        calls.append(body);return True
    r.call=call
    async def case():
        turn=await s.submit(cid,{**request,'skill_id':None,'artifact_ids':[]})
        for _ in range(30):
            if r.calls:break
            await asyncio.sleep(.02)
        assert (await s.formal.pending(cid))[0].always==['git status*']
        await s.formal.reply(cid,'per_own','always')
        with pytest.raises(Conflict,match='reconciliation'):await s.formal.reply(cid,'per_own','always')
        assert calls==[{'reply':'always'}]
        with s.store.connect() as db:
            receipt=json.loads(db.execute('SELECT document FROM formal_permissions').fetchone()[0])
        assert receipt['reply']=='always' and receipt['request']['always']==['git status*']
        await s.interrupt(turn['turn']['id']);await settled(s,turn['turn']['id'])
    asyncio.run(case())

def test_api_settings_validation_conflicts_and_origin(fixture):
    from fastapi.testclient import TestClient
    from pathoreason.api import app
    s,ordinary,_,r=fixture;app.state.service=s;v=study(s)
    cid=s.store.conversations(v.project_id)[0]['id']
    client=TestClient(app);url='/api/v2/conversations/'+cid+'/permission-settings'
    body={'expected_revision':0,'settings':{'mode':'custom','bash':'deny','edit':'allow'}}
    assert client.get(url).json()['settings']['mode']=='ask'
    assert client.put(url,json=body,headers={'Origin':'https://elsewhere.invalid'}).status_code==403
    assert client.put(url,json=body).json()['revision']==1
    assert client.put(url,json=body).status_code==409
    assert client.put(url,json={'expected_revision':1,'settings':{'mode':'auto','read':'allow'}}).status_code==422
    assert client.get('/api/v2/conversations/'+ordinary['id']+'/permission-settings').status_code==409
    assert not r.calls
