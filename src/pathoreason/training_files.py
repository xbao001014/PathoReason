"""Content-bound environment and input helpers; never import task code here."""
import hashlib,json,os,re,shutil,stat,subprocess,sys,sysconfig,time
from email.parser import Parser
from pathlib import Path


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def canonical(path):
    p=Path(path)
    if not p.is_absolute() or '..' in p.parts or any(q.is_symlink() for q in (p,*p.parents)):raise ValueError('training_path_must_not_traverse_links')
    return p

def file_digest(path,check=None):
    path=canonical(path)
    with open(path,'rb') as f:
        first=os.fstat(f.fileno())
        if not stat.S_ISREG(first.st_mode) or first.st_nlink!=1:raise ValueError('training_regular_unlinked_file_required')
        h=hashlib.sha256()
        for block in iter(lambda:f.read(4*1024*1024),b''):
            if check:check()
            h.update(block)
        last=os.fstat(f.fileno())
    if (first.st_ino,first.st_size,first.st_mtime_ns,first.st_ctime_ns)!=(last.st_ino,last.st_size,last.st_mtime_ns,last.st_ctime_ns):raise ValueError('training_file_changed_during_read')
    return h.hexdigest()

def relative(value):
    p=Path(value)
    if not value or p.is_absolute() or '..' in p.parts or str(p)!=value or '\\' in value:raise ValueError('training_relative_path_required')
    return value

def atomic(path,value):
    p=Path(path);tmp=p.with_name(p.name+'.tmp-'+str(os.getpid()))
    with open(tmp,'x') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True);f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)

def manifest(root):
    root=canonical(root);result={}
    for base,dirs,files in os.walk(root):
        for name in dirs:canonical(Path(base)/name)
        for name in sorted(files):
            p=Path(base)/name
            result[p.relative_to(root).as_posix()]={'sha256':file_digest(p),'size':p.stat().st_size}
    return dict(sorted(result.items()))

def verify_tree(root,expected):
    if manifest(root)!=expected:raise ValueError('training_frozen_tree_changed')

def copy_tree(source,dest,allowed_roots):
    """Dereference trusted runtime links into independent bytes, not hard links."""
    source=Path(source);dest=Path(dest)
    if source.is_symlink():source=source.resolve(strict=True)
    if not any(source==p or source.is_relative_to(p) for p in allowed_roots):raise ValueError('environment_link_outside_runtime')
    if source.is_dir():
        dest.mkdir(parents=True,exist_ok=False)
        for p in sorted(source.iterdir()):
            if p.name in {'__pycache__','.git'} or (dest.name.startswith('python') and p.name in {'site-packages','dist-packages'}):continue
            copy_tree(p,dest/p.name,allowed_roots)
    else:
        st=source.stat()
        if not stat.S_ISREG(st.st_mode):raise ValueError('environment_special_file_rejected')
        dest.parent.mkdir(parents=True,exist_ok=True)
        before=source.stat()
        with open(source,'rb') as src,open(dest,'xb') as out:shutil.copyfileobj(src,out,4*1024*1024)
        after=source.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('environment_changed_during_copy')
        dest.chmod(0o555 if st.st_mode&0o111 else 0o444)

def freeze_environment(root,python,extra_paths,allowed_pythons,project_root):
    # Executables come from the configured runtime catalog, never task source.
    if python not in allowed_pythons:raise ValueError('training_python_not_in_runtime_catalog')
    info=json.loads(subprocess.check_output([python,'-I','-S','-B','-c',
        'import sys,sysconfig,json;print(json.dumps({"base":sys.base_prefix,"prefix":sys.prefix,"stdlib":sysconfig.get_path("stdlib"),"version":sys.version,"version_short":"%d.%d"%sys.version_info[:2]}))'],timeout=20))
    # Python >=3.14 initializes venv prefix even with -S; older venvs use pyvenv.cfg.
    executable=Path(python).resolve(strict=True);venv=Path(python).parent.parent
    base=Path(info['base']).resolve();stdlib=Path(info['stdlib']).resolve();version=info['version_short']
    site=venv/'lib'/('python'+version)/'site-packages'
    if not site.exists():site=Path(info['prefix'])/'lib'/('python'+version)/'site-packages'
    extras=[]
    for raw in extra_paths:
        p=canonical(raw)
        if not p.is_relative_to(project_root) or p==project_root:raise ValueError('environment_extra_must_be_project_dependency_directory')
        # Dependency copies may contain weights; no datasets/checkpoints/sealed inputs.
        if p.parts[len(project_root.parts)] not in {'.deps','environments'}:raise ValueError('environment_extra_must_be_dependency_directory')
        extras.append(p)
    root=canonical(root);root.mkdir(parents=True,exist_ok=True)
    staging=root/('building-'+str(time.time_ns()));staging.mkdir()
    runtime=staging/'runtime';runtime.mkdir();(runtime/'bin').mkdir();(runtime/'lib').mkdir()
    sources={base,stdlib,venv.resolve(),*extras}
    copy_tree(executable,runtime/'bin'/('python'+version),sources)
    copy_tree(stdlib,runtime/'lib'/('python'+version),sources)
    packages=runtime/'lib'/('python'+version)/'site-packages'
    if site.exists():copy_tree(site,packages,sources)
    else:packages.mkdir()
    # Dependent libpython lives outside stdlib on some Python distributions.
    for p in (base/'lib').glob('libpython*.so*'):
        if p.name not in {x.name for x in (runtime/'lib').iterdir()}:copy_tree(p,runtime/'lib'/p.name,sources)
    extra_rel=[]
    for i,p in enumerate(extras):
        dest=runtime/'extras'/str(i);copy_tree(p,dest,sources);extra_rel.append('extras/'+str(i))
    files=manifest(runtime)
    binding={'version':1,'python':'bin/python'+version,'site':'lib/python'+version+'/site-packages','extra_paths':extra_rel,'runtime':info,'files':files}
    distributions={}
    for directory in [*[runtime/p for p in extra_rel],packages]:
        for meta in sorted(directory.glob('*.dist-info/METADATA')):
            headers=Parser().parsestr(meta.read_text())
            if headers.get('Name') and headers.get('Version'):
                name=re.sub(r'[-_.]+','-',headers['Name']).lower()
                distributions.setdefault(name,headers['Version'])
    binding['distributions']=distributions
    # Host ABI remains part of the platform boundary; record it rather than claim a whole OS image.
    binding['host']={'machine':os.uname().machine,'kernel':os.uname().release,'libc':os.confstr('CS_GNU_LIBC_VERSION')}
    eid=digest(binding);final=root/eid
    if final.exists():
        existing=json.loads((final/'binding.json').read_text());verify_tree(final/'runtime',existing['files'])
        # Keep duplicate build evidence until explicit housekeeping; never overwrite objects.
    else:
        atomic(staging/'binding.json',binding)
        for basepath,dirs,files_ in os.walk(staging,topdown=False):Path(basepath).chmod(0o555)
        staging.rename(final)
    return {'id':eid,'path':str(final),'binding':binding}


def verify_requirements(code,binding):
    """A declared pin must match the effective frozen dependency search order."""
    for line in (code/'requirements.lock').read_text().splitlines():
        line=line.split('#',1)[0].strip()
        if not line:continue
        match=re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s;]+)',line)
        if not match:raise ValueError('training_requirement_pin_not_supported:'+line[:100])
        name=re.sub(r'[-_.]+','-',match[1]).lower()
        if binding.get('distributions',{}).get(name)!=match[2]:raise ValueError('training_environment_pin_mismatch:'+name)
