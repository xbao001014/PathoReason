"""Refresh idle native instances during an offline application maintenance window."""
import hashlib
import json
import socket
import sqlite3
import re
from pathlib import Path


def configured_skills(root, config=None):
    """Build the expected catalog from configured paths, never a fixed name list.

    Only the name scalar is needed; reject unsupported/missing names explicitly
    instead of silently omitting a file. Do not read provider credentials.
    """
    root = Path(root)
    if config is None:
        config = json.loads((root / 'config/opencode.json').read_text())
    result = {}
    for entry in config.get('skills', {}).get('paths', []):
        directory = Path(entry).expanduser()
        if not directory.is_absolute():
            directory = root / directory
        if not directory.is_dir():
            raise RuntimeError('native_skill_directory_missing:' + str(directory))
        for file in sorted(directory.rglob('SKILL.md')):
            source = file.read_text()
            pieces = re.split(r'^---\s*$', source, maxsplit=2, flags=re.M)
            if len(pieces) != 3 or pieces[0].strip():
                raise RuntimeError('native_skill_frontmatter_invalid:' + str(file))
            names = re.findall(r'^name:\s*[\'\"]?([a-z0-9]+(?:-[a-z0-9]+)*)[\'\"]?\s*$', pieces[1], re.M)
            if len(names) != 1:
                raise RuntimeError('native_skill_name_invalid:' + str(file))
            name = names[0]
            if name in result and result[name].resolve() != file.resolve():
                raise RuntimeError('native_skill_duplicate:' + name)
            result[name] = file.resolve()
    if not result:
        raise RuntimeError('native_skill_catalog_empty')
    return result


async def inspect_skills(runtime, directory, required_skills):
    """Read-only comparison with the actual native cached bodies and locations."""
    found = {}
    for item in await runtime.call('GET', '/skill', directory):
        found.setdefault(item['name'], []).append(item)
    mismatches = []; hashes = {}
    for name, file in required_skills.items():
        source = Path(file).read_text()
        hashes[name] = hashlib.sha256(source.encode()).hexdigest()
        expected = re.split(r'^---\s*$', source, maxsplit=2, flags=re.M)[-1].strip()
        entries = found.get(name, [])
        if not entries:
            reason = 'missing'
        elif len(entries) != 1:
            reason = 'duplicate'
        elif Path(entries[0].get('location', '')).resolve() != Path(file).resolve():
            reason = 'location'
        elif entries[0].get('content', '').strip() != expected:
            reason = 'content'
        else:
            continue
        mismatches.append({'name': name, 'reason': reason})
    return {'directory': directory, 'verified': not mismatches,
            'skills': hashes, 'mismatches': mismatches}


def bound_directories(data):
    with sqlite3.connect(f'file:{data}/state/pathoreason.sqlite3?mode=ro', uri=True) as db:
        return [row[0] for row in db.execute('SELECT DISTINCT directory FROM conversations WHERE native_session IS NOT NULL ORDER BY directory')]


def maintenance_directories(data, api_port):
    # The application must be offline, so no submit/goal tick can race disposal.
    try:
        with socket.create_connection(('127.0.0.1', api_port), timeout=.5):
            raise RuntimeError('native_refresh_requires_app_offline')
    except ConnectionRefusedError:
        pass
    with sqlite3.connect(f'file:{data}/state/pathoreason.sqlite3?mode=ro', uri=True) as db:
        if db.execute("SELECT 1 FROM turns WHERE status IN ('queued','running','interrupt_requested','recovery_required') LIMIT 1").fetchone():
            raise RuntimeError('native_refresh_turn_unresolved')
        if db.execute("SELECT 1 FROM context_operations WHERE status IN ('running','recovery_required') LIMIT 1").fetchone():
            raise RuntimeError('native_refresh_context_unresolved')
        for row in db.execute('SELECT document FROM research_goals'):
            goal = json.loads(row[0])
            # Detached training continues without the app/native instance. While
            # the app is offline its receipt cannot race a new Agent dispatch.
            detached_wait = (goal.get('wait_for') or {}).get('kind') == 'training_run'
            if goal['state'] == 'active' or (goal['state'] == 'waiting' and not detached_wait):
                raise RuntimeError('native_refresh_goal_active')
        return [row[0] for row in db.execute('SELECT DISTINCT directory FROM conversations WHERE native_session IS NOT NULL ORDER BY directory')]


async def refresh_idle_instances(runtime, directories, required_skills, record):
    async def check(directory):
        if await runtime.call('GET', '/session/status', directory):
            raise RuntimeError('native_refresh_instance_busy')
        if await runtime.call('GET', '/permission', directory):
            raise RuntimeError('native_refresh_permission_pending')

    # Check all targets first; recheck each just before its mutation.
    for directory in directories:
        await check(directory)
    receipts = []
    for directory in directories:
        await check(directory)
        await runtime.call('POST', '/instance/dispose', directory)
        receipt = {'directory': directory, 'disposed': True, 'verified': False}
        record(dict(receipt))
        audit = await inspect_skills(runtime, directory, required_skills)
        if not audit['verified']:
            record({**receipt, **audit})
            raise RuntimeError('native_refresh_skill_mismatch:' + audit['mismatches'][0]['name'])
        mcp = await runtime.call('GET', '/mcp', directory)
        if mcp.get('pathoreason_dialogue', {}).get('status') != 'connected':
            raise RuntimeError('native_refresh_dialogue_disconnected')
        receipt.update(verified=True, skills=audit['skills'], dialogue='connected')
        record(dict(receipt));receipts.append(receipt)
    return receipts
