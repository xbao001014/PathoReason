import asyncio,json,time
from datetime import datetime,timezone
import pytest
from pathoreason.timing import observe,seconds,totals
from pathoreason.command_activity import command_activity
from pathoreason.persistence import Conflict
from test_p1_service import fixture,settled
from test_p5_entry import formal_runtime,study


def iso(value):return datetime.fromtimestamp(value,timezone.utc).isoformat()
def row(start=1000,end=1100,timing=None):return {'created_at':iso(start),'document':json.dumps({'finished_at':iso(end) if end else None}),'timing':json.dumps(timing) if timing else None}
def messages(parts,parent='user'):return [{'info':{'role':'assistant','parentID':parent},'parts':parts}]
def tool(id,start,end=None,status='running'):return {'id':id,'type':'tool','state':{'status':status,'time':{'start':start*1000,**({'end':end*1000} if end is not None else {})}}}


def test_parallel_tool_time_is_unioned_and_kept_after_compaction():
    ledger=observe({},messages([tool('a',1010,1050,'completed'),tool('b',1030,1080,'completed')]),'user',1000,1100)
    timing=seconds(row(),ledger)
    assert timing.wall_seconds==100 and timing.tool_seconds==70 and timing.agent_seconds==30
    assert observe(ledger,[], 'user',1000,1110)['spans']==ledger['spans']
    assert seconds(row(end=None),ledger,1120).agent_seconds==50


def test_unobserved_disconnect_and_invalid_timestamps_remain_charged():
    ledger=observe({},messages([tool('a',1010)]),'user',1000,1040)
    assert seconds(row(),ledger).tool_seconds==30
    assert seconds(row(),ledger).budget_seconds==70
    invalid=messages([tool('wrong',950,1090),tool('future',1110,1150),tool('reverse',1070,1060),tool('nan',float('nan'))])
    assert observe(ledger,invalid,'user',1000,1100)['spans']==ledger['spans']
    assert not observe({},messages([tool('other',1010,1090)],'other'),'user',1000,1100)['spans']


def test_legacy_history_is_not_rebilled():
    legacy=row();new=row(timing={'spans':{'t':[1010,1090]}})
    assert totals([legacy,new])=={'wall_seconds':200,'budget_seconds':120,'tool_seconds':80,'legacy_seconds':100}
    assert seconds(legacy).agent_seconds is None
    precise={"created_at":"2026-11-01T00:00:00.000001+00:00","document":json.dumps({"finished_at":"2026-11-01T00:00:01.123457+00:00"})}
    assert seconds(precise).budget_seconds==1.123456


@pytest.mark.parametrize('command,expected',[
    ('cat /private/data.txt','read'),('sleep 5','wait'),('python -m pip install addict','dependencies'),
    ('python train_mil.py --yaml_path /private/config.yaml','train'),
    ('P=/venv/bin/python; S=/repo/study_io.py; $P $S publish --file outputs/x.json','publish'),
    ('python - <<\'PY\'\nimport h5py\nh.create_dataset("features",data=x)\nPY\n','prepare'),
    ('python - <<\'PY\'\nimport yaml\nyaml.safe_dump(cfg,stream)\nPY\n','config'),
    ('echo "python train.py"','command'),('python -c \'print("python train.py")\'','python'),
])
def test_command_labels_follow_structure_without_leaking_values(command,expected):
    result=command_activity(command)
    assert result['kind']==expected,result
    assert '/private/' not in json.dumps(result)
    assert ('repeat_key' in result)


def test_compound_does_not_group_and_repeat_requires_exact_command():
    x=command_activity('python -m pip install x && python train_mil.py | tail -20')
    assert x['kind']=='compound' and '安装' in x['summary'] and '训练' in x['summary'] and x['repeat_key'] is None
    assert command_activity('tail a.log')['repeat_key']!=command_activity('tail b.log')['repeat_key']
    assert command_activity('tail a.log')==command_activity('tail a.log')


def test_formal_admission_uses_recorded_agent_time_and_ledger_survives_restart(fixture):
    from pathoreason.service import Service
    s,_,request,r=fixture;formal_runtime(r)
    async def case():
        v=study(s,turns=4);cid=s.store.conversations(v.project_id)[0]['id']
        result=await s.submit(cid,{**request,'skill_id':None,'artifact_ids':[]});tid=result['turn']['id'];await settled(s,tid)
        with s.store.connect(True) as db:
            doc=json.loads(s.store.turn(tid)['document']);doc.update(created_at=iso(1000),finished_at=iso(1120))
            db.execute('UPDATE turns SET created_at=?,document=? WHERE id=?',(iso(1000),json.dumps(doc),tid))
            db.execute('UPDATE turn_timing SET document=? WHERE turn_id=?',(json.dumps({'spans':{'tool':[1010,1110]}}),tid))
        view=s.formal.view(v.project_id)
        assert view.used_wall_seconds==120 and view.used_budget_seconds==20 and view.excluded_tool_seconds==100
        restored=Service(s.store,r,s.config);assert restored.store.timing(tid).budget_seconds==20
        second=await restored.submit(cid,{**request,'request_key':'second','skill_id':None,'artifact_ids':[]});await settled(restored,second['turn']['id'])
        # Losing a ledger conservatively falls back to legacy wall charge, not zero.
        with s.store.connect(True) as db:db.execute('DELETE FROM turn_timing WHERE turn_id=?',(tid,))
        with pytest.raises(Conflict,match='budget_exhausted'):
            await restored.submit(cid,{**request,'request_key':'third','skill_id':None,'artifact_ids':[]})
    asyncio.run(case())


def test_tool_exclusion_does_not_remove_turn_wall_limit(fixture):
    from pathoreason.formal import StudyCreate
    s,_,request,r=fixture;formal_runtime(r);s.config['execution_environment']='bxn-server';r.hold=True
    async def case():
        v=s.formal.create(StudyCreate(request_key='wall',title='Fixture',objective='test',budget={'max_turns':2,'max_wall_seconds':60,'max_turn_wall_seconds':60}))
        cid=s.store.conversations(v.project_id)[0]['id'];result=await s.submit(cid,{**request,'skill_id':None,'artifact_ids':[]});tid=result['turn']['id']
        beginning=time.time()-120
        with s.store.connect(True) as db:
            doc=json.loads(s.store.turn(tid)['document']);doc['created_at']=iso(beginning)
            db.execute('UPDATE turns SET created_at=?,document=? WHERE id=?',(iso(beginning),json.dumps(doc),tid))
        async def native(sid,directory):
            parent=r.sessions[sid]
            return [{'info':{'id':parent,'role':'user'},'parts':[]}]+messages([tool('ongoing',beginning+1)],parent)
        r.messages=native
        await settled(s,tid)
        assert s.store.turn(tid)['status']=='failed'
        assert json.loads(s.store.turn(tid)['document'])['error_code']=='turn_wall_time_limit'
        assert s.store.timing(tid).budget_seconds<60 and r.abort_called
    asyncio.run(case())
