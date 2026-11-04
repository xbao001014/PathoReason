"""Once-only first-turn titles; manual edits win without another model call."""
import json
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .persistence import Conflict, encoded, now

OPEN = '<pathoreason_title>'
CLOSE = '</pathoreason_title>'


def clean_title(value):
    value = ' '.join(value.split()).strip('"\'“”')
    if not value or len(value) > 120 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('conversation_title_invalid')
    return value


class ConversationTitleUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=120)

    @field_validator('title')
    @classmethod
    def validate_title(cls, value):
        return clean_title(value)


class ConversationTitleView(BaseModel):
    conversation_id: str
    title: str
    revision: int = 0
    source: Literal['original', 'automatic', 'fallback', 'manual'] = 'original'


class ConversationTitles:
    def __init__(self, service):
        self.s = service
        with self.s.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS conversation_titles(conversation_id TEXT PRIMARY KEY REFERENCES conversations(id),turn_id TEXT UNIQUE,document TEXT NOT NULL)')

    def _record(self, db, cid):
        row = db.execute('SELECT turn_id,document FROM conversation_titles WHERE conversation_id=?', (cid,)).fetchone()
        return (row['turn_id'], json.loads(row['document'])) if row else (None, {'revision': 0, 'source': 'original', 'auto_state': 'unstarted'})

    def _save(self, db, cid, tid, doc):
        db.execute('INSERT INTO conversation_titles VALUES(?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET turn_id=excluded.turn_id,document=excluded.document', (cid, tid, encoded(doc)))

    def view(self, cid):
        with self.s.store.connect() as db:
            conv = self.s.store.check_conversation(db, cid)
            _, doc = self._record(db, cid)
        return ConversationTitleView(conversation_id=cid, title=json.loads(conv['document'])['title'], revision=doc['revision'], source=doc['source'])

    async def rename(self, cid, body):
        async with self.s.lock:
            with self.s.store.connect(True) as db:
                conv = self.s.store.check_conversation(db, cid)
                self.s.store.check_project(db, conv['project_id'], writable=True)
                tid, doc = self._record(db, cid)
                if doc['revision'] != body.expected_revision:
                    raise Conflict('conversation_title_changed')
                value = json.loads(conv['document'])
                value['title'] = body.title
                # Even saving the original name deliberately disables automatic naming.
                doc.update(revision=doc['revision'] + 1, source='manual', auto_state='skipped', updated_at=now())
                doc.pop('candidate', None)
                self._save(db, cid, tid, doc)
                db.execute('UPDATE conversations SET document=? WHERE id=?', (encoded(value), cid))
        return self.view(cid)

    def bind(self, db, turn):
        # Called in the same transaction as first-turn creation. No historical backfill.
        if db.execute('SELECT 1 FROM conversation_titles WHERE conversation_id=?', (turn.conversation_id,)).fetchone():
            return
        first = db.execute('SELECT id FROM turns WHERE conversation_id=? ORDER BY rowid LIMIT 1', (turn.conversation_id,)).fetchone()
        if first and first[0] == turn.id:
            self._save(db, turn.conversation_id, turn.id, {'revision': 0, 'source': 'original', 'auto_state': 'pending'})

    def prompt(self, row):
        with self.s.store.connect() as db:
            tid, doc = self._record(db, row['conversation_id'])
        if tid != row['id'] or doc['auto_state'] != 'pending':
            return ''
        return ('\nConversation naming metadata: this is the first turn. At the very end of your final reply, '
                'add exactly one line <pathoreason_title>short title</pathoreason_title>. '
                'Summarize the user topic in the user\'s language, preferably 8–20 Chinese characters or 3–8 words, '
                'at most 80 characters. Describe the topic, not a success verdict; omit patient identifiers, credentials, '
                'paths and internal IDs. This metadata will be separated from the reply. Do not call another model, '
                'write a file, or take extra research actions to name the conversation.\n')

    def consume(self, tid, text):
        with self.s.store.connect() as db:
            record = db.execute('SELECT conversation_id,document FROM conversation_titles WHERE turn_id=?', (tid,)).fetchone()
        if not record:
            return text
        # Consume only a standalone metadata line, not quoted examples inside a sentence.
        match = re.search(r'(?m)^\s*' + re.escape(OPEN), text)
        if match:
            start = match.start()
            end = text.find(CLOSE, match.end())
            if end >= 0:
                candidate = text[match.end():end]
                try:
                    candidate = clean_title(candidate)
                    if len(candidate) > 80 or '<' in candidate or '>' in candidate:
                        raise ValueError('invalid_title')
                except ValueError:
                    candidate = None
                if candidate:
                    with self.s.store.connect(True) as db:
                        bound, doc = self._record(db, record['conversation_id'])
                        if bound == tid and doc['auto_state'] == 'pending' and doc.get('candidate') != candidate:
                            doc['candidate'] = candidate
                            self._save(db, record['conversation_id'], tid, doc)
                return (text[:start].rstrip() + text[end + len(CLOSE):]).strip()
            return text[:start].rstrip()
        # Hold back an unfinished opening tag during streaming.
        lines = text.rsplit('\n', 1)
        tail = lines[-1].strip()
        if tail and OPEN.startswith(tail):
            return lines[0].rstrip() if len(lines) == 2 else ''
        return text

    def finish(self, tid, status):
        if status not in ('completed', 'failed', 'interrupted'):
            return
        with self.s.store.connect(True) as db:
            row = db.execute('SELECT * FROM turns WHERE id=?', (tid,)).fetchone()
            bound, doc = self._record(db, row['conversation_id'])
            if bound != tid or doc['auto_state'] != 'pending':
                return
            conv = self.s.store.check_conversation(db, row['conversation_id'])
            value = json.loads(conv['document'])
            doc.update(auto_state='finished' if status == 'completed' else 'skipped', updated_at=now())
            if status == 'completed':
                candidate = doc.pop('candidate', None)
                # Omitted metadata falls back to a short topic excerpt, never another inference.
                fallback = re.sub(r'\[[^]]*\]\([^)]*\)|https?://\S+|[`#*_]', '', row['user_text']).strip()
                fallback = re.split(r'[\n。！？!?]', fallback, maxsplit=1)[0]
                fallback = ' '.join(fallback.split())[:32].rstrip('，,；;：: ')
                title = candidate or fallback
                if title:
                    value['title'] = title
                    doc.update(revision=doc['revision'] + 1, source='automatic' if candidate else 'fallback')
                    db.execute('UPDATE conversations SET document=? WHERE id=?', (encoded(value), row['conversation_id']))
            doc.pop('candidate', None)
            self._save(db, row['conversation_id'], tid, doc)

    def recover(self):
        with self.s.store.connect() as db:
            rows = db.execute("SELECT t.id,t.status FROM turns t JOIN conversation_titles c ON c.turn_id=t.id WHERE json_extract(c.document,'$.auto_state')='pending' AND t.status IN ('completed','failed','interrupted')").fetchall()
        for row in rows:
            self.finish(row['id'], row['status'])
