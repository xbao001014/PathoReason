"""Conversation selection and immutable compute configurations for future turns."""
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .hardware import gpu_inventory
from .persistence import Conflict, encoded, now, uid


class GpuBinding(BaseModel):
    gpu_uuid: str
    gpu_index: int
    gpu_name: str
    revision: int
    compute_path: str
    compute_sha256: str


class GpuSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)
    gpu_uuid: str = Field(pattern=r'^GPU-[0-9a-fA-F-]{8,64}$')


class GpuSettingsView(BaseModel):
    conversation_id: str
    revision: int = 0
    source: Literal['project', 'conversation', 'unconfigured']
    gpu_uuid: str | None = None
    gpu_index: int | None = None
    gpu_name: str | None = None
    applies_to: Literal['future_turns'] = 'future_turns'


def checked_compute(path, root, digest=None):
    path, root = Path(path), Path(root).resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file() or path.stat().st_size > 1_000_000:
        raise Conflict('compute_config_unavailable')
    blob = path.read_bytes()
    if digest and hashlib.sha256(blob).hexdigest() != digest:
        raise Conflict('compute_config_changed')
    try:
        result = json.loads(blob)
        if not isinstance(result, dict) or not isinstance(result.get('gpu'), dict):
            raise ValueError()
        return result
    except ValueError:
        raise Conflict('compute_config_invalid') from None


class ConversationGpuSettings:
    def __init__(self, service):
        self.s = service
        with self.s.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS conversation_gpu_settings(
                conversation_id TEXT NOT NULL REFERENCES conversations(id), revision INTEGER NOT NULL,
                document TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(conversation_id,revision))''')

    def frozen(self, cid):
        self.s.store.conversation(cid)
        with self.s.store.connect() as db:
            row = db.execute('SELECT document FROM conversation_gpu_settings WHERE conversation_id=? ORDER BY revision DESC LIMIT 1', (cid,)).fetchone()
        if not row:
            return None
        binding = GpuBinding.model_validate_json(row[0])
        checked_compute(binding.compute_path, self.s.data/'runtime/compute-bindings', binding.compute_sha256)
        return binding

    def view(self, cid):
        conv = self.s.formal.mode(cid)
        binding = self.frozen(cid)
        if binding:
            return GpuSettingsView(conversation_id=cid, source='conversation', **binding.model_dump(exclude={'compute_path','compute_sha256'}))
        path = self.s.data/'projects'/conv['project_id']/'compute.json'
        if not path.exists():
            return GpuSettingsView(conversation_id=cid, source='unconfigured')
        gpu = checked_compute(path, self.s.data/'projects'/conv['project_id'])['gpu']
        return GpuSettingsView(conversation_id=cid, source='project', gpu_uuid=gpu.get('uuid'), gpu_index=gpu.get('index'))

    async def update(self, cid, body):
        if not self.s.formal.enabled():
            raise Conflict('formal_server_only')
        conv = self.s.store.conversation(cid, writable=True)
        self.s.formal.mode(cid)
        with self.s.store.connect() as db:
            self.s.conversations._check_idle(db, cid)
        await self.s.conversations._native_idle(conv)
        current = self.view(cid)
        if current.revision != body.expected_revision:
            raise Conflict('gpu_settings_revision_conflict')
        try:
            devices = await asyncio.to_thread(gpu_inventory)
        except Exception:
            raise Conflict('gpu_metrics_unavailable') from None
        gpu = next((d for d in devices if d.uuid == body.gpu_uuid), None)
        if gpu is None:
            raise Conflict('gpu_not_found')
        # Copy the project's current template, preserving paths, budgets and all authorization gates.
        compute = checked_compute(self.s.data/'projects'/conv['project_id']/'compute.json', self.s.data/'projects'/conv['project_id'])
        compute['gpu'].update(index=gpu.index, uuid=gpu.uuid)
        root = self.s.data/'runtime/compute-bindings'
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.resolve().is_relative_to(self.s.data.resolve()):
            raise Conflict('compute_config_unavailable')
        path = root/(uid('gpu')+'.json')
        blob = (json.dumps(compute, ensure_ascii=False, indent=2)+'\n').encode()
        binding = GpuBinding(gpu_uuid=gpu.uuid, gpu_index=gpu.index, gpu_name=gpu.name,
            revision=current.revision+1, compute_path=str(path), compute_sha256=hashlib.sha256(blob).hexdigest())
        try:
            with path.open('xb') as stream:
                stream.write(blob)
            with self.s.store.connect(True) as db:
                self.s.store.check_conversation(db, cid, writable=True)
                self.s.conversations._check_idle(db, cid)
                revision = db.execute('SELECT coalesce(max(revision),0) FROM conversation_gpu_settings WHERE conversation_id=?', (cid,)).fetchone()[0]
                if revision != current.revision:
                    raise Conflict('gpu_settings_revision_conflict')
                db.execute('INSERT INTO conversation_gpu_settings VALUES(?,?,?,?)', (cid,binding.revision,encoded(binding),now()))
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return self.view(cid)
