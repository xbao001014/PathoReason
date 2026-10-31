"""Conversation-scoped permissions. Changes affect future turns, never replay tools."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .persistence import Conflict, encoded, now
import json

Action = Literal['allow', 'ask', 'deny']

class PermissionSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['ask', 'auto', 'custom'] = 'ask'
    bash: Action = 'ask'
    edit: Action = 'ask'
    webfetch: Action = 'ask'
    external_directory: Action = 'ask'

    def action(self, tool):
        value = getattr(self, tool)
        if value == 'deny':
            return value
        return {'ask': 'ask', 'auto': 'allow'}.get(self.mode, value)

class PermissionSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)
    settings: PermissionSettings

class PermissionSettingsView(BaseModel):
    conversation_id: str
    revision: int
    settings: PermissionSettings
    applies_to: Literal['next_turn'] = 'next_turn'

def formal_rules(directory, settings=None):
    policy = settings or PermissionSettings()
    return [
        {'permission': '*', 'pattern': '*', 'action': 'deny'},
        *[{'permission': k, 'pattern': '*', 'action': 'allow'}
          for k in ['read', 'glob', 'grep', 'list', 'skill']],
        *[{'permission': k, 'pattern': '*', 'action': policy.action(k)}
          for k in ['bash', 'edit', 'webfetch', 'external_directory']],
        # Trusted project directories are already inside the study's access boundary.
        *([{'permission': 'external_directory', 'pattern': p, 'action': 'allow'}
           for p in [directory+'/*', '/home/bxn/projects/PathoReason/*']]
          if policy.external_directory != 'deny' else []),
        *[{'permission': 'read', 'pattern': p, 'action': 'deny'} for p in
          ['*.env', '*.env.*', '*/.config/pathoreason/*', '*image-generation*.json',
           '*opencode-password', '*business-token']],
    ]

class ConversationPermissions:
    def __init__(self, formal):
        self.formal = formal
        self.s = formal.s
        with self.s.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS conversation_permission_settings(
                conversation_id TEXT NOT NULL REFERENCES conversations(id),
                revision INTEGER NOT NULL, document TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(conversation_id,revision))''')

    def view(self, cid):
        self.formal.mode(cid)
        with self.s.store.connect() as db:
            row = db.execute('SELECT revision,document FROM conversation_permission_settings '
                             'WHERE conversation_id=? ORDER BY revision DESC LIMIT 1', (cid,)).fetchone()
        return PermissionSettingsView(conversation_id=cid, revision=row['revision'] if row else 0,
            settings=PermissionSettings.model_validate_json(row['document']) if row else PermissionSettings())

    async def update(self, cid, body):
        if not self.formal.enabled():
            raise Conflict('formal_server_only')
        conv = self.formal.mode(cid)
        if any(r['conversation_id'] == cid for r in self.s.store.active()):
            raise Conflict('permission_settings_turn_active')
        if conv['native_session']:
            statuses = await self.s.runtime.status(conv['directory'])
            if statuses.get(conv['native_session'], {}).get('type', 'idle') != 'idle':
                raise Conflict('permission_settings_turn_active')
            if await self.formal.pending(cid):
                raise Conflict('permission_settings_turn_active')
        current = self.view(cid)
        if body.expected_revision != current.revision:
            raise Conflict('permission_settings_revision_conflict')
        with self.s.store.connect(True) as db:
            revision = db.execute('SELECT coalesce(max(revision),0) FROM conversation_permission_settings '
                                  'WHERE conversation_id=?', (cid,)).fetchone()[0]
            if revision != body.expected_revision:
                raise Conflict('permission_settings_revision_conflict')
            db.execute('INSERT INTO conversation_permission_settings VALUES(?,?,?,?)',
                       (cid, revision+1, encoded(body.settings), now()))
        return self.view(cid)
