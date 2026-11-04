"""One disposable Python unit under the existing Landlock/seccomp policy."""
import ctypes,hashlib,json,os,resource,shutil,signal,subprocess,sys,time
from pathlib import Path
from .training_files import canonical,file_digest,manifest,verify_tree


def availability():
    try:
        libc=ctypes.CDLL(None,use_errno=True);abi=libc.syscall(444,0,0,1)
        ctypes.CDLL('libseccomp.so.2')
        if abi<1:raise RuntimeError('landlock_unavailable')
        if not shutil.which('systemd-run') or not Path('/run/user/'+str(os.getuid())+'/bus').exists():raise RuntimeError('training_user_cgroup_manager_required')
        return {'capability':'training_execution','available':True,'owner':'platform','backend':'landlock_seccomp','landlock_abi':abi,'parallel_units':1,'worker_contract':'python_threaded_no_subprocess','gpu_namespace_available':bool(shutil.which('unshare'))}
    except (OSError,RuntimeError) as exc:return {'capability':'training_execution','available':False,'owner':'platform','reason':str(exc)}


def run_unit(*,environment,code,inputs,output,entrypoint,args,shared_files,gpu,allowance,check_limits,memory_gib=16,record_launch=None):
    running,remaining=check_limits()
    if not running:raise InterruptedError('training_stop_requested')
    if remaining<=0:raise TimeoutError('training_budget_or_unit_deadline')
    allowance=min(allowance,remaining)
    output=canonical(output);(output/'tmp').mkdir();(output/'home').mkdir()
    root=Path(environment['path'])/'runtime';binding=environment['binding'];python=root/binding['python']
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(output/'home'),'TMPDIR':str(output/'tmp'),'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':gpu['uuid'] if gpu else '',
         'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','CUBLAS_WORKSPACE_CONFIG':':4096:8','CUDA_CACHE_PATH':str(output/'home/cuda'),'TORCH_HOME':str(output/'home/torch'),'XDG_CACHE_HOME':str(output/'home/cache'),
         'XDG_RUNTIME_DIR':'/run/user/'+str(os.getuid()),'LD_LIBRARY_PATH':str(root/'lib'),'PATHOREASON_INPUT_MANIFEST':str(inputs/'manifest.json'),'PATHOREASON_OUTPUT_DIR':str(output)}
    # Restriction code is platform-owned, snapshotted with this controller.
    restriction=str(Path(__file__).with_name('training_restrictions.py'))
    bootstrap='\n'.join([
        'import sys,os,ctypes,signal,json,runpy,resource',
        'sys.dont_write_bytecode=True',
        'libc=ctypes.CDLL(None,use_errno=True)',
        'assert libc.prctl(1,signal.SIGKILL,0,0,0)==0',
        f'assert os.getppid()=={os.getpid()}',
        f'namespace=runpy.run_path({restriction!r})',
        'resource.setrlimit(resource.RLIMIT_CORE,(0,0))',
        # A unit cannot raise limits after restrictions install.
        f'receipt=namespace["restrict"](code={str(code)!r},inputs={str(inputs)!r},output={str(output)!r},gpu_minor={gpu["minor"] if gpu else None!r},parent_network_namespace={os.readlink("/proc/self/ns/net")!r},shared_read_files={shared_files!r})',
        f'with open({str(output/"isolation.json")!r},"x") as f:json.dump(receipt,f)',
        f'sys.path[:0]={[str(code),*[str(root/p) for p in binding["extra_paths"]],str(root/binding["site"]) ]!r}',
        f'sys.argv={[str(code/entrypoint),*args]!r}',
        f'runpy.run_path({str(code/entrypoint)!r},run_name="__main__")',
    ])
    command=[str(python),'-I','-S','-B','-c',bootstrap]
    if gpu:
        unshare=shutil.which('unshare')
        if not unshare:raise ValueError('training_gpu_namespace_unavailable')
        command=[unshare,'--user','--map-root-user','--net',*command]
    command=['systemd-run','--user','--scope','--quiet','--unit=pr-unit-'+str(os.getpid())+'-'+str(time.time_ns()),'-p','MemoryMax='+str(memory_gib)+'G','-p','TasksMax=128','-p','RuntimeMaxSec='+str(allowance)+'s',*command]
    if record_launch:
        record_launch({'schema':'training-launch-spec/1','stage':'before_subprocess_dispatch',
            'environment_id':environment['id'],'python':str(python),'python_flags':['-I','-S','-B'],
            'cwd':str(code),'argv':[str(code/entrypoint),*args],
            'environment':env,'inherits_parent_environment':False,
            'entrypoint_sha256':file_digest(code/entrypoint),'controller_sha256':file_digest(Path(__file__)),
            'input_manifest':{'path':str(inputs/'manifest.json'),'sha256':file_digest(inputs/'manifest.json')},
            'limits':{'memory_gib':memory_gib,'allowance_seconds':allowance,'gpu':gpu},
            'task_runtime_observed':False})
    with open(output/'worker.log','xb') as log:
        p=subprocess.Popen(command,cwd=code,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,close_fds=True,start_new_session=True)
        started=time.monotonic()
        try:
            while p.poll() is None:
                running,remaining=check_limits()
                if not running:raise InterruptedError('training_stop_requested')
                if remaining<=0 or time.monotonic()-started>allowance:raise TimeoutError('training_budget_or_unit_deadline')
                time.sleep(.1)
        except BaseException:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait();raise
    if p.returncode:
        running,remaining=check_limits()
        if not running:raise InterruptedError('training_stop_requested')
        if remaining<=0 or time.monotonic()-started>=allowance:raise TimeoutError('training_budget_or_unit_deadline')
        raise RuntimeError('training_worker_exit_'+str(p.returncode))
    receipt=json.loads((output/'isolation.json').read_text())
    if receipt.get('backend')!='landlock_seccomp_v1':raise ValueError('training_isolation_receipt_missing')
    return receipt
