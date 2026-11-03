import json,os,time
from pathlib import Path
import pytest
from test_p1_service import fixture
from pathoreason.training_progress import project_progress,telemetry
from pathoreason.training_account import boot_id
from pathoreason.persistence import Missing


def setup(fixture):
    s,c,_,_=fixture;pid=c['project_id'];eid='exp_progress';scope='current'
    plan={'title':'Synthetic progress','task_id':'task_one','snapshot_id':'a'*64,'environment_id':'b'*64,'protocol':'Fixture only','evaluation':'previously_exposed','gpu_uuid':None,'memory_gib':16,'units':[{'id':'fit_a','label':'Fit A','phase':'fit','parameters':{'seed':1},'depends_on':[]},{'id':'fit_b','label':'Fit B','phase':'fit','parameters':{},'depends_on':[]},{'id':'eval_a','label':'Evaluate A','phase':'evaluate','parameters':{},'depends_on':['fit_a','fit_b']}]}
    doc={'id':eid,'project_id':pid,'conversation_id':c['id'],'revision':3,'status':'running','plan':plan,'scope_digest':scope,'run_id':'run_live','budget':{'max_wall_seconds':100.,'max_gpu_seconds':0.,'max_unit_seconds':30.,'max_attempts_per_unit':3},'authorized':True}
    attempts=[]
    for i,(unit,run,status,scp) in enumerate([('fit_a','run_failed','failed',scope),('fit_a','run_done','completed',scope),('fit_b','run_old','completed','old'),('fit_b','run_live','running',scope)]):
        out=s.data/'training/runs'/run/unit/'output';out.mkdir(parents=True)
        a={'id':'attempt_'+str(i),'unit_id':unit,'experiment_id':eid,'phase':'fit','run_id':run,'scope_digest':scp,'status':status,'error':'fixture failure' if status=='failed' else None,'output':str(out),'charged_seconds':None if status=='running' else 2.,'observed_seconds':1.,'started_monotonic':time.monotonic()-2,'started_at':time.time()-2,'boot_id':boot_id(),'gpu':False,'allowance':30.}
        attempts.append(a)
    with s.training.account.db() as db:
        db.execute('INSERT INTO training_experiments VALUES(?,?,?)',(eid,pid,json.dumps(doc)))
        for a in attempts:db.execute('INSERT INTO training_attempts VALUES(?,?,?,?)',(a['id'],eid,a['unit_id'],json.dumps(a)))
    return s,pid,eid,attempts

def rows(s):
    with s.store.connect() as db:return list(db.execute('SELECT document FROM training_experiments'))+list(db.execute('SELECT document FROM training_attempts'))+list(db.execute('SELECT document FROM training_events'))

def test_counts_are_receipts_current_scope_usage_keeps_failures_no_reconcile(fixture,monkeypatch):
    s,pid,eid,attempts=setup(fixture);before=[tuple(r) for r in rows(s)]
    monkeypatch.setattr(s.training,'view',lambda *a:pytest.fail('read projection must not reconcile'))
    out=project_progress(s,pid).model_dump();e=out['experiments'][0]
    assert e['counts']=={'fit':{'total':2,'completed':1},'evaluate':{'total':1,'completed':0}}
    assert [u['status'] for u in e['units']]==['completed','running','pending']
    assert e['units'][0]['retry_count']==1 and e['units'][1]['attempt_count']==2
    assert e['used_wall_seconds']>=8 and e['used_gpu_seconds']==0
    assert not e['scientific_approval'] and not out['execution_authority']
    assert [tuple(r) for r in rows(s)]==before
    assert 'output' not in json.dumps(out)

def test_metrics_sort_numeric_skip_partial_nonfinite_and_logs_escape_as_data(fixture):
    s,pid,eid,a=setup(fixture);out=Path(a[-1]['output'])
    for n in [10,2,1]:(out/f'epoch-{n}.json').write_text(json.dumps({'epoch':n,'train_loss':1/n,'val':{'macro_auc':.7,'patient_id':'private','n':24}}))
    (out/'epoch-11.json').write_text('{"epoch":')
    (out/'progress.json').write_text('{"epoch":12,"train_loss":NaN}')
    (out/'worker.log').write_text('\x1b[31m<script>fixture</script>\x1b[0m')
    v=telemetry(s,pid,eid,a[-1]['id'])
    assert [p['epoch'] for p in v.points]==[1,2,10] and v.last_epoch==10
    assert 'patient_id' not in json.dumps(v.points) and 'val.n' not in json.dumps(v.points)
    assert v.log=='<script>fixture</script>' and v.notices
    assert project_progress(s,pid).experiments[0]['current']['last_epoch']==10

def test_metrics_rows_and_jsonl_without_epoch_files(fixture):
    s,pid,eid,a=setup(fixture);out=Path(a[0]['output'])
    (out/'metrics.json').write_text(json.dumps({'rows':[{'epoch':1,'loss':2,'validation':{'loss':1.5}}]}))
    (out/'metrics.jsonl').write_text('{"epoch":2,"loss":1}\n{"epoch":')
    v=telemetry(s,pid,eid,a[0]['id']);assert v.last_epoch==2 and len(v.points)==2 and v.notices

def test_telemetry_is_attempt_scoped_and_project_scoped(fixture):
    s,pid,eid,a=setup(fixture)
    for i,row in enumerate(a):(Path(row['output'])/'epoch-1.json').write_text(json.dumps({'epoch':1,'loss':i}))
    assert telemetry(s,pid,eid,a[0]['id']).points[0]['metrics']['loss']==0
    assert telemetry(s,pid,eid,a[1]['id']).points[0]['metrics']['loss']==1
    other=s.store.create_project('Other','Other')['id']
    with pytest.raises(Missing):telemetry(s,other,eid,a[0]['id'])
    with pytest.raises(Missing):telemetry(s,pid,eid,'wrong')

@pytest.mark.parametrize('attack',['file_symlink','directory_symlink','output_mismatch','fifo'])
def test_output_boundary_rejects_symlinks_special_files_and_paths(fixture,attack):
    s,pid,eid,a=setup(fixture);out=Path(a[0]['output']);outside=s.data/'outside';outside.mkdir();(outside/'worker.log').write_text('SECRET')
    if attack=='file_symlink':(out/'worker.log').symlink_to(outside/'worker.log')
    elif attack=='directory_symlink':out.rmdir();out.symlink_to(outside,target_is_directory=True)
    elif attack=='fifo':os.mkfifo(out/'worker.log')
    else:
        a[0]['output']=str(outside)
        with s.training.account.db() as db:db.execute('UPDATE training_attempts SET document=? WHERE id=?',(json.dumps(a[0]),a[0]['id']))
    v=telemetry(s,pid,eid,a[0]['id']);assert not v.log and v.notices and 'SECRET' not in v.model_dump_json()

def test_log_and_metric_read_limits(fixture):
    s,pid,eid,a=setup(fixture);out=Path(a[0]['output'])
    (out/'worker.log').write_text('x'*100000+'END');(out/'metrics.json').write_text('x'*(1024*1024+1))
    for n in range(515):(out/f'epoch-{n}.json').write_text(json.dumps({'epoch':n,'loss':1}))
    v=telemetry(s,pid,eid,a[0]['id']);assert len(v.log.encode())==65536 and v.log.endswith('END') and v.log_truncated
    assert len(v.points)==512 and v.last_epoch==514 and v.notices

def test_endpoints_are_get_only_no_store_and_isolated(fixture,monkeypatch):
    import pathoreason.api as api
    from fastapi.testclient import TestClient
    s,pid,eid,a=setup(fixture);monkeypatch.setattr(api,'service',lambda:s)
    client=TestClient(api.app) # No lifespan: never starts another service/runtime.
    url=f'/api/v2/research-projects/{pid}/training-progress'
    assert client.get(url).status_code==200 and client.get(url).headers['cache-control']=='private, no-store'
    assert client.post(url,json={}).status_code==405
    detail=url+'/'+eid+'/attempts/'+a[0]['id'];assert client.get(detail).status_code==200
    assert client.get(url+'/wrong/attempts/'+a[0]['id']).status_code==404
    assert client.get(url+'/'+eid+'/attempts/wrong').status_code==404
