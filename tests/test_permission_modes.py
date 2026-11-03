import asyncio,json
from itertools import product
import pytest
from pydantic import ValidationError
from test_p1_service import fixture
from test_p5_entry import study,formal_runtime
from test_permission_settings import action
from pathoreason.permission_settings import PermissionSettings,PermissionSettingsUpdate,TOOLS,formal_rules
from pathoreason.persistence import encoded,now


def test_legacy_projection_preserves_every_effective_action():
    for mode in ('ask','auto','custom'):
        for values in product(('ask','allow','deny'),repeat=4):
            old={'mode':mode,**dict(zip(TOOLS,values))};original=encoded(old)
            actual=PermissionSettings.from_stored(old)
            expected={t:('deny' if old[t]=='deny' else {'ask':'ask','auto':'allow'}.get(mode,old[t])) for t in TOOLS}
            assert {t:actual.action(t) for t in TOOLS}==expected
            assert actual.mode==('custom' if mode!='custom' and 'deny' in values else mode)
            assert encoded(old)==original
            assert PermissionSettings.from_stored(actual.model_dump())==actual
            rules=formal_rules('/workspace',actual)
            for t in TOOLS:assert action(rules,t,'/untrusted/file')==expected[t]
    with pytest.raises(ValidationError):PermissionSettings.from_stored({'semantics_version':3})


def test_new_presets_ignore_stale_individual_fields():
    for mode,value in [('auto','allow'),('ask','ask')]:
        p=PermissionSettings(mode=mode,**dict.fromkeys(TOOLS,'deny'))
        assert p.model_dump()=={'semantics_version':2,'mode':mode,**dict.fromkeys(TOOLS,value)}
    p=PermissionSettings(mode='custom',bash='deny',edit='allow')
    assert [p.action(t) for t in TOOLS]==['deny','allow','ask','ask']
    for scope in ['inspection','dialogue']:
        rules=formal_rules('/workspace',PermissionSettings(mode='auto'),scope)
        assert action(rules,'bash')=='deny' and action(rules,'edit')=='deny'


def test_legacy_view_then_explicit_auto_save_appends_without_rewriting(fixture):
    s,_,_,r=fixture;v=study(s);cid=s.store.conversations(v.project_id)[0]['id']
    old=encoded({'mode':'auto',**dict.fromkeys(TOOLS,'deny')})
    with s.store.connect(True) as db:
        db.execute('INSERT INTO conversation_permission_settings VALUES(?,?,?,?)',(cid,1,old,now()))
    async def case():
        before=s.formal.permissions.view(cid)
        assert before.settings.mode=='custom' and set(before.effective_actions.values())=={'deny'}
        saved=await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=1,settings={'mode':'auto',**dict.fromkeys(TOOLS,'deny')}))
        assert saved.revision==2 and set(saved.effective_actions.values())=={'allow'}
        with s.store.connect() as db:
            rows=db.execute('SELECT document FROM conversation_permission_settings WHERE conversation_id=? ORDER BY revision',(cid,)).fetchall()
        assert rows[0][0]==old and json.loads(rows[1][0])['semantics_version']==2
        assert not r.calls
        await s.close()
    asyncio.run(case())


def test_legacy_pending_turn_uses_frozen_denials_even_after_new_auto_save(fixture,monkeypatch):
    s,_,request,r=fixture;formal_runtime(r);v=study(s);cid=s.store.conversations(v.project_id)[0]['id']
    monkeypatch.setattr(s,'schedule',lambda tid:None)
    applied=[]
    async def configure(sid,directory,policy):applied.append(policy)
    r.configure_formal_permissions=configure
    async def case():
        await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=0,settings={'mode':'auto'}))
        turn=await s.submit(cid,{**request,'skill_id':None,'artifact_ids':[]});digest=turn['turn']['config_digest']
        # Represent an already queued pre-upgrade configuration in this isolated fixture.
        with s.store.connect(True) as db:
            cfg=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(digest,)).fetchone()[0])
            cfg['permission_settings']={'mode':'auto',**dict.fromkeys(TOOLS,'deny')}
            frozen=encoded(cfg);db.execute('UPDATE runtime_configs SET document=? WHERE digest=?',(frozen,digest))
        await s.run(turn['turn']['id'])
        assert applied[0].mode=='custom' and all(applied[0].action(t)=='deny' for t in TOOLS)
        assert '"bash":"deny"' in r.calls[0][3].split('Effective tool actions for this turn')[1]
        with s.store.connect() as db:assert db.execute('SELECT document FROM runtime_configs WHERE digest=?',(digest,)).fetchone()[0]==frozen
        assert s.formal.permissions.view(cid).settings.mode=='auto'
        await s.close()
    asyncio.run(case())
