"""Detached matrix supervisor. Does not import an Agent's task or read its grants."""
import fcntl,json,os,stat,subprocess,sys,time,xml.etree.ElementTree as ET
from pathlib import Path
from .training_account import TrainingAccount
from .training_files import canonical,file_digest,manifest,verify_tree,relative,atomic
from .training_sandbox import run_unit


def gpu_binding(uuid):
    inventory=subprocess.run(['nvidia-smi','-q','-x','-i',uuid],capture_output=True,text=True,timeout=15,check=True)
    rows=ET.fromstring(inventory.stdout).findall('gpu')
    if len(rows)!=1 or rows[0].findtext('uuid')!=uuid:raise ValueError('training_gpu_identity_changed')
    if rows[0].findall('processes/process_info'):raise ValueError('training_gpu_busy')
    minor=int(rows[0].findtext('minor_number'));device=Path('/dev/nvidia'+str(minor)).stat()
    if not stat.S_ISCHR(device.st_mode) or os.minor(device.st_rdev)!=minor:raise ValueError('training_gpu_device_mismatch')
    return {'uuid':uuid,'minor':minor}


def main(root):
    root=canonical(root);request=json.loads((root/'request.json').read_text());account=TrainingAccount(request['database']);eid=request['experiment_id'];run_id=request['run_id']
    with open(root/'controller.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        doc=account.claim(eid,run_id)
        if not doc:return
        gpu_lock=None
        try:
            plan=doc['plan'];gpu=None
            code=Path(request['snapshot']['path'])/'code';env=request['environment']
            verify_tree(code,request['source_files']);verify_tree(Path(env['path'])/'runtime',env['binding']['files'])
            if plan['gpu_uuid']:
                gpu_lock=open(Path(request['gpu_locks'])/(plan['gpu_uuid']+'.lock'),'a')
                while True:
                    current=account.view(eid)
                    if current['status'] not in ('running','waiting_resource'):raise InterruptedError('training_stop_requested')
                    try:
                        fcntl.flock(gpu_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);gpu=gpu_binding(plan['gpu_uuid'])
                        with account.db() as db:
                            current=account.get(db,eid)
                            if current['status'] not in ('running','waiting_resource'):raise InterruptedError('training_stop_requested')
                            current.update(status='running',error=None);account.save(db,current)
                        break
                    except (BlockingIOError,ValueError) as exc:
                        fcntl.flock(gpu_lock,fcntl.LOCK_UN)
                        if not isinstance(exc,BlockingIOError) and str(exc)!='training_gpu_busy':raise
                        with account.db() as db:
                            current=account.get(db,eid)
                            if current['status'] not in ('running','waiting_resource'):raise InterruptedError('training_stop_requested')
                            current.update(status='waiting_resource',error='training_gpu_busy');account.save(db,current)
                        time.sleep(2)
            for unit in sorted(plan['units'],key=lambda u:u['phase']=='evaluate'):
                view=account.view(eid)
                if any(a['unit_id']==unit['id'] and a['status']=='completed' and a.get('scope_digest')==doc['scope_digest'] for a in view['attempts']):continue
                slot=root/unit['id'];slot.mkdir();output=slot/'output';output.mkdir();inputs=slot/'inputs';inputs.mkdir()
                a=account.begin(eid,run_id,unit,str(output))
                if a is None:continue
                started=time.monotonic()
                def check():
                    running,remaining=account.limits(eid,a['id'])
                    if not running:raise InterruptedError('training_stop_requested')
                    if remaining<=0:raise TimeoutError('training_budget_or_unit_deadline')
                try:
                    files=[f for f in plan['inputs'] if f['id'] in unit['input_ids']]
                    for f in files:
                        if file_digest(f['path'],check)!=f['sha256']:raise ValueError('training_input_changed')
                    dependencies=[]
                    for dependency in unit['depends_on']:
                        previous=next((x for x in reversed(view['attempts']) if x['unit_id']==dependency and x['status']=='completed' and x.get('scope_digest')==doc['scope_digest']),None)
                        if not previous:raise ValueError('training_dependency_not_completed')
                        for name,sha in previous['files'].items():
                            path=str(canonical(Path(previous['output'])/relative(name)))
                            if file_digest(path,check)!=sha:raise ValueError('training_dependency_output_changed')
                            dependencies.append({'unit_id':dependency,'name':name,'path':path,'sha256':sha})
                    atomic(inputs/'manifest.json',{'files':files,'dependencies':dependencies,'parameters':unit['parameters'],'phase':unit['phase']})
                    args=[arg.replace('{inputs}',str(inputs/'manifest.json')).replace('{output}',str(output)).replace('{device}','cuda:0' if gpu else 'cpu') for arg in unit['args']]
                    run_unit(environment=env,code=code,inputs=inputs,output=output,entrypoint=unit['entrypoint'],args=args,shared_files=[f['path'] for f in [*files,*dependencies]],gpu=gpu,allowance=a['allowance'],check_limits=lambda:account.limits(eid,a['id']),memory_gib=plan['memory_gib'])
                    for f in files:
                        if file_digest(f['path'],check)!=f['sha256']:raise ValueError('training_input_changed_after_execution')
                    for f in dependencies:
                        if file_digest(f['path'],check)!=f['sha256']:raise ValueError('training_dependency_output_changed')
                    results={p:file_digest(output/relative(p),check) for p in unit['output_files']}
                    verify_tree(code,request['source_files'])
                    account.finish(eid,a['id'],time.monotonic()-started,'completed',files=results)
                except BaseException as exc:
                    status='stopped' if isinstance(exc,InterruptedError) else 'budget_exhausted' if isinstance(exc,TimeoutError) else 'failed'
                    account.finish(eid,a['id'],time.monotonic()-started,status,error=str(exc));account.state(eid,run_id,status,str(exc));return
            account.state(eid,run_id,'completed')
        except BaseException as exc:
            message=str(exc);status='budget_exhausted' if 'budget_exhausted' in message or 'attempt_limit' in message else 'stopped' if 'stop_requested' in message else 'failed'
            account.state(eid,run_id,status,message)
        finally:
            if gpu_lock:gpu_lock.close()

if __name__=='__main__':main(sys.argv[1])
