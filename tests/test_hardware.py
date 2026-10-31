import asyncio
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pathoreason import hardware
from pathoreason.compute_exec import execution_environment
from pathoreason.gpu_settings import GpuSettingsUpdate
from pathoreason.persistence import Conflict, Gone
from test_p1_service import fixture, settled
from test_p5_entry import study, formal_runtime

DEVICES = [hardware.GpuDevice(index=0,uuid='GPU-11111111',name='Fixture GPU A',memory_total_mb=24000,memory_used_mb=400),
           hardware.GpuDevice(index=3,uuid='GPU-33333333',name='Fixture GPU B',memory_total_mb=32000,memory_used_mb=31000)]


def prepare(fixture, monkeypatch):
    s,_,request,r=fixture
    formal_runtime(r)
    v=study(s,turns=5)
    c=s.store.conversations(v.project_id)[0]
    path=Path(v.workspace)/'compute.json'
    template={'gpu':{'index':9,'uuid':DEVICES[0].uuid,'max_parallel_jobs':1},'real_training_authorized':False,'storage':{'runs':str(s.data/'studies'/v.project_id/'runs')},'budget':{'wall_seconds':60}}
    path.write_text(json.dumps(template))
    monkeypatch.setattr('pathoreason.gpu_settings.gpu_inventory',lambda:DEVICES)
    monkeypatch.setattr('pathoreason.compute_exec.gpu_inventory',lambda:DEVICES)
    async def call(*args):return []
    r.call=call
    return s,c,request,r,path,template


def test_inventory_safe_command_and_unknown_values(monkeypatch):
    def run(command,**kwargs):
        assert command[0]=='nvidia-smi' and kwargs['timeout']==3 and 'shell' not in kwargs
        return SimpleNamespace(stdout='0, GPU-11111111, "NVIDIA, Fixture", 24576, 1024, 0, 42\n3, GPU-33333333, Fixture B, 32000, [N/A], [N/A], [N/A]\n')
    monkeypatch.setattr(hardware.subprocess,'run',run)
    rows=hardware.gpu_inventory()
    assert rows[0].name=='NVIDIA, Fixture' and rows[0].utilization_percent==0
    assert rows[1].memory_used_mb is None and rows[1].utilization_percent is None


def test_unavailable_gpu_does_not_claim_zero_usage(monkeypatch):
    monkeypatch.setattr(hardware,'gpu_inventory',lambda:(_ for _ in ()).throw(FileNotFoundError()))
    ticks=iter([(100,50),(200,75)])
    monkeypatch.setattr(hardware,'cpu_counters',lambda:next(ticks))
    view=hardware.sample('fixture')
    assert view.cpu_percent==75 and view.gpu_error=='gpu_metrics_unavailable' and view.gpus==[]


def test_hardware_cache_coalesces_parallel_pollers(monkeypatch):
    calls=[]
    def sample(env):
        calls.append(env)
        return hardware.HardwareSnapshot(environment=env,sampled_at='fixture',gpus=DEVICES)
    monkeypatch.setattr(hardware,'sample',sample)
    async def case():
        monitor=hardware.HardwareMonitor('bxn-server')
        a,b=await asyncio.gather(monitor.snapshot(),monitor.snapshot())
        assert a==b and len(calls)==1
        monitor.sample_time-=5
        await monitor.snapshot()
        assert len(calls)==2
    asyncio.run(case())


def test_binding_is_by_uuid_versioned_and_preserves_template(fixture,monkeypatch):
    s,c,_,_,path,template=prepare(fixture,monkeypatch)
    original=path.read_bytes()
    assert s.gpu_settings.view(c['id']).gpu_index==9
    async def case():
        result=await s.gpu_settings.update(c['id'],GpuSettingsUpdate(expected_revision=0,gpu_uuid=DEVICES[0].uuid))
        assert result.gpu_index==0 and result.revision==1
        first=s.gpu_settings.frozen(c['id'])
        frozen=json.loads(Path(first.compute_path).read_text())
        assert frozen['gpu']=={'index':0,'uuid':DEVICES[0].uuid,'max_parallel_jobs':1}
        assert frozen['real_training_authorized'] is False
        assert frozen['storage']==template['storage'] and frozen['budget']==template['budget']
        await s.gpu_settings.update(c['id'],GpuSettingsUpdate(expected_revision=1,gpu_uuid=DEVICES[1].uuid))
        assert s.gpu_settings.frozen(c['id']).compute_path!=first.compute_path
        assert json.loads(Path(first.compute_path).read_text())==frozen and path.read_bytes()==original
        sibling=s.new_conversation(c['project_id'],'Sibling')
        assert s.gpu_settings.view(sibling['id']).source=='project'
        with pytest.raises(Conflict,match='revision_conflict'):
            await s.gpu_settings.update(c['id'],GpuSettingsUpdate(expected_revision=0,gpu_uuid=DEVICES[0].uuid))
        assert s.store.turns(c['id'])==[]
    asyncio.run(case())


def test_missing_gpu_and_unresolved_state_do_not_write(fixture,monkeypatch):
    s,c,_,_,_,_=prepare(fixture,monkeypatch)
    async def case():
        with pytest.raises(Conflict,match='gpu_not_found'):
            await s.gpu_settings.update(c['id'],GpuSettingsUpdate(expected_revision=0,gpu_uuid='GPU-99999999'))
        await s.conversations.archive(c['id'])
        with pytest.raises(Conflict,match='archived'):
            await s.gpu_settings.update(c['id'],GpuSettingsUpdate(expected_revision=0,gpu_uuid=DEVICES[0].uuid))
        assert s.gpu_settings.frozen(c['id']) is None
        await s.conversations.delete(c['id'])
        with pytest.raises(Gone):s.gpu_settings.view(c['id'])
    asyncio.run(case())


def backup_for_launcher(s):
    with s.store.connect() as source,sqlite3.connect(s.data/'state/pathoreason.sqlite3') as target:
        source.backup(target)


def test_turn_freezes_device_and_launcher_applies_real_subprocess_environment(fixture,monkeypatch):
    s,c,request,r,_,_=prepare(fixture,monkeypatch)
    async def case():
        await s.gpu_settings.update(c['id'],GpuSettingsUpdate(expected_revision=0,gpu_uuid=DEVICES[0].uuid))
        r.hold=True
        result=await s.submit(c['id'],{**request,'skill_id':None,'artifact_ids':[],'execution_mode':'research'})
        tid=result['turn']['id']
        for _ in range(100):
            if s.store.turn(tid)['status']=='running':break
            await asyncio.sleep(.01)
        with pytest.raises(Conflict,match='conversation_busy'):
            await s.gpu_settings.update(c['id'],GpuSettingsUpdate(expected_revision=1,gpu_uuid=DEVICES[1].uuid))
        backup_for_launcher(s)
        env=execution_environment(s.config,tid,{'PATH':'/usr/bin:/bin','CUDA_VISIBLE_DEVICES':'9'})
        assert env['CUDA_VISIBLE_DEVICES']==DEVICES[0].uuid
        output=subprocess.check_output([sys.executable,'-c','import os,json;print(json.dumps({k:os.environ[k] for k in ["CUDA_VISIBLE_DEVICES","AUTORESEARCH_COMPUTE_CONFIG"]}))'],env=env,text=True)
        assert json.loads(output)['CUDA_VISIBLE_DEVICES']==DEVICES[0].uuid
        assert 'scripts/compute_exec.py --turn '+tid+' --' in s.formal.prompt(s.store.turn(tid))
        assert env['AUTORESEARCH_COMPUTE_CONFIG'] in s.formal.prompt(s.store.turn(tid))
        monkeypatch.setattr('pathoreason.compute_exec.gpu_inventory',lambda:[DEVICES[0].model_copy(update={'index':7})])
        with pytest.raises(Conflict,match='gpu_mapping_changed_reselect'):execution_environment(s.config,tid,{})
        monkeypatch.setattr('pathoreason.compute_exec.gpu_inventory',lambda:DEVICES)
        await s.interrupt(tid);await settled(s,tid);await asyncio.gather(*list(s.tasks.values()))
        original=s.store.turn(tid)['document']
        await s.gpu_settings.update(c['id'],GpuSettingsUpdate(expected_revision=1,gpu_uuid=DEVICES[1].uuid))
        assert s.store.turn(tid)['document']==original
        backup_for_launcher(s)
        with pytest.raises(Conflict,match='compute_turn_not_running'):execution_environment(s.config,tid,{})
    asyncio.run(case())


def test_config_tampering_does_not_silently_change_device(fixture,monkeypatch):
    s,c,_,_,_,_=prepare(fixture,monkeypatch)
    async def case():
        await s.gpu_settings.update(c['id'],GpuSettingsUpdate(expected_revision=0,gpu_uuid=DEVICES[0].uuid))
        binding=s.gpu_settings.frozen(c['id'])
        Path(binding.compute_path).write_text('{}')
        with pytest.raises(Conflict,match='compute_config_changed'):s.gpu_settings.frozen(c['id'])
    asyncio.run(case())


def test_api_scope_revision_and_hardware_response(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    from pathoreason.api import app
    s,c,_,_,_,_=prepare(fixture,monkeypatch);app.state.service=s
    async def snapshot():return hardware.HardwareSnapshot(environment='fixture',sampled_at='fixture',gpus=DEVICES)
    monkeypatch.setattr(s.hardware,'snapshot',snapshot)
    client=TestClient(app);url='/api/v2/conversations/'+c['id']+'/gpu-settings'
    assert len(client.get('/api/v2/hardware').json()['gpus'])==2
    body={'expected_revision':0,'gpu_uuid':DEVICES[1].uuid}
    assert client.put(url,json=body,headers={'Origin':'https://elsewhere.invalid'}).status_code==403
    assert client.put(url,json=body).json()['gpu_index']==3
    assert client.put(url,json=body).status_code==409
    assert client.put(url,json={'expected_revision':1,'gpu_uuid':'../../../tmp'}).status_code==422
    assert client.get(url).json()['applies_to']=='future_turns'
