"""Refresh idle native instances during an offline application maintenance window."""
import hashlib
import json
import socket
import sqlite3
from pathlib import Path


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
        if any(json.loads(row[0])['state'] in ('active','waiting') for row in db.execute('SELECT document FROM research_goals')):
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
        skills = {s['name']: s for s in await runtime.call('GET', '/skill', directory)}
        hashes = {}
        for name, file in required_skills.items():
            source = Path(file).read_text()
            expected = source.split('---', 2)[-1].strip()
            found = skills.get(name)
            if not found or Path(found['location']).resolve() != Path(file).resolve() or found['content'].strip() != expected:
                raise RuntimeError('native_refresh_skill_mismatch:' + name)
            hashes[name] = hashlib.sha256(source.encode()).hexdigest()
        mcp = await runtime.call('GET', '/mcp', directory)
        if mcp.get('pathoreason_dialogue', {}).get('status') != 'connected':
            raise RuntimeError('native_refresh_dialogue_disconnected')
        receipt.update(verified=True, skills=hashes, dialogue='connected')
        record(dict(receipt));receipts.append(receipt)
    return receipts
