import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from pathoreason.research_workbench import build_projection, project_snapshot, view_id
from pathoreason.study_io import publish_artifact
from test_p1_service import fixture
from test_p5_entry import study


def artifact(name, path, media='application/json'):
    return dict(id=name,title=name,project_id='p',media_type=media,size_bytes=100,sha256='a'*64,
                source_ref={'resource_id':path},stage_ref=None,run_ref=None)


def plan(models=None):
    return dict(schema_version='pathoreason.benchmark-plan/2',objective='示例任务：患者级比较',
                matrix={'model_ids':models or ['MEAN_MIL','MAX_MIL'],'seeds':[11,12],'total_fit_runs':4,'folds':0},
                validation={'method':'holdout','split_status':'frozen'},training_authorized=True)


def turn(tid,ids,cid='c',status='completed'):
    return dict(id=tid,conversation_id=cid,created_at='2026-11-01T10:00:'+tid[-2:]+'Z',
                user_text='请修改比较方案',text=' '.join('[结果](artifact:'+x+')' for x in ids),status=status)


def test_projection_is_derived_not_authorization_and_preserves_sources():
    arts=[artifact('a','outputs/plan-v1.json'),artifact('b','outputs/plan-v2.json'),artifact('r','outputs/results-v1.json')]
    docs={'a':plan(),'b':{**plan(['MEAN_MIL']),'change_summary':'缩减模型'},'r':{
        'schema_version':'pathoreason.block-results/1','results':[{'model':'MEAN_MIL','seed':11,'val_best':.8,'test':{'macro_auc':.7,'patient_id':'private'}}]}}
    before=copy.deepcopy((arts,docs))
    out=build_projection('p',arts,docs,[turn('t01',['a']),turn('t02',['b']),turn('t03',['r'])])
    task=next(t for t in out['tasks'] if t['id']==out['default_task_id'])
    assert task['execution_state']=='unknown' and out['execution_authority'] is False
    assert task['plan']['adoption_status']=='unknown'
    assert task['reported_results'][0]['state']=='reported'
    assert task['reported_results'][0]['test']=={'macro_auc':.7}
    assert all(s['status']=='unknown' for s in task['stages'])
    assert next(f for f in out['families'] if f['stage_id']=='plan')['versions'][0]['diff'][0]['field']=='比较模型'
    assert (arts,docs)==before


def test_episodes_never_cross_conversations_or_ambiguous_plan_citations():
    arts=[artifact('a','outputs/first-v1.json'),artifact('b','outputs/second-v1.json'),artifact('x','outputs/other.json'),artifact('y','outputs/ambiguous.json')]
    out=build_projection('p',arts,{'a':plan(),'b':plan()},[turn('t01',['a']),turn('t02',['x'],'different'),turn('t03',['a','b']),turn('t04',['y'])])
    assert all(next(f for f in out['families'] if f['versions'][0]['artifacts'][0]['id']==aid)['task_id']=='shared' for aid in ['x','y'])


def test_repeated_citation_does_not_replace_first_visible_turn():
    a=artifact('a','outputs/plan-v1.json')
    out=build_projection('p',[a],{'a':plan()},[turn('t01',['a']),turn('t02',['a'])])
    assert out['families'][0]['versions'][0]['turn']['id']=='t01'


def test_file_formats_and_versions_do_not_duplicate_reports():
    arts=[artifact('a','outputs/plan-v1.json'),artifact('r1','outputs/block-v1.json'),artifact('m','outputs/block-v1.md','text/markdown'),artifact('r2','outputs/block-v2.json')]
    result={'schema_version':'pathoreason.block-results/1','results':[{'model':'MEAN_MIL','seed':11,'val_best':.7}]}
    out=build_projection('p',arts,{'a':plan(),'r1':result,'r2':result},[turn('t01',['a']),turn('t02',['r1','m']),turn('t03',['r2'])])
    task=next(t for t in out['tasks'] if t['id']==out['default_task_id'])
    assert len(task['reported_results'])==1
    family=next(f for f in out['families'] if f['stage_id']=='baseline')
    assert len(family['versions'])==2 and len(family['versions'][1]['artifacts'])==2


def test_shared_dependencies_are_not_exclusive():
    arts=[artifact('d','outputs/inventory.json'),artifact('a','outputs/first-v1.json'),artifact('b','outputs/second-v1.json')]
    doc={**plan(),'inventory_ref':'outputs/inventory.json'}
    out=build_projection('p',arts,{'a':doc,'b':doc},[turn('t01',['a','d']),turn('t02',['b'])])
    assert next(f for f in out['families'] if f['versions'][0]['artifacts'][0]['id']=='d')['task_id']=='shared'


def test_bad_manifest_is_atomic_and_cannot_reference_another_project():
    arts=[artifact('a','outputs/plan-v1.json'),artifact('m','outputs/manifest.json')]
    tid=view_id('p:outputs/plan')
    manifest={'schema_version':'pathoreason.workbench-manifest/1','task_id':tid,'links':[
        {'artifact_id':'a','stage_id':'innovation','family_id':'bad','revision':'1'},
        {'artifact_id':'foreign','stage_id':'data','family_id':'bad','revision':'1'}]}
    out=build_projection('p',arts,{'a':plan(),'m':manifest},[])
    assert out['notices'] and next(f for f in out['families'] if f['versions'][0]['artifacts'][0]['id']=='a')['stage_id']=='plan'


def test_valid_manifest_uses_registered_task_without_granting_execution():
    arts=[artifact('a','outputs/plan-v1.json'),artifact('m','outputs/manifest.json')]
    task={'id':'task_one','objective':'正式登记任务','revision':2}
    manifest={'schema_version':'pathoreason.workbench-manifest/1','task_id':'task_one','links':[
        {'artifact_id':'a','stage_id':'plan','family_id':'comparison','revision':'2'}]}
    out=build_projection('p',arts,{'a':plan(),'m':manifest},[],[task])
    selected=next(t for t in out['tasks'] if t['id']=='task_one')
    assert selected['plan']['fits']==4 and selected['code_revision']==2
    assert out['default_task_id']=='task_one' and selected['execution_state']=='unknown'


def test_innovation_is_real_structured_evidence_with_preserved_revisions():
    arts=[artifact('a','outputs/plan-v1.json'),artifact('i1','outputs/innovation-v1.json'),artifact('i2','outputs/innovation-v2.json')]
    tid=view_id('p:outputs/plan')
    prop=dict(schema_version='pathoreason.innovation-proposal/1',proposal_id='candidate',task_id=tid,revision='1',title='候选模块',hypothesis='可检验的假设',decision='proposed')
    out=build_projection('p',arts,{'a':plan(),'i1':prop,'i2':{**prop,'revision':'2','decision':'rejected'}},[])
    task=next(t for t in out['tasks'] if t['id']==tid)
    assert [x['decision'] for x in task['innovations']]==['proposed','rejected']
    assert all(x['source_type']=='artifact_report' for x in task['innovations'])
    assert task['execution_state']=='unknown'


@pytest.mark.parametrize('field,value',[('task_id','foreign'),('evidence_artifact_ids',['foreign'])])
def test_invalid_innovation_is_not_invented(field,value):
    a=artifact('i','outputs/innovation.json')
    doc=dict(schema_version='pathoreason.innovation-proposal/1',proposal_id='p',task_id='shared',revision='1',title='X',hypothesis='Y')
    out=build_projection('p',[a],{'i':{**doc,field:value}},[])
    assert out['notices'] and not any(t['innovations'] for t in out['tasks'])


def test_report_without_matrix_and_malformed_results_stays_unknown():
    arts=[artifact('r','outputs/report.json')]
    out=build_projection('p',arts,{'r':{'schema_version':'pathoreason.block-results/1','results':None}},[])
    assert out['tasks'][0]['plan'] is None and out['tasks'][0]['reported_results']==[]


def test_current_activity_does_not_claim_training_and_revision_is_stable():
    t=turn('t01',[],status='running')
    a=build_projection('p',[],{},[t]);b=build_projection('p',[],{},[t])
    assert a['revision']==b['revision'] and a['activity'][0]['status']=='running'
    assert a['tasks'][0]['execution_state']=='unknown'


def test_snapshot_checks_source_bytes_and_does_not_write_research(fixture):
    s,_,_,_=fixture;v=study(s);root=__import__('pathlib').Path(v.workspace)
    path=root/'outputs/plan-v1.json';path.write_text(json.dumps(plan()))
    artifact=publish_artifact(s,v.project_id,'outputs/plan-v1.json','方案')
    with s.store.connect() as db:before=[tuple(x) for x in db.execute('SELECT * FROM artifacts')]
    original=path.read_bytes();first=project_snapshot(s,v.project_id)
    assert first['families'] and path.read_bytes()==original
    with s.store.connect() as db:assert before==[tuple(x) for x in db.execute('SELECT * FROM artifacts')]
    published=s.data/'artifacts'/artifact.relative_path;published.write_text('tampered')
    second=project_snapshot(s,v.project_id)
    assert second['notices'] and second['tasks'][0]['plan'] is None


def test_oversize_structured_artifact_is_not_read(fixture):
    s,_,_,_=fixture;v=study(s);a=artifact('big','outputs/big.json');a['project_id']=v.project_id;a['size_bytes']=3*1024*1024
    with s.store.connect(True) as db:db.execute('INSERT INTO artifacts VALUES(?,?,?)',('big',v.project_id,json.dumps(a)))
    s.artifact_bytes=lambda _:pytest.fail('oversized content opened')
    assert project_snapshot(s,v.project_id)['notices']
