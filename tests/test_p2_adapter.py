"""Run with the pinned legacy environment; no model calls or training."""
import importlib.util,json,time
from pathlib import Path
import pytest
pytest.importorskip('experiment_agent',reason='adapter checks require the pinned legacy environment')

@pytest.fixture
def bridge(tmp_path,monkeypatch):
    file=Path(__file__).resolve().parents[1]/'src/pathoreason/business_worker.py'
    spec=importlib.util.spec_from_file_location('p2_bridge_test',file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setattr(m,'DATA',tmp_path);monkeypatch.setattr(m,'validate_output',lambda p:p)
    root=m.task_root('prj_fixture');doc=m.document(root)
    doc.update(status='awaiting_review',plan='a'*64,question='Synthetic fixture')
    m._write(root/'task.json',doc)
    monkeypatch.setattr(m.Adapter,'dispatch',lambda *args:None)
    return m,root

def act(m,ctl,operation,key,target=None):
    target=target or {'adapter':m.Adapter.id,'id':'prj_fixture'}
    current=ctl.discover(target)
    item=ctl.plan('prj_fixture',target,current['snapshot']['revision'],operation,key,{'turn_id':'turn_fixture'})
    item=ctl.decide('prj_fixture',item['id'],item['digest'],'approve')
    return ctl.execute('prj_fixture',item['id'],item['digest'])

def test_old_owner_marker_does_not_mark_new_recovery_dead(bridge):
    m,root=bridge;ctl=m.controller();item=act(m,ctl,'execute','start');receipt=item['receipt']
    run=root/'runs'/receipt['run_id'];run.mkdir(parents=True)
    m._write(run/'owner.json',{'pid':999999999,'start':'0'})
    # New dispatch has no own marker yet; the old run marker is irrelevant.
    result=m.Adapter().verify(root.name,'recover',receipt)
    assert result['action_status']=='waiting_for_workflow'
    assert m.document(root)['status']=='running'
    m._write(run/f"started-{receipt['action_id']}.json",{'pid':999999999,'start':'0'})
    result=m.Adapter().verify(root.name,'recover',receipt)
    assert result['workflow_status']=='needs_reconciliation'

def test_stop_signal_can_preempt_running_dispatch_without_replay(bridge):
    m,root=bridge;ctl=m.controller();item=act(m,ctl,'execute','start');run=root/'runs'/item['receipt']['run_id'];run.mkdir(parents=True)
    assert item['status']=='waiting_for_workflow'
    stop=act(m,ctl,'stop','stop',{'adapter':m.ControlAdapter.id,'id':root.name})
    assert stop['status']=='succeeded' and (run/'stop.requested').exists()
    result=ctl.execute(root.name,stop['id'],stop['digest'])
    assert result['id']==stop['id']
    assert ctl.journal.get(item['id'],root.name)['status']=='waiting_for_workflow'

def test_pending_dispatch_is_never_automatically_relaunched(bridge):
    m,root=bridge;ctl=m.controller();item=act(m,ctl,'execute','start')
    doc=m.document(root);doc['updated_at']=time.time()-20;m._write(root/'task.json',doc)
    result=ctl.reconcile(root.name,item['id'],item['digest'])
    assert result['result']['workflow_status']=='needs_reconciliation'
    assert not list((root/'runs').glob('**/started-*.json'))
