"""Versioned task repositories and content-verified source snapshots.

The database owns identity and revision history. task.json is a projection only.
No filesystem operation in this module executes task-supplied code or Git hooks.
Source snapshots are NOT authorization, immutable environments or OS sandboxes.
"""
from __future__ import annotations

import ast
import configparser
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from .contracts import canonical_digest, Identifier
from .persistence import Conflict, Missing, encoded, now, uid
from .settings import ROOT

SCHEMA = 'pathoreason.task-code/1'
MAX_FILE = 4 * 1024 * 1024
MAX_TREE = 32 * 1024 * 1024


class TaskCodeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    turn_id: Identifier
    grant: str = Field(min_length=1, max_length=128)
    operation: Literal['list', 'create', 'inspect', 'revise', 'check', 'freeze', 'inspect_update', 'launch']
    task_id: Identifier | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    idempotency_key: Identifier | None = None
    template: str = 'mil-classification/1.0.1'
    objective: str | None = Field(default=None, min_length=1, max_length=4000)
    parent_task_id: Identifier | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    check_id: Identifier | None = None
    snapshot_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


def sha(content):
    return hashlib.sha256(content).hexdigest()


def safe_relative(name):
    p = PurePosixPath(name)
    if not name or str(p) != name or p.is_absolute() or any(x in ('..', '.', '.git') for x in p.parts) or '\\' in name:
        raise ValueError('unsafe_relative_path')
    return p


def no_links(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute_canonical_path_required')
    if any(p.is_symlink() for p in (*path.parents, path)):
        raise ValueError('symlink_path_rejected')
    return path


def read_regular(path):
    """No following file links; reject hard links, special files and read races."""
    no_links(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE:
            raise ValueError('code_file_must_be_small_regular_unlinked_file')
        content = stream.read(MAX_FILE + 1)
        after = os.fstat(stream.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise Conflict('file_changed_during_read')
    if len(content) > MAX_FILE:
        raise ValueError('code_file_too_large')
    return content


def tree(root, *, git=False):
    no_links(root)
    result = {}
    size = 0
    for base, dirs, files in os.walk(root, followlinks=False):
        if Path(base) == root and git and '.git' in dirs:
            dirs.remove('.git')
        for name in dirs:
            p = Path(base)/name
            if p.is_symlink():raise ValueError('symlink_directory_rejected')
        for name in files:
            p = Path(base)/name
            rel = p.relative_to(root).as_posix()
            safe_relative(rel)
            content = read_regular(p)
            size += len(content)
            if size > MAX_TREE or len(result) >= 2000:raise ValueError('code_tree_too_large')
            result[rel] = {'sha256': sha(content), 'size': len(content), 'executable': bool(p.stat().st_mode & 0o111)}
    return dict(sorted(result.items()))


def git_command(root, *args):
    # Do not read user/global configuration, hooks, fsmonitor, external diffs or
    # signing programs. Run only read plumbing or explicit initialization commands.
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/nonexistent',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
    result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                             '-c', 'commit.gpgSign=false', '-c', 'core.untrackedCache=false',
                             '-c', 'diff.external=', '-c', 'core.pager=cat',
                             '-C', str(root), *args], env=env, capture_output=True, timeout=20)
    if result.returncode:raise ValueError('task_git_command_failed')
    return result.stdout


def revision(root):
    no_links(root/'.git')
    if not (root/'.git').is_dir():raise ValueError('independent_git_directory_required')
    # No alternate object stores, includes, hooks or worktree indirection.
    tree(root/'.git')  # No Git metadata may escape through links either.
    config = configparser.RawConfigParser()
    config.read_string(read_regular(root/'.git/config').decode())
    allowed = {'core': {'repositoryformatversion','filemode','bare','logallrefupdates','ignorecase','precomposeunicode'}, 'user': {'name','email'}}
    if any(section not in allowed or set(config[section])-allowed[section] for section in config.sections()):
        raise ValueError('unsafe_git_configuration')
    if config.get('core','bare',fallback='false').lower() != 'false':raise ValueError('bare_task_repository_rejected')
    if (root/'.git/info/grafts').exists() or (root/'.git/refs/replace').exists():raise ValueError('git_history_rewrite_rejected')
    if (root/'.git/objects/info/alternates').exists():raise ValueError('git_alternates_rejected')
    if git_command(root, 'status', '--porcelain=v1', '--untracked-files=all', '--ignored=matching'):
        raise Conflict('commit_all_files_before_registering_revision')
    commit = git_command(root, 'rev-parse', '--verify', 'HEAD').decode().strip()
    listing = git_command(root, 'ls-tree', '-rz', '--full-tree', 'HEAD')
    files = tree(root, git=True)
    tracked = {}
    for entry in listing.split(b'\0'):
        if not entry:continue
        metadata, name = entry.split(b'\t', 1)
        mode, kind, blob = metadata.split()
        name = name.decode('utf-8'); safe_relative(name)
        if kind != b'blob' or mode not in (b'100644', b'100755'):raise ValueError('git_links_and_submodules_rejected')
        content = git_command(root, 'cat-file', 'blob', blob.decode())
        tracked[name] = {'sha256': sha(content), 'size': len(content), 'executable': mode == b'100755'}
    if files != tracked:raise Conflict('git_index_or_worktree_bytes_differ')
    if commit != git_command(root, 'rev-parse', 'HEAD').decode().strip():raise Conflict('git_head_changed')
    return {'commit': commit, 'files': files, 'digest': canonical_digest(files)}


def write_new(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(content); stream.flush(); os.fsync(stream.fileno())


class TaskWorkspaces:
    def __init__(self, store, data, templates=None, source_roots=None):
        self.store = store
        self.data = no_links(Path(data))
        self.templates = Path(templates or ROOT/'templates')
        self.sources = source_roots or {'platform': ROOT}
        self.control = self.data/'state/task-code'
        no_links(self.control); self.control.mkdir(exist_ok=True, parents=True)
        with store.connect(True) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS task_code_tasks(
                  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                  revision INTEGER NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS task_code_actions(
                  project_id TEXT NOT NULL REFERENCES projects(id), request_key TEXT NOT NULL,
                  digest TEXT NOT NULL, status TEXT NOT NULL, document TEXT NOT NULL,
                  PRIMARY KEY(project_id,request_key));
                CREATE TABLE IF NOT EXISTS task_code_revisions(
                  task_id TEXT NOT NULL REFERENCES task_code_tasks(id), revision INTEGER NOT NULL,
                  document TEXT NOT NULL, PRIMARY KEY(task_id,revision));
                CREATE TABLE IF NOT EXISTS task_code_checks(
                  id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES task_code_tasks(id), document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS task_code_snapshots(
                  task_id TEXT NOT NULL REFERENCES task_code_tasks(id), id TEXT NOT NULL, document TEXT NOT NULL,
                  PRIMARY KEY(task_id,id));
                CREATE TABLE IF NOT EXISTS task_code_events(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
                  task_id TEXT, turn_id TEXT, kind TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS task_code_schema(version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO task_code_schema VALUES(1);
            ''')

    @contextmanager
    def lock(self, pid):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', pid):raise ValueError('invalid_project_id')
        path = self.control/(pid+'.lock'); no_links(path)
        with path.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def event(self, db, pid, tid, actor, kind, document):
        db.execute('INSERT INTO task_code_events(project_id,task_id,turn_id,kind,document) VALUES(?,?,?,?,?)',
                   (pid, tid, actor.get('turn_id'), kind, encoded({'at': now(), 'actor': actor, **document})))

    def paths(self, pid, tid):
        if not all(re.fullmatch(r'[A-Za-z0-9_-]+', x) for x in (pid,tid)):raise ValueError('invalid_identity')
        return (no_links(self.data/'projects'/pid/'tasks'/tid),
                no_links(self.data/'studies'/pid/'tasks'/tid))

    def get(self, pid, tid):
        with self.store.connect() as db:
            row = db.execute('SELECT document FROM task_code_tasks WHERE id=? AND project_id=?', (tid,pid)).fetchone()
        if not row:raise Missing('task_not_found')
        return json.loads(row[0])

    def list(self, pid):
        self.store.project(pid)
        with self.store.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT document FROM task_code_tasks WHERE project_id=? ORDER BY rowid', (pid,))]

    def template(self, name):
        rel = safe_relative(name)
        root = no_links(self.templates/rel)
        manifest = json.loads(read_regular(root/'manifest.json'))
        if manifest['template_id']+'/'+manifest['version'] != name:raise ValueError('template_identity_mismatch')
        copied = {}
        for entry in manifest['files']:
            dest = str(safe_relative(entry['destination']))
            origin = entry.get('source_root', 'template')
            if not re.fullmatch(r'[a-f0-9]{64}',entry['sha256']):raise ValueError('invalid_template_digest')
            cached = self.templates/'objects'/entry['sha256']
            source = cached if origin!='template' and cached.exists() else (root if origin=='template' else self.sources[origin])/safe_relative(entry['source'])
            content = read_regular(source)
            if sha(content) != entry['sha256']:raise Conflict('template_source_changed:'+dest)
            if dest in copied:raise ValueError('duplicate_template_destination')
            if dest.endswith(('.pt','.pth','.npy','.npz','.sqlite3','.pem','.key')) or '.env' in PurePosixPath(dest).parts:
                raise ValueError('noncode_template_file_rejected')
            copied[dest] = content
        if sum(map(len,copied.values())) > MAX_TREE:raise ValueError('template_too_large')
        if set(manifest['entrypoints']) - set(copied):raise ValueError('template_entrypoint_missing')
        return manifest, copied

    def projection(self, record):
        directory, _ = self.paths(record['project_id'],record['id'])
        # Agent-owned projection may have been replaced. Never overwrite arbitrary
        # links or external files; authoritative operations do not read this file.
        path=directory/'task.json'; no_links(path)
        temp=directory/('.projection-'+uid('tmp'))
        write_new(temp,(encoded(record)+'\n').encode())
        os.replace(temp,path)

    def catalog(self):
        path=self.templates/'catalog.json'
        if not path.exists():return {'recommended_template':None,'templates':[]}
        value=json.loads(read_regular(path))
        for entry in value['templates']:
            manifest=json.loads(read_regular(self.templates/safe_relative(entry['template'])/'manifest.json'))
            if canonical_digest(manifest)!=entry['manifest_sha256']:raise Conflict('template_catalog_changed')
        return value

    def act(self, pid, request, actor):
        """Serializes platform mutations; filesystem CAS detects Agent edits too."""
        op = request['operation']; tid=request.get('task_id')
        if op=='list':return {'tasks': self.list(pid),'catalog':self.catalog()}
        if op=='inspect':return self.inspect(pid,tid)
        if op=='inspect_update':return self.inspect_update(pid,tid,request['template'])
        key=request.get('idempotency_key')
        if not key:raise ValueError('idempotency_key_required')
        intent={k:v for k,v in request.items() if k not in ('grant','turn_id')}
        digest=canonical_digest(intent)
        with self.lock(pid):
            self.store.project(pid)
            with self.store.connect(True) as db:
                previous=db.execute('SELECT * FROM task_code_actions WHERE project_id=? AND request_key=?',(pid,key)).fetchone()
                if previous:
                    if previous['digest']!=digest:raise Conflict('idempotency_key_conflict')
                    saved=json.loads(previous['document'])
                    if previous['status']=='completed':return saved['result']
                    raise Conflict('task_action_'+previous['status']+':inspect_original_receipt')
                db.execute('INSERT INTO task_code_actions VALUES(?,?,?,?,?)',(pid,key,digest,'pending',encoded({'request':intent,'actor':actor,'at':now()})))
            try:
                if op=='create':result=self.create(pid,request,actor)
                else:
                    record=self.get(pid,tid)
                    if request.get('expected_revision')!=record['revision']:raise Conflict('task_revision_conflict')
                    if op=='revise':result=self.revise(record,request,actor)
                    elif op=='check':result=self.check(record,actor)
                    elif op=='freeze':result=self.freeze(record,request,actor)
                    elif op=='launch':
                        self.verify_snapshot(record,request.get('snapshot_id'))
                        raise Conflict('execution_backend_not_ready:immutable_environment_and_authorized_controller_required')
                    else:raise ValueError('unknown_task_operation')
                with self.store.connect(True) as db:
                    db.execute('UPDATE task_code_actions SET status=?,document=? WHERE project_id=? AND request_key=?',
                               ('completed',encoded({'result':result,'actor':actor,'at':now()}),pid,key))
                    self.event(db,pid,result['id'] if op=='create' else tid,actor,op,{'request_key':key})
                return result
            except Exception as exc:
                with self.store.connect(True) as db:
                    db.execute('UPDATE task_code_actions SET status=?,document=? WHERE project_id=? AND request_key=?',
                               ('failed',encoded({'error':str(exc),'actor':actor,'at':now(),'request':intent}),pid,key))
                    self.event(db,pid,tid,actor,op+'_failed',{'request_key':key,'error':str(exc)})
                raise

    def create(self,pid,request,actor):
        if not request.get('objective'):raise ValueError('objective_required')
        parent=request.get('parent_task_id')
        if parent:self.get(pid,parent)
        manifest,files=self.template(request['template'])
        tid=uid('task'); directory,storage=self.paths(pid,tid)
        directory.parent.mkdir(parents=True,exist_ok=True)
        staging=directory.with_name('.creating-'+tid)
        staging.mkdir(); code=staging/'code'; code.mkdir()
        try:
            for name,content in files.items():write_new(code/name,content)
            origin={'template':request['template'],'manifest_sha256':canonical_digest(manifest),
                    'manifest':manifest,'actor':actor,'created_at':now()}
            write_new(code/'TEMPLATE_ORIGIN.json',(encoded(origin)+'\n').encode())
            git_command(code,'init','--initial-branch=task')
            git_command(code,'config','user.name','PathoReason Agent')
            git_command(code,'config','user.email','agent@pathoreason.local')
            git_command(code,'add','--all')
            git_command(code,'-c','user.name=PathoReason','-c','user.email=pathoreason@localhost','commit','-m','Import versioned task template')
            rev=revision(code)
            record={'schema_version':SCHEMA,'id':tid,'project_id':pid,'objective':request['objective'],
                    'parent_task_id':parent,'revision':1,'template':request['template'],
                    'template_digest':canonical_digest(manifest),'origin':origin,
                    'code_path':str(directory/'code'),'storage_path':str(storage),
                    'code':rev,'created_at':now(),'actor':actor,'execution_ready':False}
            write_new(staging/'task.json',(encoded(record)+'\n').encode())
            os.rename(staging,directory)
            with self.store.connect(True) as db:
                db.execute('INSERT INTO task_code_tasks VALUES(?,?,?,?)',(tid,pid,1,encoded(record)))
                db.execute('INSERT INTO task_code_revisions VALUES(?,?,?)',(tid,1,encoded(record)))
            return record
        except Exception:
            # Only our unpublished staging tree is disposable. An already renamed
            # repository stays as recoverable evidence if DB publication fails.
            if staging.exists():shutil.rmtree(staging)
            raise

    def inspect(self,pid,tid):
        record=self.get(pid,tid)
        with self.store.connect() as db:
            history=[json.loads(r[0]) for r in db.execute('SELECT document FROM task_code_revisions WHERE task_id=? ORDER BY revision',(tid,))]
            checks=[json.loads(r[0]) for r in db.execute('SELECT document FROM task_code_checks WHERE task_id=? ORDER BY rowid',(tid,))]
            snapshots=[json.loads(r[0]) for r in db.execute('SELECT document FROM task_code_snapshots WHERE task_id=? ORDER BY rowid',(tid,))]
        with self.store.connect() as db:
            actions=[{'request_key':r['request_key'],'status':r['status'],**json.loads(r['document'])} for r in db.execute('SELECT * FROM task_code_actions WHERE project_id=? ORDER BY rowid',(pid,))]
        actions=[a for a in actions if a.get('request',{}).get('task_id')==tid or a.get('result',{}).get('id')==tid or a.get('result',{}).get('task_id')==tid]
        return {'task':record,'revisions':history,'checks':checks,'snapshots':snapshots,'actions':actions,
                'execution_ready':False,'execution_gap':'immutable environment and controller integration pending'}

    def current(self,record):
        code=self.paths(record['project_id'],record['id'])[0]/'code'
        rev=revision(code)
        if rev!=record['code']:raise Conflict('register_new_code_revision_first')
        return code,rev

    def revise(self,record,request,actor):
        if not request.get('reason'):raise ValueError('revision_reason_required')
        code=self.paths(record['project_id'],record['id'])[0]/'code'
        rev=revision(code)
        if rev==record['code']:raise Conflict('code_revision_unchanged')
        # New commits must retain the original imported history.
        git_command(code,'merge-base','--is-ancestor',record['code']['commit'],rev['commit'])
        updated={**record,'revision':record['revision']+1,'code':rev,'actor':actor,
                 'revision_reason':request['reason'],'updated_at':now()}
        with self.store.connect(True) as db:
            changed=db.execute('UPDATE task_code_tasks SET revision=?,document=? WHERE id=? AND revision=?',
                               (updated['revision'],encoded(updated),record['id'],record['revision'])).rowcount
            if changed!=1:raise Conflict('task_revision_conflict')
            db.execute('INSERT INTO task_code_revisions VALUES(?,?,?)',(record['id'],updated['revision'],encoded(updated)))
        self.projection(updated)
        return updated

    def check(self,record,actor):
        code,rev=self.current(record)
        gaps=[]
        for name in rev['files']:
            if name.endswith('.py'):
                try:ast.parse(read_regular(code/name),filename=name)
                except (SyntaxError,ValueError) as exc:gaps.append({'kind':'syntax','file':name,'detail':str(exc)})
        lock=code/'requirements.lock'
        if not lock.is_file():gaps.append({'kind':'dependencies','detail':'requirements.lock required'})
        else:
            for line in read_regular(lock).decode().splitlines():
                if line and not line.startswith('#') and not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+',line):
                    gaps.append({'kind':'dependencies','detail':'exact dependency pins required'})
        result={'id':uid('check'),'task_id':record['id'],'revision':record['revision'],'code':rev,
                'status':'failed' if gaps else 'passed','scope':'source_structure_only',
                'gaps':gaps,'execution_ready':False,'environment_verified':False,
                'trainability_verified':False,'scientific_approval':False,'at':now(),'actor':actor}
        if revision(code)!=rev:raise Conflict('code_changed_during_check')
        with self.store.connect(True) as db:
            db.execute('INSERT INTO task_code_checks VALUES(?,?,?)',(result['id'],record['id'],encoded(result)))
        return result

    def freeze(self,record,request,actor):
        code,rev=self.current(record)
        with self.store.connect() as db:
            row=db.execute('SELECT document FROM task_code_checks WHERE id=? AND task_id=?',(request.get('check_id'),record['id'])).fetchone()
        if not row:raise Missing('check_not_found')
        check=json.loads(row[0])
        if check['status']!='passed' or check['code']!=rev or check['revision']!=record['revision']:raise Conflict('check_stale_or_failed')
        # Content address includes the exact check and provenance, not Git SHA alone.
        binding={'schema_version':'pathoreason.source-snapshot/1','task_id':record['id'],
                 'revision':record['revision'],'code':rev,'check_id':check['id'],
                 'template_digest':record['template_digest'],'scope':'source_only','execution_ready':False}
        sid=canonical_digest(binding)
        _,storage=self.paths(record['project_id'],record['id'])
        parent=storage/'snapshots'; no_links(parent); parent.mkdir(parents=True,exist_ok=True)
        final=parent/sid
        if final.exists():
            return self.verify_snapshot(record,sid)
        staging=parent/('.building-'+uid('snapshot')); staging.mkdir()
        try:
            for name,expected in rev['files'].items():
                content=read_regular(code/name)
                if sha(content)!=expected['sha256']:raise Conflict('code_changed_during_freeze')
                write_new(staging/'code'/name,content)
                (staging/'code'/name).chmod(0o555 if expected['executable'] else 0o444)
            if revision(code)!=rev or tree(staging/'code')!=rev['files']:raise Conflict('snapshot_copy_race')
            write_new(staging/'binding.json',(encoded(binding)+'\n').encode())
            (staging/'binding.json').chmod(0o444)
            for base,dirs,files in os.walk(staging,topdown=False):Path(base).chmod(0o555)
            os.rename(staging,final)
            document={**binding,'id':sid,'path':str(final),'actor':actor,'created_at':now()}
            with self.store.connect(True) as db:
                db.execute('INSERT INTO task_code_snapshots VALUES(?,?,?)',(record['id'],sid,encoded(document)))
            return document
        except Exception:
            # Retain failed snapshot builds; never repurpose them as a valid snapshot.
            raise

    def verify_snapshot(self,record,sid):
        with self.store.connect() as db:
            row=db.execute('SELECT document FROM task_code_snapshots WHERE task_id=? AND id=?',(record['id'],sid)).fetchone()
        if not row:raise Missing('snapshot_not_registered')
        document=json.loads(row[0]); _,storage=self.paths(record['project_id'],record['id'])
        path=no_links(storage/'snapshots'/sid)
        binding=json.loads(read_regular(path/'binding.json'))
        expected={k:v for k,v in document.items() if k not in ('id','path','actor','created_at')}
        if binding!=expected or canonical_digest(binding)!=sid or tree(path/'code')!=binding['code']['files']:
            raise Conflict('snapshot_bytes_changed')
        return document

    def inspect_update(self,pid,tid,template):
        record=self.get(pid,tid); manifest,files=self.template(template)
        old={e['destination']:e['sha256'] for e in record['origin']['manifest']['files']}
        new={k:sha(v) for k,v in files.items()}
        return {'task_id':tid,'from_template':record['template'],'to_template':template,'catalog':self.catalog(),
                'files':[{'file':n,'old':old.get(n),'new':new.get(n),'task':record['code']['files'].get(n,{}).get('sha256')}
                         for n in sorted(old.keys()|new.keys()) if old.get(n)!=new.get(n)],
                'applied':False,'compatibility':'Agent review and new revision/check required',
                'target_manifest_sha256':canonical_digest(manifest)}
