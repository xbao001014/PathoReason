"""Cron entry: restart only this deployment's missing, identity-checked services."""
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.settings import ROOT,settings

if __name__=='__main__':
    control=Path(settings()['data_root'])/'runtime/control'
    if not (control/'delivery-maintenance').exists():
        subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/service.py'),'start'],
                       cwd=ROOT,check=True,timeout=30,stdout=subprocess.DEVNULL)
