"""Consistent DB + all registered artifact bytes; immutable research files via rsync.

Skips busy research. A changed platform DB during copy invalidates the snapshot.
Existing snapshots are never overwritten or removed automatically.
"""
import fcntl,hashlib,json,os,shutil,sqlite3,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.settings import ROOT,settings

CATEGORIES=['projects','studies','training','research','artifacts','manuscript_reviews','runtime']

def backup_sqlite(src,dst):
    with sqlite3.connect(src.as_uri()+'?mode=ro',uri=True) as db,sqlite3.connect(dst) as out:
        db.backup(out)
        if out.execute('pragma integrity_check').fetchone()[0]!='ok': raise RuntimeError('invalid backup')

def platform_state(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        active=db.execute("select count(*) from turns where status in ('queued','running','interrupt_requested','recovery_required')").fetchone()[0]
        active+=sum(json.loads(r[0]).get('state') not in {'completed','cancelled','paused','blocked'} for r in db.execute('select document from research_goals'))
        active+=sum(json.loads(r[0]).get('status') not in {'completed','failed','cancelled','stopped','interrupted'} for r in db.execute('select document from training_attempts'))
        active+=db.execute("select count(*) from context_operations where status in ('running','recovery_required')").fetchone()[0]
        if active: raise RuntimeError('research_busy_backup_skipped')
        h=hashlib.sha256()
        for (table,) in db.execute("select name from sqlite_master where type='table' order by name"):
            h.update(table.encode())
            for row in db.execute('select * from "'+table+'" order by rowid'):
                h.update(json.dumps(row,ensure_ascii=False).encode())
        return h.hexdigest()

def main():
    cfg=settings();data=Path(cfg['data_root'])
    parent=Path(cfg['delivery_backup_root']);parent.mkdir(mode=0o700,exist_ok=True)
    with (parent/'.backup.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=platform_state(data/'state/pathoreason.sqlite3')
        dest=parent/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());dest.mkdir(mode=0o700)
        backup_sqlite(data/'state/pathoreason.sqlite3',dest/'pathoreason.sqlite3')
        shutil.copy2(ROOT/'config/pathoreason.local.json',dest/'pathoreason.local.json')
        previous=sorted(p for p in parent.iterdir() if p.is_dir() and (p/'complete.json').is_file())
        linkbase=previous[-1] if previous else Path(cfg['delivery_backup_seed']) if cfg.get('delivery_backup_seed') else None
        for category in CATEGORIES:
            if not (data/category).exists():continue
            command=['rsync','-a']
            if linkbase:command+=['--link-dest='+str(linkbase/category)]
            command+=[str(data/category)+'/',str(dest/category)+'/']
            subprocess.run(command,check=True)
        for src in (data/'runtime').rglob('*'):
            if src.is_file() and src.suffix in {'.db','.sqlite','.sqlite3'}:
                target=dest/src.relative_to(data);tmp=target.with_name(target.name+'.consistent')
                backup_sqlite(src,tmp);os.replace(tmp,target)
                for suffix in ['-wal','-shm']:
                    Path(str(target)+suffix).unlink(missing_ok=True)
        with sqlite3.connect(dest/'pathoreason.sqlite3') as db:
            artifacts=[json.loads(r[0]) for r in db.execute('select document from artifacts')]
        for a in artifacts:
            if a['storage_root']=='legacy_evidence':continue
            if hashlib.sha256((dest/'artifacts'/a['relative_path']).read_bytes()).hexdigest()!=a['sha256']:
                raise RuntimeError('artifact_backup_hash_mismatch')
        if before!=platform_state(data/'state/pathoreason.sqlite3'):
            raise RuntimeError('platform_changed_backup_incomplete')
        (dest/'complete.json').write_text(json.dumps({'platform_sha256':before,'artifacts':len(artifacts),
            'native_databases':'individually_consistent','external_datasets':'referenced_not_copied'})+'\n')
        print(json.dumps({'backup':str(dest),'complete':True}))

if __name__=='__main__':main()
