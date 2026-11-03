"""Print grouped cost evidence; only calls the read-only progress API."""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.training_costs import summarize,render_table


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    parser.add_argument('--format',choices=['json','table'],default='json')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.project):parser.error('invalid project id')
    url='http://127.0.0.1:8520/api/v2/research-projects/'+args.project+'/training-progress'
    with urllib.request.urlopen(url,timeout=30) as response:
        progress=json.load(response)
    result=summarize(progress)
    print(render_table(result) if args.format=='table' else json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
