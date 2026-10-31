import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

def helper(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'skills/benchmark-design/scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def plan(tmp_path):
    (tmp_path / 'inventory.json').write_text('{}')
    (tmp_path / 'search.md').write_text('fixture')
    candidate = dict(name='Fixture method', year=2025, paper_url='https://example.org/paper', code_url=None,
                     reason='Task-relevant reference', task_fit='Same input and endpoint', input_requirements='Feature bags',
                     local_status='structural_complete', executor_status='needs_adaptation', implementation_gap='Adapter required',
                     comparison_track='fixed_features', source_checked='paper', decision='select',
                     paper_access='full_text', code_access='not_checked', evidence_notes='Fixture methods section')
    return dict(schema_version='pathoreason.benchmark-plan/1', objective='Fixture comparison', as_of='2026-01-01', recent_from_year=2023,
                inventory_ref='inventory.json', search_log_ref='search.md',
                searches=[dict(query=q, accessed_at='2026-01-01', source='fixture', urls=['https://example.org']) for q in ('methods', 'comparisons')],
                candidates=[dict(candidate, id='a', role='classic'), dict(candidate, id='b', role='recent')],
                fairness={k: 'Fixture policy' for k in ('patient_split', 'feature_policy', 'tuning_policy', 'sampling_policy', 'held_out_policy')},
                matrix=dict(model_ids=['a', 'b'], folds=5, seeds=[17, 23], settings_per_model=1, cv_runs=20, final_fit_runs=4, total_fit_runs=24),
                split_counts=dict(cohort=100, development=80, locked_test=20, cv_oof=[16]*5), training_authorized=False)

def test_structure_does_not_claim_execution_readiness(tmp_path):
    value = plan(tmp_path)
    result = helper('check_plan').check(value, tmp_path)
    assert result['structure_valid'] and len(result['warnings']) == 2
    value['candidates'][1].update(source_checked='abstract_only', paper_access='abstract_only')
    result = helper('check_plan').check(value, tmp_path)
    assert 'original paper' in ' '.join(result['warnings'])
    assert result['structure_valid'] and not result['source_review_complete']

@pytest.mark.parametrize('mutation,expected', [
    (lambda p: p['matrix'].update(cv_runs=10), 'arithmetic'),
    (lambda p: p['matrix'].update(model_ids=['a']), 'matrix models'),
    (lambda p: p['split_counts'].update(cv_oof=[15]*5), 'OOF fold sizes'),
    (lambda p: p['split_counts'].update(cohort=99), 'cohort arithmetic'),
    (lambda p: p.update(training_authorized=True), 'authorize training'),
    (lambda p: p['candidates'][1].update(year=2020), 'recent window'),
    (lambda p: p['candidates'][0].update(executor_status='validated'), 'status conflict'),
    (lambda p: p.update(inventory_ref='../other.json'), 'inventory_ref'),
    (lambda p: p['candidates'][0].update(paper_access='abstract_only'), 'requires full text'),
    (lambda p: p['candidates'][0].update(source_checked='paper_and_code', code_access='repository_page', code_url='https://example.org/repo'), 'requires source files'),
])
def test_inconsistent_plan_rejected(tmp_path, mutation, expected):
    value = plan(tmp_path)
    mutation(value)
    result = helper('check_plan').check(value, tmp_path)
    assert not result['structure_valid'] and expected in ' '.join(result['errors'])

def test_reference_symlink_escape_rejected(tmp_path):
    outside = tmp_path / 'outside'
    outside.write_text('{}')
    workspace = tmp_path / 'study'
    workspace.mkdir()
    (workspace / 'ref').symlink_to(outside)
    with pytest.raises(ValueError):
        helper('check_plan').local_file(workspace, 'ref')

def test_inventory_never_imports_or_claims_trainable(tmp_path):
    library = tmp_path / 'engines/auto_mil/third_party/MIL_BASELINE'
    for directory in ('configs', 'modules/complete', 'process/complete', 'modules/partial'):
        (library / directory).mkdir(parents=True)
    (library / 'configs/complete.yaml').write_text('model: complete')
    (library / 'modules/complete/__init__.py').write_text('raise RuntimeError("must not import")')
    result = helper('method_inventory').inventory(tmp_path)
    entries = {m['id']: m for m in result['methods']}
    assert entries['complete']['local_status'] == 'structural_complete'
    assert entries['partial']['local_status'] == 'partial'
    assert all(m['executor_status'] == 'unknown' for m in result['methods'])
    assert not helper('method_inventory').inventory(tmp_path / 'missing')['library_exists']

def test_catalog_navigation_and_network_permission_binding():
    from pathoreason.formal import project_skills
    from pathoreason.contracts import SkillDefinition
    from pathoreason.permission_settings import PermissionSettings, formal_rules
    skills = {s['id']: s for s in project_skills(True)}
    SkillDefinition.model_validate(skills['benchmark-design'])
    assert len(skills['benchmark-design']['instruction_refs']) == 7
    nav = json.loads((ROOT / 'config/skill-navigation.json').read_text())
    assert 'benchmark-design' in nav[0]['stages'][1]['skill_ids']
    for mode in ('ask', 'auto', 'custom'):
        for value in ('allow', 'ask', 'deny'):
            rules = formal_rules('/workspace', PermissionSettings(mode=mode, webfetch=value))
            network = {r['permission']: r['action'] for r in rules if r['permission'] in ('webfetch', 'websearch')}
            assert network['webfetch'] == network['websearch']
            if value == 'deny':
                assert network['websearch'] == 'deny'


def pdf_fixture():
    import io
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 20 100 Td (Fixture research method) Tj ET')
    page[NameObject('/Contents')] = stream
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def response(data):
    import io
    class Response(io.BytesIO):
        status = 200
        def geturl(self):
            return 'https://example.org/paper.pdf'
    return lambda *a, **k: Response(data)


def test_pdf_retrieval_extracts_text_and_preserves_receipts(tmp_path):
    module = helper('fetch_paper')
    result = module.retrieve(tmp_path, 'https://example.org/paper.pdf', 'plans/source-v1', opener=response(pdf_fixture()))
    assert result['state'] == 'text_extracted' and result['pages'] == 1
    assert result['scientific_verification'] is False
    assert 'Fixture research method' in (tmp_path / 'plans/source-v1/text.txt').read_text()
    assert len(result['pdf_sha256']) == 64 and len(result['text_sha256']) == 64
    with pytest.raises(FileExistsError):
        module.retrieve(tmp_path, 'https://example.org/paper.pdf', 'plans/source-v1', opener=response(pdf_fixture()))


def test_pdf_failure_bounds_and_non_pdf_response(tmp_path):
    module = helper('fetch_paper')
    with pytest.raises(ValueError, match='not a PDF'):
        module.retrieve(tmp_path, 'https://example.org/paper.pdf', 'plans/html', opener=response(b'<html>not a PDF</html>'))
    with pytest.raises(ValueError, match='size cap'):
        module.retrieve(tmp_path, 'https://example.org/paper.pdf', 'plans/large', max_bytes=10, opener=response(b'x' * 20))
    import time
    class SlowBody:
        status = 200
        def geturl(self): return 'https://example.org/paper.pdf'
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, count): time.sleep(2)
    def slow(*a, **k):
        return SlowBody()
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        module.retrieve(tmp_path, 'https://example.org/paper.pdf', 'plans/slow', timeout=.05, opener=slow)
    assert time.monotonic() - started < 1
    assert json.loads((tmp_path / 'plans/slow/receipt.json').read_text())['state'] == 'failed'
    assert not (tmp_path / 'plans/slow/text.txt').exists()
    with pytest.raises(ValueError):
        module.destination(tmp_path, '../outside')


def holdout_plan(tmp_path):
    value = plan(tmp_path)
    value['schema_version'] = 'pathoreason.benchmark-plan/2'
    value['validation'] = dict(method='holdout', fixed_split=True, split_seed=71,
                               group_unit='patient', stratification='class label', split_status='proposed',
                               split_manifest_ref=None, split_manifest_sha256=None)
    value['matrix'].update(folds=0, cv_runs=0, final_fit_runs=4, total_fit_runs=4, test_inference_runs=4)
    value['split_counts'] = dict(cohort=100, development=80, locked_test=20, train=64, validation=16)
    return value


def test_holdout_keeps_training_seeds_separate_from_one_split(tmp_path):
    value = holdout_plan(tmp_path)
    value['matrix'].update(seeds=[11, 23, 37], settings_per_model=2,
                           final_fit_runs=12, total_fit_runs=12, test_inference_runs=12)
    before = copy.deepcopy(value)
    result = helper('check_plan').check(value, tmp_path)
    assert result['structure_valid'] and result['validation_method'] == 'holdout'
    assert value == before
    assert len(result['warnings']) == 2  # Execution is still unvalidated.


@pytest.mark.parametrize('mutation,expected', [
    (lambda p: p['matrix'].update(folds=1), 'one-fold CV'),
    (lambda p: p['matrix'].update(cv_runs=4, total_fit_runs=8), 'holdout cv_runs'),
    (lambda p: p['matrix'].update(final_fit_runs=8, total_fit_runs=8), 'holdout final_fit_runs'),
    (lambda p: p['matrix'].update(test_inference_runs=8), 'test_inference_runs'),
    (lambda p: p['split_counts'].update(validation=15), 'train + validation'),
    (lambda p: p['split_counts'].update(cv_oof=[16]*5), 'must not contain CV'),
    (lambda p: p['split_counts'].update(final_train=70), 'conflicting count'),
    (lambda p: p['validation'].update(split_seed=[11, 23]), 'split_seed'),
    (lambda p: p['validation'].update(fixed_split=False), 'fixed_split'),
    (lambda p: p['validation'].update(method='repeated_holdout'), 'validation.method'),
    (lambda p: p['validation'].update(split_status='frozen'), 'split manifest'),
    (lambda p: p.pop('validation'), 'validation.method'),
    (lambda p: p.update(schema_version='pathoreason.benchmark-plan/1'), 'requires benchmark-plan/2'),
])
def test_invalid_holdout_does_not_pass_as_cv(tmp_path, mutation, expected):
    value = holdout_plan(tmp_path)
    mutation(value)
    result = helper('check_plan').check(value, tmp_path)
    assert not result['structure_valid'] and expected in ' '.join(result['errors'])


def test_frozen_split_requires_unchanged_manifest(tmp_path):
    import hashlib
    value = holdout_plan(tmp_path)
    path = tmp_path / 'split.json'
    path.write_text('{"fixture": true}')
    value['validation'].update(split_status='frozen', split_manifest_ref='split.json',
                               split_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert helper('check_plan').check(value, tmp_path)['structure_valid']
    path.write_text('{"fixture": "changed"}')
    result = helper('check_plan').check(value, tmp_path)
    assert not result['structure_valid'] and 'SHA256' in ' '.join(result['errors'])
    value['validation']['split_manifest_ref'] = '../outside'
    assert not helper('check_plan').check(value, tmp_path)['structure_valid']


def test_cv_versions_remain_readable_without_rewriting(tmp_path):
    original = plan(tmp_path)
    before = copy.deepcopy(original)
    assert helper('check_plan').check(original, tmp_path)['structure_valid']
    assert original == before
    modern = copy.deepcopy(original)
    modern['schema_version'] = 'pathoreason.benchmark-plan/2'
    modern['validation'] = holdout_plan(tmp_path)['validation']
    modern['validation']['method'] = 'cross_validation'
    modern['matrix']['test_inference_runs'] = modern['matrix']['final_fit_runs']
    assert helper('check_plan').check(modern, tmp_path)['structure_valid']
    modern['matrix'].update(folds=1, cv_runs=4, total_fit_runs=8)
    modern['split_counts']['cv_oof'] = [80]
    assert not helper('check_plan').check(modern, tmp_path)['structure_valid']
