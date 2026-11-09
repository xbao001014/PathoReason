import copy
import json
import pytest
from pathoreason.research_workbench import build_projection
from pathoreason.legacy_workbench import legacy_outcomes


def evidence():
    files={'conclusion':'conclusion.json','pipeline':'pipeline.json','matrix':'results-data.json',
           'cells':'cell_metrics.csv','performance':'performance.csv','paper':'manuscript.md',
           'pdf':'CESC_manuscript.pdf','figure':'method.png','checklist':'AUTHOR_CHECKLIST.json'}
    arts=[{'id':aid,'project_id':'p','title':aid,'relative_path':'archive/'+name,'sha256':aid[0]*64,
           'media_type':'application/json','size_bytes':100,'kind':'report',
           'source_ref':{'adapter':'auto_research.evidence_file','resource_id':'archive/'+name}}
          for aid,name in files.items()]
    cells=[{'round':r,'condition':c,'fold':f,'seed':7,'best_epoch':3,'val_rmse':float(f)/10,'val_mae':float(f)/20}
           for r in ['A','B'] for c in ['raw','instance'] for f in [1,2]]
    performance=[{'round':r,'condition':c,'n_cells':2,'mean_fold_seed_rmse':.15,'mean_fold_seed_mae_at_rmse_selected_epoch':.075}
                 for r in ['A','B'] for c in ['raw','instance']]
    docs={'conclusion':{'schema_version':'cesc-study-conclusions/1','headline':'Measured improvement, incomplete goal',
                       'conclusions':['registered interval includes zero'],'limits':['development only'],
                       'goal_achieved_dev':False,'execution':{'patients':18},'private_patient_rows':['NEVER_EXPOSE']},
          'pipeline':{'schema':'cesc-manuscript-delivery/2','status':'review_delivery_ready','submission_ready':False,'author_approved_exact_artifacts':False},
          'matrix':{'performance':performance,'cells':cells,'exploration':[],
                    'sources':[{'path':'archive/'+files[aid],'sha256':aid[0]*64} for aid in ['cells','performance']]},
          'cells':{'_legacy_csv':copy.deepcopy(cells)},'performance':{'_legacy_csv':copy.deepcopy(performance)},
          'checklist':{'pending':['final author check']}}
    return arts,docs


def test_legacy_uses_current_workbench_without_inventing_approvals_or_tasks():
    arts,docs=evidence();original=copy.deepcopy((arts,docs))
    result=build_projection('p',arts,docs,[])
    outcome=result['outcomes']
    assert result['default_task_id']=='project_outcomes'
    assert result['execution_authority'] is False
    assert outcome['origin']=='legacy_archive' and outcome['pending'] is None
    assert outcome['source_goal_achieved'] is False and outcome['submission_ready'] is False
    assert len(outcome['legacy_matrix']['cells'])==8
    assert outcome['legacy_matrix']['patients']==18
    assert outcome['key_findings']==['registered interval includes zero']
    assert outcome['content']['conversation_id'] is None
    assert all(t['kind']!='registered_task' for t in result['tasks'])
    assert 'NEVER_EXPOSE' not in json.dumps(result)
    assert (arts,docs)==original


@pytest.mark.parametrize('cause',['mean','duplicate','source_hash','csv','missing_csv','missing_matrix','foreign_source'])
def test_unverified_matrix_not_projected(cause):
    arts,docs=evidence()
    if cause=='mean':docs['matrix']['performance'][0]['mean_fold_seed_rmse']=.9
    if cause=='duplicate':docs['matrix']['cells'].append(docs['matrix']['cells'][0])
    if cause=='source_hash':docs['matrix']['sources'][0]['sha256']='bad'
    if cause=='csv':docs['cells']['_legacy_csv'][0]['val_rmse']=.8
    if cause=='missing_csv':docs.pop('cells')
    if cause=='missing_matrix':docs.pop('matrix')
    if cause=='foreign_source':next(a for a in arts if a['id']=='cells')['project_id']='other'
    outcome,_,notices=legacy_outcomes('p',arts,docs)
    assert outcome['legacy_matrix'] is None and notices
    assert outcome['content'] and outcome['source_goal_achieved'] is False


def test_ambiguous_or_unknown_legacy_does_not_override_platform():
    arts,docs=evidence();duplicate={**arts[1],'id':'pipeline2'}
    docs['pipeline2']=docs['pipeline'];assert legacy_outcomes('p',[*arts,duplicate],docs)[0] is None
    docs['pipeline']['schema']='unsupported/1';assert legacy_outcomes('p',arts,docs)[0] is None
    arts,docs=evidence()
    r={'project_id':'p','stage_id':'analysis','status':'active','revision':1}
    out=build_projection('p',arts,docs,[],research=r)['outcomes']
    assert out['stage_id']=='analysis' and out.get('origin')!='legacy_archive'
