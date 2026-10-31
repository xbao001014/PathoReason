"""Explicit Landlock CPU transport; reuses original preparation and evaluator."""
from pathlib import Path
import fcntl,json,os,signal,sys,time
ROOT=Path(__file__).resolve().parents[2]
CFG=json.loads((ROOT/'config/pathoreason.local.json').read_text())
sys.path.insert(0,str(Path(CFG['legacy_root'])/'packages/core'))
os.environ['AUTORESEARCH_COMPUTE_CONFIG']=str(ROOT/'config/p2-compute.local.json')
from experiment_agent.performance_loop.development_mil import _write,prepare_development,execute_development
from experiment_agent.performance_loop.local_plan import LocalLoopPlan,runtime_binding
from experiment_agent.performance_loop.contracts import digest
from experiment_agent.performance_loop.jobs import verify_unit

def run(path):
    with (path/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (path/'started.json').exists() or (path/'outcome.json').exists():return
        payload=json.loads((path/'job.json').read_text());started=time.monotonic()
        _write(path/'started.json',{'pid':os.getpid(),'at':time.time(),'job_sha256':digest(payload)})
        def expired(*_):raise TimeoutError('Frozen development allowance exhausted')
        signal.signal(signal.SIGALRM,expired)
        allowance=min(payload['timeout_seconds'],payload['deadline_at']-time.time())
        stop=lambda:(path/'stop.requested').exists()
        try:
            if allowance<=0:raise TimeoutError('Frozen deadline exhausted before preparation')
            signal.setitimer(signal.ITIMER_REAL,allowance)
            plan=LocalLoopPlan.model_validate(payload['plan']);unit=payload['unit']
            if plan.remote or plan.local_cuda or plan.cuda_execution or plan.planner:raise ValueError('Only fixed CPU synthetic execution')
            if next((u for u in plan.units() if u['id']==unit['id']),None)!=unit:raise ValueError('Unit identity mismatch')
            if runtime_binding()!=plan.contract.protocol.environment_sha256:raise ValueError('Runtime changed')
            if stop():raise InterruptedError('Stopped before preparation')
            prepared=prepare_development(unit['request'],plan.cohort,features_root=plan.features_root,
                workspace=path/'unit',layout='native_allowlist')
            if prepared['code_sha256']!=plan.contract.protocol.protected_training_sha256 or prepared['evaluator_sha256']!=plan.contract.protocol.evaluator_sha256:raise ValueError('Protected implementation changed')
            execute_development(path/'unit',backend='landlock_cpu',timeout_seconds=allowance-(time.monotonic()-started),stop_requested=stop)
            result=verify_unit(plan.model_dump(mode='json'),unit,path/'unit')
            outcome={'status':'completed','result':result}
        except Exception as exc:outcome={'status':'failed','error':type(exc).__name__+': '+str(exc)}
        finally:signal.setitimer(signal.ITIMER_REAL,0)
        _write(path/'outcome.json',{**outcome,'elapsed':time.monotonic()-started,'job_sha256':digest(payload)})

if __name__=='__main__':run(Path(sys.argv[1]))
