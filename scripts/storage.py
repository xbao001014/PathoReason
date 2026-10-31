import argparse
from pathlib import Path
from pathoreason.storage import allocate, data_root

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["check", "create"])
parser.add_argument("category", nargs="?")
parser.add_argument("name", nargs="?")
parser.add_argument("--config", type=Path, default=Path("config/pathoreason.local.json"))
args = parser.parse_args()
if args.action == "check":
    print(data_root(args.config))
else:
    if not args.category or not args.name:
        parser.error("create requires category and name")
    print(allocate(args.config, args.category, args.name))
