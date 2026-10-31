"""Read-only structural inventory; never imports or runs library implementations."""
import argparse
import hashlib
import json
from pathlib import Path


def inventory(root):
    root = Path(root).resolve()
    library = root / 'engines/auto_mil/third_party/MIL_BASELINE'
    names = set()
    for section in ('modules', 'process'):
        names.update(p.name for p in (library / section).glob('*')
                     if p.is_dir() and not p.name.startswith(('.', '_')))
    names.update(p.stem for p in (library / 'configs').glob('*.yaml'))
    methods = []
    for name in sorted(names):
        paths = {'config': library / 'configs' / (name + '.yaml'),
                 'module': library / 'modules' / name,
                 'process': library / 'process' / name}
        present = {k: p.exists() for k, p in paths.items()}
        methods.append({'id': name, 'paths': {k: str(p) for k, p in paths.items()},
                        'present': present,
                        'local_status': 'structural_complete' if all(present.values()) else 'partial',
                        'executor_status': 'unknown', 'input_compatibility': 'unknown'})
    sources = []
    for relative in ('engines/auto_mil/auto_mil/baseline_registry.py',
                     'engines/auto_mil/MIL_methods_overview.md',
                     'packages/core/experiment_agent/task_capabilities.py',
                     'packages/core/experiment_agent/method_engines/auto_mil_gates.py'):
        path = root / relative
        sources.append({'path': str(path), 'exists': path.is_file(),
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None})
    return {'schema_version': 'pathoreason.method-inventory/1', 'root': str(root),
            'library_exists': library.is_dir(), 'methods': methods, 'sources': sources,
            'summary_directory': str(root / 'engines/auto_mil/method_summaries'),
            'scope': 'Structural file presence only; no imports, execution, dependency or gate validation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/home/bxn/projects/auto-research')
    args = parser.parse_args()
    result = inventory(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['library_exists'] else 1)
