import copy
import csv
import json
import os
from pathlib import Path
import subprocess

import pytest

from pathoreason.mil_execution import (
    ExecutionCheckError, configuration_diff, validate_config, validate_trainval_csv,
)


def config(path):
    return {'General': {'MODEL_NAME':'MEAN_MIL', 'seed':17, 'num_classes':3,
                       'num_epochs':30, 'num_workers':0, 'best_model_metric':'macro_auc',
                       'earlystop':{'use':False}},
            'Model': {'in_dim':64, 'dropout':0.1, 'act':'relu', 'criterion':'ce',
                      'optimizer':{'which':'adam', 'adam_config':{'lr':0.0002, 'weight_decay':0.00001}},
                      'scheduler':{'which':'step', 'warmup':0, 'step_config':{'step_size':3,'gamma':0.9}}},
            'Dataset': {'dataset_csv_path':str(path), 'balanced_sampler':{'use':False,'replacement':True}}}


def manifest(path, rows=None):
    with path.open('w', newline='') as f:
        w=csv.writer(f)
        w.writerow(['train_slide_path','train_label','val_slide_path','val_label','test_slide_path','test_label'])
        w.writerows(rows or [['/synthetic/train.pt','0','/synthetic/val.pt','1','','']])
    return path


@pytest.mark.parametrize('value', [True, False, 1, -0.1, 1.1, '0.1', float('nan')])
def test_probability_cannot_be_boolean_or_degenerate(tmp_path, value):
    c=config(tmp_path/'data.csv'); c['Model']['dropout']=value
    with pytest.raises(ExecutionCheckError): validate_config(c)


def test_requires_explicit_values_and_preserves_config(tmp_path):
    c=config(tmp_path/'data.csv')
    assert validate_config(c)==c
    for key in ('in_dim','dropout','act','optimizer','scheduler','criterion'):
        bad=copy.deepcopy(c); del bad['Model'][key]
        with pytest.raises(ExecutionCheckError): validate_config(bad)
    c['General']['MODEL_NAME']='DTFD_MIL'
    with pytest.raises(ExecutionCheckError, match='adapter_missing'): validate_config(c)


@pytest.mark.parametrize('rows,match', [
    ([['/x','0','/y','1','/sealed','2']], 'test_data_present'),
    ([['/x','','/y','1','','']], 'unpaired'),
    ([['/x','0','/x','1','','']], 'overlapping'),
    ([['/x','0','/y','3','','']], 'invalid class'),
    ([['/x','0','','','','']], 'nonempty'),
])
def test_manifest_rejections_without_feature_reads(tmp_path, rows, match):
    path=manifest(tmp_path/'data.csv', rows)
    with pytest.raises(ExecutionCheckError, match=match): validate_trainval_csv(path,3)


def test_empty_test_and_paired_padding_are_valid(tmp_path):
    p=manifest(tmp_path/'data.csv', [['/x','0','/y','1','',''], ['/z','2','','','','']])
    result=validate_trainval_csv(p,3)
    assert result['counts']=={'train':2,'val':1,'test':0}
    assert result['feature_contents_checked'] is False


@pytest.mark.parametrize('ambiguous', ['whitespace', 'duplicate_header'])
def test_csv_parsing_agrees_with_training_loader(tmp_path, ambiguous):
    path=manifest(tmp_path/'data.csv')
    if ambiguous=='whitespace':
        with path.open('a') as f:f.write(' , ,,,,\n')
    else:
        # Include all required columns while duplicating one recognized column.
        path.write_text('train_slide_path,train_label,val_slide_path,val_label,test_slide_path,test_label,train_slide_path\n/x,0,/y,1,,,/z\n')
    with pytest.raises(ExecutionCheckError): validate_trainval_csv(path,3)


def test_all_alignment_changes_reported(tmp_path):
    a=config(tmp_path/'data.csv'); b=copy.deepcopy(a)
    b['Model']['optimizer']['adam_config']['weight_decay']=0
    b['Model']['scheduler']['which']='none'
    b['General']['seed']=18
    differences=configuration_diff(a,b)
    assert {d['field'] for d in differences}=={
        'Model.optimizer.adam_config.weight_decay','Model.scheduler.which','General.seed'}


def test_real_vendor_synthetic_regression(tmp_path):
    """Opt-in environment integration, no project tensors and no GPU access."""
    python=os.environ.get('PATHOREASON_MIL_TEST_PYTHON')
    vendor=os.environ.get('PATHOREASON_MIL_TEST_VENDOR')
    if not python or not vendor: pytest.skip('training environment not configured')
    root=Path(__file__).resolve().parents[1]
    p=manifest(tmp_path/'data.csv'); cfg=tmp_path/'config.json'
    cfg.write_text(json.dumps(config(p)))
    code=r'''
import copy, json, sys
from pathlib import Path
import torch
from pathoreason.mil_execution import *
torch.set_num_threads(1)
cfg, vendor, output = sys.argv[1:]
report=preflight(cfg,vendor)
assert report['status']=='passed',report
Path(output).write_text(json.dumps(report))
fresh=prepare_training(cfg,vendor,output)
assert fresh.optimizer.param_groups[0]['weight_decay']==0.00001
assert fresh.scheduler.gamma==0.9 and fresh.scheduler.step_size==3
assert fresh.generator.initial_seed()==17
# Reproduce the actual upstream bug, including nonzero weight decay: checking
# parameter deltas alone would falsely pass this bias/decay-only training.
from modules.MEAN_MIL.mean_mil import MEAN_MIL
broken=MEAN_MIL(in_dim=64,num_classes=3)
assert [m.p for m in broken.modules() if isinstance(m,torch.nn.Dropout)]==[1.0]
fresh.model=broken
fresh.optimizer=torch.optim.Adam(broken.parameters(),lr=0.0002,weight_decay=0.01)
failed=probe_components(fresh)
assert failed['passed'] is False and 'head.0.weight' in failed['failed_weights']
for name in ('MAX_MIL','AB_MIL'):
    c=load_config(cfg); c['General']['MODEL_NAME']=name
    assert probe_components(build_components(c,vendor))['passed']
# Exercise the shared real loop on newly generated synthetic tensors only.
import csv
folder=Path(output).parent
rows=[]
for i in range(3):
    train=folder/f'train-{i}.pt'; val=folder/f'val-{i}.pt'
    torch.save(torch.randn(16,64),train); torch.save(torch.randn(12,64),val)
    rows.append([str(train),i,str(val),i,'',''])
synthetic=folder/'synthetic.csv'
with synthetic.open('w',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['train_slide_path','train_label','val_slide_path','val_label','test_slide_path','test_label'])
    writer.writerows(rows)
c=load_config(cfg); c['Dataset']['dataset_csv_path']=str(synthetic)
for name in ('MEAN_MIL','MAX_MIL','AB_MIL'):
    c['General']['MODEL_NAME']=name
    components=build_components(c,vendor)
    loaders=trainval_loaders(components)
    assert len(loaders)==2 and len(loaders[0].dataset)==3
    before={n:p.detach().clone() for n,p in components.model.named_parameters()}
    loss,elapsed=train_epoch(components,loaders[0],'cpu',1)
    val_loss,metrics=validate_epoch(components,loaders[1],'cpu')
    assert loss>0 and val_loss>0 and 'macro_auc' in metrics
    assert any(not torch.equal(p,before[n]) for n,p in components.model.named_parameters() if p.ndim>=2)
    assert components.scheduler.last_epoch==1
# Receipt cannot be reused after config, CSV, source binding or sampling changes.
original=Path(cfg).read_text()
c=json.loads(original); c['Model']['dropout']=0.2
Path(cfg).write_text(json.dumps(c))
try: prepare_training(cfg,vendor,output)
except ExecutionCheckError as e: assert 'stale' in str(e)
else: raise AssertionError('stale config accepted')
Path(cfg).write_text(original)
data=Path(c['Dataset']['dataset_csv_path']); saved=data.read_text()
data.write_text(saved.replace('/synthetic/val.pt','/synthetic/val-new.pt'))
try: prepare_training(cfg,vendor,output)
except ExecutionCheckError as e: assert 'stale' in str(e)
else: raise AssertionError('changed manifest accepted')
data.write_text(saved)
import os
os.environ['AUTO_MIL_MAX_PATCHES']='16'
try: prepare_training(cfg,vendor,output)
except ExecutionCheckError as e: assert 'stale' in str(e)
else: raise AssertionError('changed sampling accepted')
del os.environ['AUTO_MIL_MAX_PATCHES']
bad=copy.deepcopy(report); bad['binding']['adapter_sha256']='changed'
Path(output).write_text(json.dumps(bad))
try: prepare_training(cfg,vendor,output)
except ExecutionCheckError as e: assert 'stale' in str(e)
else: raise AssertionError('changed source accepted')
print(json.dumps({'good':report['trainability'],'bad_default':failed}))
'''
    env=dict(os.environ, PYTHONPATH=str(root/'src'), PYTHONDONTWRITEBYTECODE='1',
             CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    run=subprocess.run([python,'-c',code,str(cfg),vendor,str(tmp_path/'report.json')],
                       capture_output=True,text=True,env=env,timeout=60)
    assert run.returncode==0,run.stdout+run.stderr
    result=json.loads(run.stdout.strip().splitlines()[-1])
    assert result['good']['passed'] and not result['bad_default']['passed']
    command=[python,str(root/'scripts/mil_preflight.py'),'--config',str(cfg),'--vendor-root',vendor,
             '--report',str(tmp_path/'cli.json')]
    assert subprocess.run(command,env=env,capture_output=True,text=True,timeout=70).returncode==0
    saved=(tmp_path/'cli.json').read_bytes()
    assert subprocess.run(command,env=env,capture_output=True,text=True,timeout=70).returncode!=0
    assert (tmp_path/'cli.json').read_bytes()==saved
    c=config(p); c['Model']['dropout']=True; cfg.write_text(json.dumps(c))
    command[-1]=str(tmp_path/'failed.json')
    assert subprocess.run(command,env=env,capture_output=True,text=True,timeout=70).returncode==2
    assert json.loads((tmp_path/'failed.json').read_text())['status']=='failed'
