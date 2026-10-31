"""Refresh safe action labels for one finished turn; no model call or research command."""
import argparse,asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.settings import settings
from pathoreason.persistence import Store
from pathoreason.runtime import OpenCode
from pathoreason.process_projection import refresh_process

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--turn',required=True);args=parser.parse_args()
    cfg=settings()
    if cfg.get('primary_runtime','opencode')!='opencode':parser.error('native process refresh currently requires OpenCode')
    root=Path(cfg['data_root'])
    print(json.dumps(asyncio.run(refresh_process(Store(root/'state/pathoreason.sqlite3'),OpenCode(root,cfg['opencode_port']),args.turn)),ensure_ascii=False))
