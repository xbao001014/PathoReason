"""Explicit study I/O; does not start training or approve scientific outcomes."""
import argparse,json,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.settings import settings
from pathoreason.study_io import fetch_data,generate_image
p=argparse.ArgumentParser();p.add_argument('operation',choices=['data','image','publish']);p.add_argument('--project',required=True);p.add_argument('--disease');p.add_argument('--limit',type=int,default=1000);p.add_argument('--output');p.add_argument('--request');p.add_argument('--file');p.add_argument('--title');args=p.parse_args();cfg=settings()
if args.operation=='data':
 if not args.disease or not args.output:p.error('data requires --disease and --output')
 print(fetch_data(args.project,args.disease,args.limit,args.output,cfg))
elif args.operation=='image':
 if not args.request or not args.output:p.error('image requires --request and --output')
 print(generate_image(args.project,args.request,args.output,cfg))
else:
 if not args.file or not args.title:p.error('publish requires --file and --title')
 token=Path(cfg['data_root'])/'runtime/control/business-token'
 if token.is_symlink() or token.stat().st_mode & 0o077:raise ValueError('bridge_token_permissions')
 req=urllib.request.Request(f"http://127.0.0.1:{cfg['api_port']}/internal/formal/artifacts",data=json.dumps({'project_id':args.project,'relative_path':args.file,'title':args.title}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token.read_text().strip()})
 with urllib.request.urlopen(req,timeout=30) as r:result=json.load(r)
 print(json.dumps({'artifact_id':result['id'],'citation':'artifact:'+result['id'],'sha256':result['sha256']}))
