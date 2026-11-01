"""Explicit MIL construction and synthetic readiness checks, not a job scheduler.

Torch/PyYAML are loaded only in the training environment. No feature tensor is
read by preflight. The legacy implementation is imported read-only, never patched.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import random
import sys
from types import SimpleNamespace


ADAPTERS = {
    'MEAN_MIL': ('modules.MEAN_MIL.mean_mil', 'MEAN_MIL'),
    'MAX_MIL': ('modules.MAX_MIL.max_mil', 'MAX_MIL'),
    'AB_MIL': ('modules.AB_MIL.ab_mil', 'AB_MIL'),
}
SCHEMA = 'pathoreason.mil-preflight/1'


class ExecutionCheckError(ValueError):
    pass


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value, name, minimum=0, maximum=None, integer=False):
    if (type(value) not in ((int,) if integer else (int, float))
            or not math.isfinite(value) or value < minimum
            or (maximum is not None and value > maximum)):
        raise ExecutionCheckError(f'{name}: invalid numeric value (boolean is not a number)')
    return value


def validate_config(config):
    """Validate the supported explicit contract; never choose missing hyperparameters."""
    try:
        g, m, d = config['General'], config['Model'], config['Dataset']
        if g['MODEL_NAME'] not in ADAPTERS:
            raise ExecutionCheckError('adapter_missing: ' + str(g['MODEL_NAME']))
        number(g['seed'], 'seed', 0, 2**32-1, integer=True)
        number(g['num_classes'], 'num_classes', 2, 128, integer=True)
        number(g['num_epochs'], 'num_epochs', 1, integer=True)
        number(g['num_workers'], 'num_workers', 0, integer=True)
        number(m['in_dim'], 'in_dim', 1, 8192, integer=True)
        number(m['dropout'], 'dropout', 0, 1)
        if m['dropout'] == 1:
            raise ExecutionCheckError('dropout must be < 1; p=1 destroys the training signal')
        if m['act'] not in ('relu', 'gelu', 'leakyrelu', 'sigmoid', 'tanh', 'silu'):
            raise ExecutionCheckError('unsupported activation')
        allowed = {'in_dim', 'dropout', 'act', 'optimizer', 'scheduler', 'criterion'}
        if g['MODEL_NAME'] == 'AB_MIL':
            allowed |= {'L', 'D'}
            for key, default in [('L', 512), ('D', 128)]:
                number(m.get(key, default), key, 1, 2048, integer=True)
        if set(m) - allowed:
            raise ExecutionCheckError('unsupported Model fields: ' + ','.join(sorted(set(m)-allowed)))
        if m['criterion'] != 'ce':
            raise ExecutionCheckError('this adapter supports multiclass CE only')
        opt = m['optimizer']
        if opt['which'] not in ('adam', 'adamw'):
            raise ExecutionCheckError('unsupported optimizer')
        active = opt[opt['which'] + '_config']
        number(active['lr'], 'lr', 0)
        if active['lr'] == 0:
            raise ExecutionCheckError('lr must be positive')
        number(active['weight_decay'], 'weight_decay')
        if set(active) != {'lr', 'weight_decay'}:
            raise ExecutionCheckError('unsupported optimizer arguments')
        sch = m['scheduler']
        number(sch['warmup'], 'warmup', 0, integer=True)
        name = sch['which']
        if name not in ('none', 'step', 'multi_step', 'exponential', 'cosine'):
            raise ExecutionCheckError('unsupported scheduler')
        if name != 'none':
            s = sch[name + '_config']
            required = {'step': {'step_size','gamma'}, 'multi_step': {'milestones','gamma'},
                        'exponential': {'gamma'}, 'cosine': {'T_max','eta_min'}}[name]
            if set(s) != required:
                raise ExecutionCheckError('missing or unsupported scheduler arguments')
            if 'gamma' in s:
                number(s['gamma'], 'gamma', 0)
                if s['gamma'] == 0:
                    raise ExecutionCheckError('gamma must be positive')
            if name == 'step':
                number(s['step_size'], 'step_size', 1, integer=True)
            if name == 'multi_step':
                if not isinstance(s['milestones'], list) or not s['milestones']:
                    raise ExecutionCheckError('milestones must be a nonempty list')
                for milestone in s['milestones']:
                    number(milestone, 'milestone', 1, integer=True)
            if name == 'cosine':
                number(s['T_max'], 'T_max', 1, integer=True)
                number(s['eta_min'], 'eta_min')
        if not isinstance(d['dataset_csv_path'], str) or not Path(d['dataset_csv_path']).is_absolute():
            raise ExecutionCheckError('dataset_csv_path must be absolute')
        sampler = d['balanced_sampler']
        if type(sampler['use']) is not bool or type(sampler['replacement']) is not bool:
            raise ExecutionCheckError('balanced_sampler needs explicit booleans')
        # Required for the scientific selection protocol, even though preflight
        # cannot judge whether that protocol is appropriate for the research.
        if not isinstance(g['best_model_metric'], str) or not g['best_model_metric']:
            raise ExecutionCheckError('best_model_metric required')
        if type(g['earlystop']['use']) is not bool:
            raise ExecutionCheckError('earlystop.use must be boolean')
    except (KeyError, TypeError) as exc:
        raise ExecutionCheckError(f'missing or malformed explicit configuration: {exc}') from exc
    return copy.deepcopy(config)


def load_config(path):
    path = Path(path)
    if path.suffix.lower() == '.json':
        value = json.loads(path.read_text())
    else:
        import yaml
        value = yaml.safe_load(path.read_text())
    return validate_config(value)


def validate_trainval_csv(path, num_classes):
    """Check paired metadata, never open features or silently strip test rows."""
    counts = {'train': 0, 'val': 0, 'test': 0}
    seen = set()
    with Path(path).open(newline='') as stream:
        rows = csv.DictReader(stream)
        required = {f'{g}_{k}' for g in counts for k in ('slide_path', 'label')}
        if not required.issubset(rows.fieldnames or []):
            raise ExecutionCheckError('CSV needs paired train/val/test slide_path and label columns')
        if len(rows.fieldnames) != len(set(rows.fieldnames)):
            raise ExecutionCheckError('duplicate CSV column names')
        for index, row in enumerate(rows, 2):
            if None in row:
                raise ExecutionCheckError(f'malformed CSV row {index}')
            for group in counts:
                path_value = row.get(group + '_slide_path') or ''
                label_value = row.get(group + '_label') or ''
                if path_value != path_value.strip() or label_value != label_value.strip():
                    raise ExecutionCheckError(f'ambiguous whitespace at row {index}, {group}')
                if group == 'test' and (path_value or label_value):
                    raise ExecutionCheckError('test_data_present: use an Agent-created train/val-only manifest; no dummy test rows')
                if bool(path_value) != bool(label_value):
                    raise ExecutionCheckError(f'unpaired path/label at row {index}, {group}')
                if not path_value:
                    continue
                try:
                    label = float(label_value)
                    if not math.isfinite(label) or not label.is_integer() or not 0 <= label < num_classes:
                        raise ValueError()
                except ValueError as exc:
                    raise ExecutionCheckError(f'invalid class at row {index}, {group}') from exc
                feature = Path(path_value)
                if not feature.is_absolute():
                    raise ExecutionCheckError('feature paths must be absolute')
                # resolve catches cross-split aliases without opening the file.
                resolved = str(feature.resolve())
                if resolved in seen:
                    raise ExecutionCheckError(f'duplicate or overlapping feature at row {index}, {group}')
                seen.add(resolved)
                counts[group] += 1
    if not counts['train'] or not counts['val']:
        raise ExecutionCheckError('nonempty train and validation sets required')
    return {'pipeline': 'Train_Val', 'counts': counts, 'sha256': digest(path),
            'feature_contents_checked': False, 'patient_membership_checked': False}


def _namespace(value):
    return SimpleNamespace(**{k: _namespace(v) for k,v in value.items()}) if isinstance(value, dict) else value


def _vendor(root):
    root = Path(root).resolve()
    for name, module in list(sys.modules.items()):
        if name in ('utils', 'modules') or name.startswith(('utils.', 'modules.')):
            file = getattr(module, '__file__', None)
            locations = [Path(file)] if file else [Path(p) for p in getattr(module, '__path__', [])]
            if any(not p.resolve().is_relative_to(root) for p in locations):
                raise ExecutionCheckError('vendor import collision; use a fresh training process')
    if not (root/'utils/model_utils.py').is_file():
        raise ExecutionCheckError('MIL_BASELINE source root required')
    sys.dont_write_bytecode = True
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def source_binding(config, root):
    root = Path(root).resolve()
    module, _ = ADAPTERS[config['General']['MODEL_NAME']]
    files = [module.replace('.', '/')+'.py']
    files += [str(p.relative_to(root)) for p in sorted((root/'utils').glob('*.py'))]
    return {'vendor_root': str(root), 'vendor_sha256': {p: digest(root/p) for p in files},
            'adapter_sha256': digest(__file__),
            'sampling_environment': {k:v for k,v in os.environ.items() if k.startswith('AUTO_MIL_')}}


def build_components(config, vendor_root, device='cpu'):
    """Shared by preflight and training; seed/model/optimizer/loss/schedulers agree.

    Training callers use prepare_training() to bind this construction to a
    successful preflight. No training dataset or device is touched here.
    """
    config = validate_config(config)
    _vendor(vendor_root)
    import numpy as np
    import torch
    g, m = config['General'], config['Model']
    random.seed(g['seed']); np.random.seed(g['seed']); torch.manual_seed(g['seed'])
    torch.cuda.manual_seed_all(g['seed'])
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    module, name = ADAPTERS[g['MODEL_NAME']]
    factory = getattr(importlib.import_module(module), name)
    get_act = importlib.import_module('utils.process_utils').get_act
    kwargs = dict(in_dim=m['in_dim'], num_classes=g['num_classes'],
                  dropout=m['dropout'], act=get_act(m['act']))
    if name == 'AB_MIL':
        kwargs.update(L=m.get('L', 512), D=m.get('D', 128), rrt=None)
    model = factory(**kwargs).to(device)
    for layer in model.modules():
        if isinstance(layer, torch.nn.modules.dropout._DropoutNd):
            number(layer.p, 'effective dropout', 0, 1)
            if layer.p == 1:
                raise ExecutionCheckError('effective dropout is 1')
    utils = importlib.import_module('utils.model_utils')
    args = _namespace(config)
    optimizer, lr = utils.get_optimizer(args, model)
    scheduler, warmup = utils.get_scheduler(args, optimizer, lr)
    return SimpleNamespace(model=model, optimizer=optimizer, scheduler=scheduler,
                           warmup_scheduler=warmup, criterion=utils.get_criterion(m['criterion']),
                           generator=torch.Generator().manual_seed(g['seed']), config=config)


def probe_components(components):
    """Three CPU synthetic steps; bias-only or weight-decay-only updates fail."""
    import torch
    model, opt = components.model, components.optimizer
    model.cpu().train()
    matrices = {n:p for n,p in model.named_parameters() if p.requires_grad and p.ndim >= 2}
    if not matrices:
        raise ExecutionCheckError('no trainable weight matrices')
    stats = {n: {'gradient_max': 0.0, 'update_max': 0.0} for n in matrices}
    g, m = components.config['General'], components.config['Model']
    generator = torch.Generator().manual_seed(g['seed'])
    losses = []
    for step in range(3):
        x = torch.randn(1, 16, m['in_dim'], generator=generator)
        y = torch.tensor([step % g['num_classes']])
        before = {n:p.detach().clone() for n,p in matrices.items()}
        opt.zero_grad(set_to_none=True)
        logits = model(x)['logits']
        if logits.shape != (1, g['num_classes']) or not torch.isfinite(logits).all():
            raise ExecutionCheckError('invalid or nonfinite logits')
        loss = components.criterion(logits, y)
        if not torch.isfinite(loss):
            raise ExecutionCheckError('nonfinite loss')
        loss.backward()
        for n,p in matrices.items():
            if p.grad is not None:
                if not torch.isfinite(p.grad).all():
                    raise ExecutionCheckError('nonfinite gradient: ' + n)
                stats[n]['gradient_max'] = max(stats[n]['gradient_max'], p.grad.abs().max().item())
        opt.step()
        for n,p in matrices.items():
            if not torch.isfinite(p).all():
                raise ExecutionCheckError('nonfinite weight: ' + n)
            stats[n]['update_max'] = max(stats[n]['update_max'], (p.detach()-before[n]).abs().max().item())
        losses.append(loss.item())
    failed = [n for n,s in stats.items() if s['gradient_max'] == 0 or s['update_max'] == 0]
    return {'passed': not failed, 'steps': 3, 'losses': losses, 'weights': stats,
            'failed_weights': failed, 'scope': 'CPU synthetic; no real data or generalization claim'}


def preflight(config_path, vendor_root):
    import torch
    torch.set_num_threads(1)
    config = load_config(config_path)
    manifest = validate_trainval_csv(config['Dataset']['dataset_csv_path'], config['General']['num_classes'])
    binding = source_binding(config, vendor_root)
    components = build_components(config, vendor_root)
    probe = probe_components(components)
    if binding != source_binding(config, vendor_root):
        raise ExecutionCheckError('source changed during preflight')
    return {'schema_version': SCHEMA, 'status': 'passed' if probe['passed'] else 'failed',
            'config': config, 'config_sha256': digest(config_path), 'binding': binding,
            'manifest': manifest, 'trainability': probe, 'torch_version': str(torch.__version__),
            'training_authorized': False, 'scientific_approval': False}


def prepare_training(config_path, vendor_root, report_path, device='cpu'):
    """Fresh components only after checking the report against current inputs.

    This is a reproducibility guard, not a signed permission or OS sandbox.
    Callers must enforce study authorization, patient splits and compute budgets.
    """
    import torch
    config = load_config(config_path)
    report = json.loads(Path(report_path).read_text())
    manifest = validate_trainval_csv(config['Dataset']['dataset_csv_path'], config['General']['num_classes'])
    if (report.get('schema_version') != SCHEMA or report.get('status') != 'passed'
            or report.get('trainability', {}).get('passed') is not True):
        raise ExecutionCheckError('successful preflight required')
    if (report.get('config') != config or report.get('config_sha256') != digest(config_path)
            or report.get('binding') != source_binding(config, vendor_root)
            or report.get('manifest') != manifest or report.get('torch_version') != str(torch.__version__)):
        raise ExecutionCheckError('preflight stale: configuration, source, environment or manifest changed')
    return build_components(config, vendor_root, device=device)


def trainval_loaders(components):
    """Use paired train/val metadata, the configured sampler and seeded generator.

    Deliberately constructs no test dataset. Feature reads occur only when the
    caller iterates these loaders inside its authorized executor.
    """
    from torch.utils.data import DataLoader
    config = components.config
    g, d = config['General'], config['Dataset']
    validate_trainval_csv(d['dataset_csv_path'], g['num_classes'])
    dataset = importlib.import_module('utils.wsi_utils').WSI_Dataset
    train, val = dataset(d['dataset_csv_path'], 'train'), dataset(d['dataset_csv_path'], 'val')
    sampler = train.get_balanced_sampler(replacement=d['balanced_sampler']['replacement']) if d['balanced_sampler']['use'] else None
    return (
        DataLoader(train, batch_size=1, num_workers=g['num_workers'], generator=components.generator,
                   sampler=sampler, shuffle=sampler is None),
        DataLoader(val, batch_size=1, num_workers=g['num_workers'], shuffle=False),
    )


def train_epoch(components, loader, device, epoch):
    """One-based epoch; reuse upstream loop and its once-per-epoch scheduler step."""
    number(epoch, 'epoch', 1, components.config['General']['num_epochs'], integer=True)
    scheduler = (components.warmup_scheduler if epoch <= components.config['Model']['scheduler']['warmup']
                 else components.scheduler)
    return importlib.import_module('utils.loop_utils').train_loop(
        device, components.model, loader, components.criterion, components.optimizer, scheduler)


def validate_epoch(components, validation_loader, device):
    return importlib.import_module('utils.loop_utils').val_loop(
        device, components.config['General']['num_classes'], components.model,
        validation_loader, components.criterion)


def configuration_diff(left, right, prefix=''):
    """Show all changes, including optimizer/scheduler/sampling, not just model name."""
    if isinstance(left, dict) and isinstance(right, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            path = f'{prefix}.{key}' if prefix else key
            if key not in left or key not in right:
                result.append({'field': path, 'left': left.get(key), 'right': right.get(key)})
            else:
                result.extend(configuration_diff(left[key], right[key], path))
        return result
    return [] if type(left) is type(right) and left == right else [{'field': prefix, 'left': left, 'right': right}]
