"""Start only PathoReason-owned services; never signals an unrelated process."""
import argparse, json, os, signal, socket, subprocess, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pathoreason.settings import ROOT, settings, credential

cfg=settings(); data=Path(cfg["data_root"]); control=data/"runtime/control";control.mkdir(parents=True,exist_ok=True)

def identity(pid):
    try:
        fields=Path(f"/proc/{pid}/stat").read_text().split()
        return None if fields[2]=="Z" else fields[21]
    except (FileNotFoundError,ProcessLookupError):return None

def record(name):
    file=control/f"{name}.json"
    if not file.exists():return None
    value=json.loads(file.read_text())
    return value if identity(value["pid"])==value["identity"] else None

def stop(name):
    value=record(name)
    if not value:return
    os.killpg(value["pid"],signal.SIGTERM)
    for _ in range(50):
        if identity(value["pid"])!=value["identity"]:break
        time.sleep(.1)
    else:
        if identity(value["pid"])==value["identity"]:
            os.killpg(value["pid"],signal.SIGKILL)
            for _ in range(40):
                if identity(value["pid"])!=value["identity"]:break
                time.sleep(.05)
            else:raise RuntimeError(name+" did not stop")

def start(name):
    if record(name):return
    port=cfg["opencode_port"] if name=="opencode" else cfg["api_port"]
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        sock.bind(("127.0.0.1",port))
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTHONPATH=str(ROOT/"src"))
    env["PATH"]=str(Path(cfg["codex_binary"]).parent)+":"+env.get("PATH","")
    tool_path_file=ROOT/".tools/manuscript-path.json"
    if tool_path_file.exists():env["PATH"]=":".join(json.loads(tool_path_file.read_text()))+":"+env["PATH"]
    if name=="opencode":
        native=data/"runtime/opencode";native.mkdir(exist_ok=True)
        for category in ["config","data","cache","state"]:
            path=native/category;path.mkdir(exist_ok=True);env["XDG_"+category.upper()+"_HOME"]=str(path)
        password_file=control/"opencode-password"
        if not password_file.exists():
            import secrets
            password_file.write_text(secrets.token_urlsafe(32));password_file.chmod(0o600)
        env["OPENCODE_SERVER_PASSWORD"]=password_file.read_text().strip()
        env["OPENCODE_CONFIG"]=str(ROOT/"config/opencode.json")
        env["OPENCODE_DISABLE_PROJECT_CONFIG"]="true"
        env["OPENCODE_DISABLE_EXTERNAL_SKILLS"]="true"
        env["OPENCODE_DISABLE_AUTOUPDATE"]="true"
        env["OPENCODE_ENABLE_EXA"]="1"  # Native search for non-Zen providers; permission still applies.
        env["DEEPSEEK_API_KEY"]=credential()
        command=[cfg["opencode_binary"],"serve","--pure","--hostname","127.0.0.1","--port",str(port)]
        cwd=data/"projects/runtime";cwd.mkdir(exist_ok=True)
    else:
        command=[str(ROOT/".venv/bin/python"),"-m","uvicorn","pathoreason.api:app","--host","127.0.0.1","--port",str(port),"--timeout-graceful-shutdown","2"]
        cwd=ROOT
    with (control/f"{name}.log").open("ab") as log:
        child=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    (control/f"{name}.json").write_text(json.dumps({"pid":child.pid,"identity":identity(child.pid),"port":port,"credential_loaded":bool(env.get("DEEPSEEK_API_KEY")) if name=="opencode" else None})+"\n")
    time.sleep(.4)
    if child.poll() is not None:raise RuntimeError(name+" failed; inspect its service log")

parser=argparse.ArgumentParser();parser.add_argument("action",choices=["start","stop","stop-app","status","restart-app","restart-runtime","refresh-native"]);args=parser.parse_args()
import fcntl
with (control/"service.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    if args.action=="stop":stop("app");stop("opencode")
    elif args.action=="stop-app":stop("app")
    elif args.action=="refresh-native":
        import asyncio
        from pathoreason.runtime import OpenCode
        from pathoreason.native_refresh import maintenance_directories,refresh_idle_instances
        if cfg.get("primary_runtime")=="codex":raise RuntimeError('native_refresh_requires_opencode')
        if record('app'):raise RuntimeError('native_refresh_requires_app_offline')
        directories=maintenance_directories(data,cfg['api_port'])
        receipt=control/('native-refresh-'+str(time.time_ns())+'.jsonl')
        def save_receipt(value):
            with receipt.open('a') as file:file.write(json.dumps(value,ensure_ascii=False)+'\n')
        asyncio.run(refresh_idle_instances(OpenCode(data,cfg['opencode_port']),directories,
            {name:ROOT/'skills'/name/'SKILL.md' for name in ['benchmark-design','task-code-workspaces']},save_receipt))
        print(json.dumps({'native_refresh_receipt':str(receipt)}))
    elif args.action=="restart-app":stop("app");start("app")
    elif args.action=="restart-runtime":
        if cfg.get("primary_runtime")=="codex":stop("app");start("app")
        else:stop("opencode");start("opencode")
    elif args.action=="start":
        if cfg.get("primary_runtime")!="codex":start("opencode")
        start("app")
    print(json.dumps({n:record(n) for n in ["app","opencode"]}))
