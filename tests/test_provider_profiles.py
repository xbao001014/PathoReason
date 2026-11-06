import asyncio,copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from pathoreason import settings as settings_module
from pathoreason.provider_config import initialize,effective_settings,native_config,state,key_for,private_directory,validate_endpoint
from pathoreason.provider_settings import ProviderSettings,ProviderSettingsUpdate
from pathoreason.persistence import Conflict
from pathoreason.reasoning import configured_options as reasoning
from pathoreason.output_settings import configured_options as outputs
from test_p1_service import fixture


@pytest.fixture
def managed(fixture,monkeypatch):
    s,conv,*_=fixture;initialize(s.config,'official-fixture-key')
    s.config=effective_settings({**s.config,'provider_profiles_enabled':True})
    async def call(method,path,directory=None,body=None):
        if path=='/session/status':return {}
        if path=='/permission':return []
        raise AssertionError(path)
    s.runtime.call=call
    manager=ProviderSettings(s);restarts=[]
    async def restart():restarts.append(state(s.config)['active'])
    monkeypatch.setattr(manager,'restart',restart)
    return s,conv,manager,restarts


def update(manager,**overrides):
    body=dict(expected_revision=manager.view().revision,provider_id='dashscope-deepseek',
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',model='deepseek-v4-pro',api_key='dash-fixture-key')
    return asyncio.run(manager.update(ProviderSettingsUpdate(**{**body,**overrides})))


def test_independent_keys_blank_preservation_and_provider_metadata(managed):
    s,_,manager,restarts=managed;before=manager.view().model_dump_json()
    assert 'fixture-key' not in before and not manager.view().profiles[1].credential_present
    result=update(manager)
    assert result.active=='dashscope-deepseek' and s.config['provider']['id']==result.active
    assert key_for(s.config,'deepseek-direct')=='official-fixture-key'
    assert key_for(s.config,'dashscope-deepseek')=='dash-fixture-key'
    assert all((private_directory(s.config)/name).stat().st_mode & 0o077==0 for name in ['profiles.json','deepseek-direct.env','dashscope-deepseek.env'])
    update(manager,provider_id='deepseek-direct',base_url='https://api.deepseek.com/v1',api_key=None)
    update(manager,api_key=None)
    assert key_for(s.config,'deepseek-direct')=='official-fixture-key'
    assert key_for(s.config,'dashscope-deepseek')=='dash-fixture-key'
    assert restarts==['dashscope-deepseek','deepseek-direct','dashscope-deepseek']
    assert 'fixture-key' not in (private_directory(s.config)/'audit.jsonl').read_text()


def test_missing_key_stale_revision_and_invalid_endpoint_do_not_mutate(managed):
    s,_,manager,restarts=managed;before=(private_directory(s.config)/'profiles.json').read_bytes()
    with pytest.raises(ValueError,match='provider_key_missing'):update(manager,api_key=None)
    with pytest.raises(Conflict,match='provider_settings_stale'):update(manager,expected_revision=99)
    for endpoint in ['http://127.0.0.1/v1','https://attacker.invalid/v1','https://dashscope.aliyuncs.com.evil.invalid/compatible-mode/v1',
                     'https://secret@dashscope.aliyuncs.com/compatible-mode/v1','https://dashscope.aliyuncs.com:secret/compatible-mode/v1']:
        with pytest.raises(ValueError,match='^provider_endpoint_invalid$'):update(manager,base_url=endpoint)
    assert before==(private_directory(s.config)/'profiles.json').read_bytes() and not restarts


def test_pending_native_permission_refuses_switch(managed,monkeypatch):
    s,_,manager,restarts=managed
    async def pending(method,path,directory=None,body=None):return {} if path=='/session/status' else [{'id':'pending'}]
    (s.data/'projects/runtime').mkdir()
    monkeypatch.setattr(s.runtime,'call',pending)
    with pytest.raises(Conflict,match='provider_switch_busy'):update(manager)
    assert state(s.config)['active']=='deepseek-direct' and not restarts


@pytest.mark.parametrize('kind',['goal','context','training'])
def test_other_active_operations_refuse_switch(managed,kind):
    s,conv,manager,restarts=managed
    with s.store.connect(True) as db:
        if kind=='goal':db.execute('INSERT INTO research_goals VALUES(?,?,?,?)',('goal_probe',conv['id'],conv['project_id'],json.dumps({'state':'active'})))
        elif kind=='context':db.execute('INSERT INTO context_operations VALUES(?,?,?,?,?,?)',('op_probe',conv['id'],'req_probe','deepseek-v4-pro','running','{}'))
        else:
            db.execute('INSERT INTO training_experiments VALUES(?,?,?)',('exp_probe',conv['project_id'],'{}'))
            db.execute('INSERT INTO training_attempts VALUES(?,?,?,?)',('attempt_probe','exp_probe','unit_probe',json.dumps({'status':'running'})))
    with pytest.raises(Conflict,match='provider_switch_busy'):update(manager)
    assert not restarts and not key_for(s.config,'dashscope-deepseek')


def test_pending_turn_blocks_before_saving_key(managed,monkeypatch):
    s,_,manager,restarts=managed;monkeypatch.setattr(s.store,'active',lambda:[{'id':'queued'}])
    with pytest.raises(Conflict,match='provider_switch_busy'):update(manager)
    assert not key_for(s.config,'dashscope-deepseek') and not restarts


def test_failed_reload_restores_keys_and_configuration(managed,monkeypatch):
    s,_,manager,_=managed;calls=[]
    async def restart():
        calls.append(state(s.config)['active'])
        if len(calls)==1:raise RuntimeError('fixture reload failed')
    monkeypatch.setattr(manager,'restart',restart)
    with pytest.raises(RuntimeError,match='^provider_switch_failed$'):update(manager)
    assert calls==['dashscope-deepseek','deepseek-direct']
    assert manager.view().revision==1 and manager.view().active=='deepseek-direct'
    assert key_for(s.config,'deepseek-direct')=='official-fixture-key' and not key_for(s.config,'dashscope-deepseek')


def test_dashscope_capabilities_and_request_snapshots_contain_no_key(managed):
    s,_,manager,_=managed;update(manager)
    config=native_config(s.config);p=config['provider']['dashscope-deepseek']
    assert list(config['provider'])==['dashscope-deepseek']
    assert config['model']=='dashscope-deepseek/deepseek-v4-pro'
    assert 'dash-fixture-key' not in json.dumps(config) and p['options']['apiKey']=='{env:PATHOREASON_PROVIDER_API_KEY}'
    assert p['models']['deepseek-v4-pro']['variants']['none']=={'enable_thinking':False}
    assert {v['model']:v['efforts'] for v in reasoning(config)}=={
        'deepseek-v4-pro':['none','high','max'],'deepseek-v4.1-flash':['none','low','high','max']}
    assert all(o.choices==[8192,32768,65536] for o in outputs(s.config))
    assert {m['provider'] for m in s.models()}=={'dashscope-deepseek'}
    assert all(m['availability']=='catalog_only' for m in s.models())


def test_private_profiles_ignore_other_deployments_environment_key(managed,monkeypatch):
    s,_,manager,_=managed;update(manager)
    monkeypatch.setattr(settings_module,'settings',lambda:s.config)
    monkeypatch.setenv('DEEPSEEK_API_KEY','unrelated-env-key')
    monkeypatch.setenv('DASHSCOPE_API_KEY','another-env-key')
    assert settings_module.credential()=='dash-fixture-key'


def test_secret_never_echoed_in_api_or_validation_errors(managed,monkeypatch):
    from pathoreason.api import app
    s,_,manager,_=managed
    monkeypatch.setattr(app.state,'service',s,raising=False)
    monkeypatch.setattr('pathoreason.api.ProviderSettings',lambda service:manager)
    client=TestClient(app)
    r=client.get('/api/v1/settings/providers')
    assert r.status_code==200 and r.headers['cache-control']=='no-store' and 'official-fixture-key' not in r.text
    for body in [{'api_key':'private-fixture-input'}, {'api_key':'private-fixture-input'*100,'provider_id':'bad'}]:
        r=client.put('/api/v1/settings/providers',json=body)
        assert r.status_code==422 and 'private-fixture-input' not in r.text
    r=client.put('/api/v1/settings/providers',json={'expected_revision':1,'provider_id':'dashscope-deepseek','model':'deepseek-v4-pro',
        'base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1','api_key':'private-fixture-input'},headers={'Origin':'https://evil.invalid'})
    assert r.status_code==403 and state(s.config)['revision']==1
