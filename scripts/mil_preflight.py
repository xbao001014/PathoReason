"""CPU-only, time-bounded readiness check. Never launches a research experiment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.mil_execution import SCHEMA, configuration_diff, load_config, preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--vendor-root', required=True)
    parser.add_argument('--report', required=True, help='new JSON path; never overwritten')
    parser.add_argument('--reference-config', help='optional previous config to compare; never changed')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            result = preflight(args.config, args.vendor_root)
            if args.reference_config:
                differences = configuration_diff(load_config(args.reference_config), result['config'])
                result['alignment'] = {'config_equal': not differences, 'differences': differences,
                                       'data_and_training_behavior_verified': False}
        except Exception as exc:
            result = {'schema_version': SCHEMA, 'status': 'failed',
                      'error': f'{type(exc).__name__}: {exc}', 'training_authorized': False}
        print(json.dumps(result, allow_nan=False))
        return 0
    # Reserve before any work. Failed checks have their own immutable report too.
    with Path(args.report).open('x') as stream:
        json.dump({'schema_version': SCHEMA, 'status': 'running'}, stream)
        stream.flush()
        env = dict(os.environ, CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1',
                   OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
        command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], '--worker']
        try:
            run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
            if run.returncode:
                raise RuntimeError('preflight worker exited ' + str(run.returncode) + ': ' + run.stderr[-1600:])
            result = json.loads(run.stdout.strip().splitlines()[-1])
        except (subprocess.TimeoutExpired, RuntimeError, ValueError, IndexError) as exc:
            result = {'schema_version': SCHEMA, 'status': 'failed', 'error': str(exc),
                      'training_authorized': False}
        stream.seek(0); stream.truncate()
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({'status': result['status'], 'report': str(Path(args.report).resolve()),
                      'error': result.get('error')}, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
