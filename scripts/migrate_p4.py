"""Explicit additive schema projection. No model, runtime, training, or legacy write."""
import argparse,json
from pathlib import Path
from types import SimpleNamespace
from pathoreason.settings import settings
from pathoreason.persistence import Store
from pathoreason.domain import Domain
p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group();group.add_argument('--apply',action='store_true');group.add_argument('--rollback',metavar='BATCH_ID');args=p.parse_args()
cfg=settings();data=Path(cfg['data_root']);store=Store(data/'state/pathoreason.sqlite3')
domain=Domain(SimpleNamespace(config=cfg,data=data,store=store))
result=domain.rollback(args.rollback) if args.rollback else domain.migrate(args.apply)
print(json.dumps(result,ensure_ascii=False,indent=2))
