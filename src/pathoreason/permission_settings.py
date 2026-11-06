"""Conversation-scoped permissions. Changes affect future turns, never replay tools."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .persistence import Conflict, encoded, now
from .settings import ROOT
import json

Action = Literal['allow', 'ask', 'deny']
TOOLS = ('bash', 'edit', 'webfetch', 'external_directory')

class PermissionSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    semantics_version: Literal[2] = 2
    mode: Literal['ask', 'auto', 'custom'] = 'ask'
    bash: Action = 'ask'
    edit: Action = 'ask'
    webfetch: Action = 'ask'
    external_directory: Action = 'ask'

    @model_validator(mode='after')
    def apply_preset(self):
        if self.mode != 'custom':
            for tool in TOOLS:
                setattr(self, tool, 'allow' if self.mode == 'auto' else 'ask')
        return self

    def action(self, tool):
        return getattr(self, tool)

    @classmethod
    def from_stored(cls, document):
        """Project legacy effective actions without rewriting history or granting access."""
        value = json.loads(document) if isinstance(document, str) else dict(document)
        if 'semantics_version' not in value:
            mode = value.get('mode', 'ask')
            actions = {tool: ('deny' if value.get(tool) == 'deny' else
                {'ask': 'ask', 'auto': 'allow'}.get(mode, value.get(tool, 'ask')))
                for tool in TOOLS}
            if mode != 'custom' and 'deny' in actions.values():
                value['mode'] = 'custom'
            value.update(actions)
        return cls.model_validate(value)

class PermissionSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)
    settings: PermissionSettings

class PermissionSettingsView(BaseModel):
    conversation_id: str
    revision: int
    settings: PermissionSettings
    effective_actions: dict[str, Action] = Field(default_factory=dict)
    applies_to: Literal['next_turn'] = 'next_turn'

def formal_rules(directory, settings=None, execution_scope="standard"):
    policy = settings or PermissionSettings()
    rules = [
        {'permission': '*', 'pattern': '*', 'action': 'deny'},
        *[{'permission': k, 'pattern': '*', 'action': 'allow'}
          for k in ['read', 'glob', 'grep', 'list', 'skill', 'pathoreason_dialogue_offer', 'pathoreason_dialogue_checkpoint', 'pathoreason_dialogue_training']],
        *[{'permission': k, 'pattern': '*', 'action': policy.action(k)}
          for k in ['bash', 'edit', 'webfetch', 'external_directory']],
        {'permission': 'websearch', 'pattern': '*', 'action': policy.action('webfetch')},
        # Trusted project directories are already inside the study's access boundary.
        *([{'permission': 'external_directory', 'pattern': p, 'action': 'allow'}
           for p in [directory+'/*', str(ROOT)+'/*']]
          if policy.external_directory != 'deny' else []),
        *[{'permission': 'read', 'pattern': p, 'action': 'deny'} for p in
          ['*.env', '*.env.*', '*/.config/pathoreason/*', '*image-generation*.json',
           '*opencode-password', '*business-token', '*guidance-token']],
    ]

    if execution_scope not in ('standard','dialogue','inspection'):raise ValueError('invalid_execution_scope')
    denied=['bash','edit','webfetch','websearch'] if execution_scope!='standard' else []
    if execution_scope=='dialogue':denied+=['read','glob','grep','list','skill','external_directory']
    rules.extend({'permission':tool,'pattern':'*','action':'deny'} for tool in denied)
    return rules

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
        policy=PermissionSettings.from_stored(row['document']) if row else PermissionSettings()
        return PermissionSettingsView(conversation_id=cid, revision=row['revision'] if row else 0,
            settings=policy,effective_actions={tool:policy.action(tool) for tool in TOOLS})

    async def update(self, cid, body):
        self.s.store.conversation(cid,writable=True)
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
            self.s.store.check_conversation(db,cid,writable=True)
            revision = db.execute('SELECT coalesce(max(revision),0) FROM conversation_permission_settings '
                                  'WHERE conversation_id=?', (cid,)).fetchone()[0]
            if revision != body.expected_revision:
                raise Conflict('permission_settings_revision_conflict')
            db.execute('INSERT INTO conversation_permission_settings VALUES(?,?,?,?)',
                       (cid, revision+1, encoded(body.settings), now()))
            self.s.goals.permissions_changed(db,cid,current.settings,body.settings,revision+1)
        return self.view(cid)
