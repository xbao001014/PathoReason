import copy
import pytest
from pathoreason.training_costs import summarize


def projection():
    units=[{'id':name,'phase':'fit','parameters':{'model':'example','seed':seed,
             'epochs':30,'early_stop_patience':stop}} for name,seed,stop in [('a',1,0),('b',2,0),('c',1,5)]]
    attempts=[{'id':name,'unit_id':name,'phase':'fit','status':'completed','charged':True,
               'current_scope':True,'elapsed_seconds':elapsed} for name,elapsed in [('a',100),('b',120),('c',40)]]
    return {'schema_version':'pathoreason.training-progress/1','project_id':'fixture',
            'experiments':[{'id':'experiment','status':'completed','plan':{'environment_id':'env'},
             'units':units,'attempts':attempts,'used_wall_seconds':260,'used_gpu_seconds':None}]}


def test_does_not_mix_early_stopping_or_failures_with_full_fits():
    p=projection();e=p['experiments'][0]
    e['attempts'].append({**e['attempts'][0],'id':'failed','status':'failed','elapsed_seconds':20})
    result=summarize(p)['experiments'][0]
    groups=result['completed_groups']
    assert len(groups)==2
    assert groups[0]['statistics']['mean_seconds']==110
    assert groups[0]['statistics']['median_seconds']==110
    assert groups[0]['statistics']['min_seconds']==100
    assert groups[1]['statistics']['mean_seconds']==40
    assert result['failed_elapsed_statistics']['observed_sum_seconds']==20
    assert result['ledger_used_wall_seconds']==260  # never rewrites the ledger
    assert result['ledger_used_gpu_seconds'] is None


@pytest.mark.parametrize('value',[None,float('nan'),float('inf'),-1,True])
def test_unknown_or_invalid_times_are_not_zero(value):
    p=projection();p['experiments'][0]['attempts'][0]['elapsed_seconds']=value
    g=summarize(p)['experiments'][0]['completed_groups'][0]['statistics']
    assert g['measured_count']==1 and g['unknown_count']==1 and g['mean_seconds']==120


def test_stale_unsettled_and_other_phase_receipts_are_not_pooled():
    p=projection();e=p['experiments'][0]
    for name,patch in [('stale',{'current_scope':False}),('unsettled',{'charged':False}),('phase',{'phase':'evaluate'})]:
        e['attempts'].append({**e['attempts'][0],'id':name,**patch})
    before=copy.deepcopy(p)
    result=summarize(p)['experiments'][0]
    assert len(result['excluded_from_completed_groups'])==3
    assert result['completed_groups'][0]['statistics']['attempt_count']==2
    assert p==before


def test_duplicate_receipt_rejected():
    p=projection();e=p['experiments'][0];e['attempts'].append(dict(e['attempts'][0]))
    with pytest.raises(ValueError,match='duplicate_attempt'):summarize(p)


def test_empty_experiment_keeps_unknown_measurement():
    p=projection();e=p['experiments'][0];e['attempts']=[]
    result=summarize(p)['experiments'][0]
    assert result['completed_groups']==[]
    assert result['failed_elapsed_statistics']['observed_sum_seconds'] is None


def test_evaluation_groups_inherit_parent_fit_parameters():
    p=projection();e=p['experiments'][0];e['attempts']=[]
    for name,parent in [('eval_a','a'),('eval_c','c')]:
        e['units'].append({'id':name,'phase':'evaluate','parameters':{'model':'example'},'depends_on':[parent]})
        e['attempts'].append({'id':name,'unit_id':name,'phase':'evaluate','status':'completed',
                              'charged':True,'current_scope':True,'elapsed_seconds':10})
    groups=summarize(p)['experiments'][0]['completed_groups']
    assert len(groups)==2
    assert {g['dependency_parameters'][0]['parameters']['early_stop_patience'] for g in groups}=={0,5}
