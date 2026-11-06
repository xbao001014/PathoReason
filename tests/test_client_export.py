import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from test_p1_service import fixture


def invoke(source, destination, pid):
    script=Path(__file__).resolve().parents[1]/'scripts/export_client_database.py'
    return subprocess.run([sys.executable,str(script),'--source',str(source),
        '--destination',str(destination),'--project',pid],capture_output=True,text=True)


def test_export_keeps_case_bytes_and_excludes_other_projects(fixture,tmp_path):
    s,conv,*_=fixture
    other=s.store.create_project('INTERNAL_ONLY','not for delivery',[])
    s.new_conversation(other['id'],'INTERNAL_ONLY')
    source=tmp_path/'source.sqlite3'
    with s.store.connect() as db,sqlite3.connect(source) as backup: db.backup(backup)
    original=source.read_bytes()
    dest=tmp_path/'delivery.sqlite3'
    result=invoke(source,dest,conv['project_id'])
    assert result.returncode==0, result.stderr
    with sqlite3.connect(dest) as db:
        assert db.execute('select id from projects').fetchall()==[(conv['project_id'],)]
        assert db.execute('select id from conversations').fetchall()==[(conv['id'],)]
        assert db.execute('select id from artifacts').fetchall()==[('art_test',)]
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not db.execute('pragma foreign_key_check').fetchall()
    assert b'INTERNAL_ONLY' not in dest.read_bytes()
    assert source.read_bytes()==original
    assert invoke(source,dest,conv['project_id']).returncode != 0


def test_unknown_schema_fails_before_creating_export(fixture,tmp_path):
    s,conv,*_=fixture
    with s.store.connect(True) as db: db.execute('create table unexpected_private_notes (body text)')
    dest=tmp_path/'delivery.sqlite3'
    result=invoke(s.store.path,dest,conv['project_id'])
    assert result.returncode != 0
    assert 'unclassified table' in result.stderr
    assert not dest.exists()
