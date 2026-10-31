"""Launch with a turn's frozen device binding; never change a running job."""
import json
import os
from pathlib import Path
import sqlite3
from .contracts import canonical_digest
from .gpu_settings import GpuBinding, checked_compute
from .hardware import gpu_inventory
from .persistence import Conflict


def execution_environment(config, turn_id, base_environment=None):
    root = Path(config['data_root'])
    with sqlite3.connect('file:'+str(root/'state/pathoreason.sqlite3')+'?mode=ro', uri=True) as db:
        row = db.execute('SELECT t.status,t.document,r.document FROM turns t JOIN runtime_configs r ON r.digest=json_extract(t.document,\'$.config_digest\') WHERE t.id=?', (turn_id,)).fetchone()
    if not row or row[0] != 'running':
        raise Conflict('compute_turn_not_running')
    turn, frozen = json.loads(row[1]), json.loads(row[2])
    if canonical_digest(frozen) != turn['config_digest']:
        raise Conflict('runtime_configuration_changed')
    if frozen.get('execution_mode') != 'research' or not frozen.get('gpu_binding'):
        raise Conflict('gpu_binding_required')
    binding = GpuBinding.model_validate(frozen['gpu_binding'])
    compute = checked_compute(binding.compute_path, root/'runtime/compute-bindings', binding.compute_sha256)
    gpu = next((g for g in gpu_inventory() if g.uuid == binding.gpu_uuid), None)
    if not gpu:
        raise Conflict('gpu_not_found')
    if gpu.index != binding.gpu_index or compute['gpu'].get('uuid') != gpu.uuid or compute['gpu'].get('index') != gpu.index:
        raise Conflict('gpu_mapping_changed_reselect')
    env = dict(os.environ if base_environment is None else base_environment)
    env.update(CUDA_VISIBLE_DEVICES=gpu.uuid, AUTORESEARCH_COMPUTE_CONFIG=binding.compute_path, PYTHONDONTWRITEBYTECODE='1')
    return env
