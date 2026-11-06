"""Idle-only, revision-checked provider switching with rollback and write-only keys."""
import asyncio
import copy
import fcntl
import json
import os
import httpx
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from .persistence import Conflict, now
from .provider_config import PROVIDERS, atomic_private, effective_settings, key_for, native_config, private_directory, state, validate_endpoint
from .settings import ROOT


class ProviderProfileView(BaseModel):
    id: str
    title: str
    base_url: str
    model: str
    models: list[str]
    credential_present: bool


class ProviderSettingsView(BaseModel):
    revision: int
    active: str
    profiles: list[ProviderProfileView]
    scope: Literal['deployment']='deployment'


class ProviderSettingsUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision: int=Field(ge=1,strict=True)
    provider_id: Literal['deepseek-direct','dashscope-deepseek']
    base_url: str=Field(max_length=300)
    model: str=Field(max_length=100)
    api_key: SecretStr|None=Field(default=None,max_length=512)


class ProviderSettings:
    def __init__(self,service):self.s=service

    def current(self):
        if self.s.runtime_name!='opencode' or not self.s.config.get('provider_profiles_enabled'):
            raise ValueError('provider_management_unavailable')
        return state(self.s.config)

    def view(self):
        value=self.current()
        return ProviderSettingsView(revision=value['revision'],active=value['active'],profiles=[
            ProviderProfileView(id=pid,title=spec['title'],models=spec['models'],
                credential_present=bool(key_for(self.s.config,pid)),**value['profiles'][pid])
            for pid,spec in PROVIDERS.items()])

    async def idle(self):
        s=self.s
        if s.store.active():raise Conflict('provider_switch_busy')
        with s.store.connect() as db:
            if db.execute("SELECT 1 FROM context_operations WHERE status IN ('running','recovery_required') LIMIT 1").fetchone():
                raise Conflict('provider_switch_busy')
            for row in db.execute('SELECT document FROM research_goals'):
                if json.loads(row[0]).get('state') not in {'completed','cancelled','blocked','paused'}:
                    raise Conflict('provider_switch_busy')
            for row in db.execute('SELECT document FROM training_attempts'):
                if json.loads(row[0]).get('status') not in {'completed','failed','cancelled','stopped','interrupted'}:
                    raise Conflict('provider_switch_busy')
            directories={r[0] for r in db.execute('SELECT DISTINCT directory FROM conversations WHERE native_session IS NOT NULL')}
        directories.add(str(s.data/'projects/runtime'))
        for directory in sorted(directories):
            if not Path(directory).is_dir():continue
            try:
                status=await s.runtime.call('GET','/session/status',directory)
                permissions=await s.runtime.call('GET','/permission',directory)
            except httpx.HTTPError:
                record=s.data/'runtime/control/opencode.json'
                if record.exists():
                    process=json.loads(record.read_text());proc=Path('/proc')/str(process['pid'])/'stat'
                    if proc.exists() and proc.read_text().split()[21]==process['identity']:
                        raise RuntimeError('provider_runtime_unavailable') from None
                return  # No live owned engine; restart still verifies ownership and port availability.
            if any(v.get('type')!='idle' for v in status.values()) or permissions:
                raise Conflict('provider_switch_busy')

    async def restart(self):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),PYTHONDONTWRITEBYTECODE='1')
        process=await asyncio.create_subprocess_exec(str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/service.py'),
            'restart-runtime',cwd=ROOT,env=env,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        try:await asyncio.wait_for(process.wait(),20)
        except asyncio.TimeoutError:
            process.kill();await process.wait();raise RuntimeError('provider_restart_failed') from None
        if process.returncode:raise RuntimeError('provider_restart_failed')
        expected=state(self.s.config)
        for _ in range(40):
            try:
                health=await self.s.runtime.health()
                if health.get('healthy') and health.get('provider_revision')==expected['revision']:
                    providers=await self.s.runtime.call('GET','/provider',str(self.s.data/'projects/runtime'))
                    current=next((p for p in providers['all'] if p['id']==expected['active']),None)
                    if current and expected['profiles'][expected['active']]['model'] in current.get('models',{}):return
            except Exception:pass
            await asyncio.sleep(.25)
        raise RuntimeError('provider_restart_failed')

    def audit(self, outcome, value):
        path=private_directory(self.s.config)/'audit.jsonl'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'a') as f:
            f.write(json.dumps({'at':now(),'outcome':outcome,'provider':value['active'],'revision':value['revision']})+'\n')

    async def update(self, body):
        async with self.s.lock:
            directory=private_directory(self.s.config)
            with (directory/'update.lock').open('a') as lock:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise Conflict('provider_switch_busy') from None
                old=self.current()
                if body.expected_revision!=old['revision']:raise Conflict('provider_settings_stale')
                pid=body.provider_id
                endpoint=validate_endpoint(pid,body.base_url)
                if body.model not in PROVIDERS[pid]['models']:raise ValueError('model_not_configured')
                key=body.api_key.get_secret_value().strip() if body.api_key else ''
                if key and (not key.isascii() or any(ord(c)<33 or ord(c)>126 for c in key) or any(c in key for c in '\"\'')):
                    raise ValueError('provider_key_invalid')
                if not key and not key_for(self.s.config,pid):raise ValueError('provider_key_missing')
                await self.idle()
                new=copy.deepcopy(old);new.update(active=pid,revision=old['revision']+1)
                new['profiles'][pid]={'base_url':endpoint,'model':body.model}
                key_path=directory/(pid+'.env');old_key=key_path.read_bytes() if key_path.exists() else None
                try:
                    if key:atomic_private(key_path,(PROVIDERS[pid]['key_env']+'='+key+'\n').encode())
                    atomic_private(directory/'profiles.json',(json.dumps(new,indent=2)+'\n').encode())
                    await self.restart()
                except BaseException:
                    # Retain the original exception only as a generic error; never reflect secret-bearing inputs.
                    atomic_private(directory/'profiles.json',(json.dumps(old,indent=2)+'\n').encode())
                    if old_key is None:key_path.unlink(missing_ok=True)
                    else:atomic_private(key_path,old_key)
                    try:await self.restart()
                    except BaseException:
                        self.audit('rollback_reload_failed',old)
                        raise RuntimeError('provider_rollback_failed') from None
                    self.audit('rolled_back',old)
                    raise RuntimeError('provider_switch_failed') from None
                self.s.config=effective_settings(self.s.config)
                self.s.runtime.config=self.s.config
                self.audit('applied',new)
                return self.view()

    async def reload(self):
        async with self.s.lock:
            self.current();await self.idle();await self.restart()
            self.s.config=effective_settings(self.s.config);self.s.runtime.config=self.s.config
            return {'status':'reloading'}
