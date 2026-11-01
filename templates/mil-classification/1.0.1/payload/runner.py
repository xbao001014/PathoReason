"""Task-local MIL entrypoint. Only execute through an authorized restricted worker.

All adaptable source is copied into this repository; no platform checkout import.
"""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import mil_execution as mil


def main():
    p=argparse.ArgumentParser()
    p.add_argument('operation',choices=['preflight','train'])
    p.add_argument('--config',required=True)
    p.add_argument('--report',required=True)
    p.add_argument('--output')
    p.add_argument('--device',default='cpu')
    args=p.parse_args()
    vendor=Path(__file__).resolve().parent/'vendor'
    if args.operation=='preflight':
        report=mil.preflight(args.config,vendor)
        with open(args.report,'x') as f:json.dump(report,f,indent=2)
        return 0 if report['status']=='passed' else 1
    if not args.output:raise ValueError('exclusive output directory required')
    # Authorization/isolation/budget belong to the external executor. This function
    # cannot grant them. Deployment currently refuses launch until it is connected.
    components=mil.prepare_training(args.config,vendor,args.report,args.device)
    train,val=mil.trainval_loaders(components)
    output=Path(args.output); output.mkdir(exist_ok=False)
    import torch
    for epoch in range(1,components.config['General']['num_epochs']+1):
        loss,elapsed=mil.train_epoch(components,train,args.device,epoch)
        result=mil.validate_epoch(components,val,args.device)
        # Raw results and per-epoch checkpoints stay separate; protocol-specific
        # model selection and independent test evaluation require Agent adaptation.
        torch.save({'model':components.model.state_dict(),'optimizer':components.optimizer.state_dict(),
                    'epoch':epoch},output/f'epoch-{epoch}.pt')
        with (output/f'epoch-{epoch}.json').open('x') as f:
            json.dump({'epoch':epoch,'train_loss':loss,'train_seconds':elapsed,
                       'validation':result},f,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x))
    return 0

if __name__=='__main__':sys.exit(main())
