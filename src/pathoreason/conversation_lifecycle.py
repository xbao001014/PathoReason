"""Conversation content lifecycle, independent of research assets and budget use."""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from . import contracts as c
from .persistence import Conflict, encoded, now


class ManagedConversation(c.Conversation):
    deletion_state: Literal['deleting', 'failed'] | None = None


class ConversationLifecycleView(BaseModel):
    conversation_id: str
    state: Literal['open', 'archived', 'deleting', 'failed', 'deleted']
    error_code: str | None = None
    requested_at: str | None = None
    completed_at: str | None = None
    native_deleted: bool = False
    project_assets_preserved: bool = True
    budget_preserved: bool = True


class DeleteConversationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirm: Literal[True]


class ConversationLifecycle:
    def __init__(self, service):
        self.s = service

    def view(self, cid):
        conv = self.s.store.conversation(cid, include_removed=True)
        with self.s.store.connect() as db:
            row = db.execute('SELECT document FROM conversation_deletions WHERE conversation_id=?', (cid,)).fetchone()
        if row:
            return ConversationLifecycleView(**json.loads(row[0]))
        return ConversationLifecycleView(conversation_id=cid, state=json.loads(conv['document'])['status'])

    def list(self, pid, include_archived=False):
        self.s.store.project(pid)
        with self.s.store.connect() as db:
            rows = db.execute('SELECT c.document,d.state FROM conversations c LEFT JOIN conversation_deletions d ON d.conversation_id=c.id WHERE c.project_id=? ORDER BY c.rowid DESC', (pid,)).fetchall()
        result = []
        for row in rows:
            doc = json.loads(row['document'])
            if row['state'] == 'deleted':
                continue
            if not include_archived and doc['status'] == 'archived' and not row['state']:
                continue
            result.append(ManagedConversation(**doc, deletion_state=row['state']))
        return result

    def _check_idle(self, db, cid):
        for row in db.execute('SELECT id FROM turns WHERE conversation_id=?', (cid,)):
            task = self.s.tasks.get(row[0])
            if task and not task.done():
                raise Conflict('conversation_busy')
        if db.execute("SELECT 1 FROM turns WHERE conversation_id=? AND status IN ('queued','running','interrupt_requested','recovery_required')", (cid,)).fetchone():
            raise Conflict('conversation_busy')
        if db.execute("SELECT 1 FROM context_operations WHERE conversation_id=? AND status IN ('running','recovery_required')", (cid,)).fetchone():
            raise Conflict('context_operation_unresolved')
        for row in db.execute('SELECT document FROM formal_permissions WHERE conversation_id=?', (cid,)):
            if json.loads(row[0]).get('state') == 'dispatching':
                raise Conflict('permission_outcome_requires_native_reconciliation')

    async def _native_idle(self, conv):
        sid = conv['native_session']
        if not sid:
            return
        try:
            status = await self.s.runtime.status(conv['directory'])
            if status.get(sid, {}).get('type', 'idle') != 'idle':
                raise Conflict('conversation_busy')
            if self.s.runtime_name == 'opencode':
                requests = await self.s.runtime.call('GET', '/permission', conv['directory'])
                if any(r.get('sessionID') == sid for r in requests):
                    raise Conflict('conversation_permission_pending')
        except Conflict:
            raise
        except Exception:
            raise Conflict('native_state_unavailable') from None

    async def archive(self, cid, restore=False):
        async with self.s.lock:
            conv = self.s.store.conversation(cid)
            self.s.store.project(conv['project_id'],writable=True)
            with self.s.store.connect() as db:
                self._check_idle(db, cid)
            await self._native_idle(conv)
            with self.s.store.connect(True) as db:
                self._check_idle(db, cid)
                doc = json.loads(conv['document'])
                doc['status'] = 'open' if restore else 'archived'
                if not restore:self.s.goals.archive(db,cid)
                db.execute('UPDATE conversations SET document=? WHERE id=?', (encoded(doc), cid))
            return self.view(cid)

    def _save(self, view):
        with self.s.store.connect(True) as db:
            if view.state == 'deleting':self._check_idle(db, view.conversation_id)
            db.execute('INSERT INTO conversation_deletions VALUES(?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET state=excluded.state,document=excluded.document', (view.conversation_id, view.state, encoded(view)))

    async def delete(self, cid):
        async with self.s.lock:
            conv=self.s.store.conversation(cid,include_removed=True)
            self.s.store.project(conv['project_id'],writable=True)
            return await self._delete_locked(cid)

    async def _delete_locked(self, cid):
        conv = self.s.store.conversation(cid, include_removed=True)
        previous = self.view(cid)
        if previous.state == 'deleted':
            return previous
        if conv['native_session'] and not hasattr(self.s.runtime, 'delete_session'):
            raise Conflict('native_deletion_unsupported')
        with self.s.store.connect() as db:
            self._check_idle(db, cid)
            if conv['native_session'] and db.execute('SELECT 1 FROM conversations WHERE native_session=? AND id<>?', (conv['native_session'], cid)).fetchone():
                raise Conflict('native_session_shared')
        await self._native_idle(conv)
        view = ConversationLifecycleView(conversation_id=cid, state='deleting', requested_at=previous.requested_at or now(), native_deleted=previous.native_deleted)
        # Lock new submissions before touching the external runtime. The marker
        # survives a process crash, so unknown outcomes are never reported done.
        self._save(view)
        try:
            if conv['native_session'] and not view.native_deleted:
                await self.s.runtime.delete_session(conv['native_session'], conv['directory'])
            view.native_deleted = True
            self._save(view)
            self._purge(cid, view)
        except asyncio.CancelledError:
            raise  # leave durable deleting state for explicit reconciliation
        except Exception as exc:
            view.state = 'failed'
            view.error_code = str(exc) if isinstance(exc, Conflict) else 'conversation_cleanup_incomplete'
            self._save(view)
        return self.view(cid)

    def _purge(self, cid, view):
        # The project directory is shared, including model-authored files. Never
        # infer ownership from a filename or recursively remove that directory.
        # Conversation-exclusive memory currently consists of DB content and the
        # native session. No standalone file memory is registered by this version.
        with self.s.store.connect(True) as db:
            self._check_idle(db, cid)
            self.s.goals.purge(db,cid)
            db.execute('DELETE FROM conversation_titles WHERE conversation_id=?',(cid,))
            db.execute('DELETE FROM conversation_guidance WHERE conversation_id=?',(cid,))
            for table in ['context_snapshots', 'p4_context_projections', 'skill_invocations', 'turn_guidance_context', 'turn_process_projection']:
                db.execute('DELETE FROM ' + table + ' WHERE turn_id IN (SELECT id FROM turns WHERE conversation_id=?)', (cid,))
            db.execute("UPDATE business_turns SET context='null' WHERE turn_id IN (SELECT id FROM turns WHERE conversation_id=?)", (cid,))
            db.execute('DELETE FROM events WHERE conversation_id=?', (cid,))
            db.execute('DELETE FROM bindings WHERE conversation_id=?', (cid,))
            db.execute('DELETE FROM conversation_permission_settings WHERE conversation_id=?', (cid,))
            # Handoff provenance is retained by artifact provenance records. The
            # handoff receipt is needed for deduplication; remove its free text.
            for row in db.execute('SELECT document FROM handoffs WHERE conversation_id=?', (cid,)).fetchall():
                record = json.loads(row[0])
                record = {k: v for k, v in record.items() if k in {'digest','source_environment','source_runtime','source_project_id','artifact_map','created_at'}}
                db.execute('UPDATE handoffs SET document=? WHERE conversation_id=?', (encoded(record), cid))
            # Preserve operation count and status, not compaction payloads.
            for row in db.execute('SELECT id,document FROM context_operations WHERE conversation_id=?', (cid,)).fetchall():
                old = json.loads(row['document'])
                keep = {k: v for k, v in old.items() if k in {'id','conversation_id','model','kind','status','started_at','finished_at'}}
                db.execute('UPDATE context_operations SET document=? WHERE id=?', (encoded(keep), row['id']))
            # Tool approval decisions remain traceable without storing command/output text.
            for row in db.execute('SELECT request_id,document FROM formal_permissions WHERE conversation_id=?', (cid,)).fetchall():
                old = json.loads(row['document'])
                keep = {k: v for k, v in old.items() if k in {'reply','at','state'}}
                db.execute('UPDATE formal_permissions SET document=? WHERE request_id=?', (encoded(keep), row['request_id']))
            # Keep turn identities, timing, status, usage, model and artifact links.
            # Budget queries continue to count the exact original rows and durations.
            db.execute("UPDATE turns SET user_text='',text='',tools='[]',input_digest='',native_message_id='' WHERE conversation_id=?", (cid,))
            row = db.execute('SELECT document FROM conversations WHERE id=?', (cid,)).fetchone()
            doc = json.loads(row[0])
            doc.update(title='已删除会话', status='archived')
            db.execute('UPDATE conversations SET document=?,native_session=NULL WHERE id=?', (encoded(doc), cid))
            view.state = 'deleted'
            view.completed_at = now()
            view.error_code = None
            db.execute('UPDATE conversation_deletions SET state=?,document=? WHERE conversation_id=?', (view.state, encoded(view), cid))
