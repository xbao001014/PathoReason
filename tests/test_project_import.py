import importlib.util
import sqlite3
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('project_import',Path(__file__).resolve().parents[1]/'scripts/import_project_database.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def database(path,project):
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE projects(id TEXT PRIMARY KEY,document TEXT); CREATE TABLE turns(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),status TEXT); CREATE TABLE shared(id TEXT PRIMARY KEY,document TEXT);')
        db.execute('INSERT INTO projects VALUES (?,?)',(project,'original '+project))
        db.execute('INSERT INTO turns VALUES (?,?,?)',('turn_'+project,project,'completed'))
        db.execute('INSERT INTO shared VALUES (?,?)',('config','identical'))


def test_additive_dry_run_and_idempotency(tmp_path):
    src,dst=tmp_path/'source.db',tmp_path/'target.db'
    database(src,'showcase');database(dst,'customer')
    result=module.merge(src,dst,'showcase')
    assert result['tables']['projects']['added']==1
    with sqlite3.connect(dst) as db:assert db.execute('SELECT * FROM projects').fetchall()==[('customer','original customer')]
    module.merge(src,dst,'showcase',True)
    with sqlite3.connect(dst) as db:
        assert db.execute('SELECT * FROM projects').fetchall()==[('customer','original customer'),('showcase','original showcase')]
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert all(v['added']==0 for v in module.merge(src,dst,'showcase',True)['tables'].values())


def test_late_conflict_rolls_back_all_rows(tmp_path):
    src,dst=tmp_path/'source.db',tmp_path/'target.db'
    database(src,'showcase');database(dst,'customer')
    with sqlite3.connect(dst) as db:db.execute("UPDATE shared SET document='customer changed this'")
    with pytest.raises(ValueError,match='conflicting'):module.merge(src,dst,'showcase',True)
    with sqlite3.connect(dst) as db:
        assert db.execute('SELECT id FROM projects').fetchall()==[('customer',)]
        assert db.execute('SELECT document FROM shared').fetchone()[0]=='customer changed this'


@pytest.mark.parametrize('cause',['schema','busy','other_project','missing_reference'])
def test_unsafe_inputs_rejected(tmp_path,cause):
    src,dst=tmp_path/'source.db',tmp_path/'target.db'
    database(src,'showcase');database(dst,'customer')
    with sqlite3.connect(src) as db:
        if cause=='schema':db.execute('CREATE TABLE unexpected(id TEXT PRIMARY KEY)')
        if cause=='busy':db.execute("UPDATE turns SET status='running'")
        if cause=='other_project':db.execute("INSERT INTO projects VALUES ('other','private')")
        if cause=='missing_reference':db.execute("UPDATE turns SET project_id='missing'")
    with pytest.raises(ValueError):module.merge(src,dst,'showcase',True)
    with sqlite3.connect(dst) as db:assert db.execute('SELECT id FROM projects').fetchall()==[('customer',)]
