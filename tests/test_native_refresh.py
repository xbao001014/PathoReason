import asyncio
import json
import socket
import sqlite3
import pytest
from pathoreason.native_refresh import maintenance_directories,refresh_idle_instances,configured_skills,inspect_skills


class Runtime:
    def __init__(self, skill, *, busy=None, permission=None, stale=False, connected=True):
        self.skill=skill;self.busy=busy;self.permission=permission;self.stale=stale;self.connected=connected;self.disposed=[]
    async def call(self, method, path, directory):
        if path=='/session/status':return {'session':{'type':'busy'}} if directory==self.busy else {}
        if path=='/permission':return [{}] if directory==self.permission else []
        if path=='/instance/dispose':self.disposed.append(directory);return True
        if path=='/skill':return [{'name':'example','location':str(self.skill),'content':'old' if self.stale else 'new instructions'}]
        if path=='/mcp':return {'pathoreason_dialogue':{'status':'connected' if self.connected else 'failed'}}


@pytest.mark.parametrize('block',['busy','permission'])
def test_checks_all_instances_before_disposal(tmp_path,block):
    runtime=Runtime(tmp_path/'SKILL.md',**{block:'second'})
    with pytest.raises(RuntimeError,match='busy|pending'):
        asyncio.run(refresh_idle_instances(runtime,['first','second'],{},lambda r:None))
    assert not runtime.disposed


def test_innovation_catalog_exposes_hashed_resources_without_scientific_claims():
    from pathoreason.formal import project_skills, ROOT
    from pathoreason.contracts import SkillDefinition
    skills={s['id']:s for s in project_skills(True)}
    navigation=json.loads((ROOT/'config/skill-navigation.json').read_text())
    registered={s for category in navigation for stage in category['stages'] for s in stage['skill_ids']}
    for name in ('baseline-innovation','innovation-experiments','innovation-checkpoint'):
        skill=SkillDefinition.model_validate(skills[name])
        assert name in registered
        assert skill.evidence_scope=='contract_only'
        assert any('SKILL.md#sha256=' in ref for ref in skill.instruction_refs)
    assert any('method-and-cost.md#sha256=' in ref for ref in skills['innovation-experiments']['instruction_refs'])


@pytest.mark.parametrize('stale,connected',[(False,True),(True,True),(False,False)])
def test_refresh_verifies_actual_content_and_keeps_partial_receipt(tmp_path,stale,connected):
    skill=tmp_path/'SKILL.md';skill.write_text('---\nname: example\n---\nnew instructions\n')
    runtime=Runtime(skill,stale=stale,connected=connected);receipts=[]
    operation=refresh_idle_instances(runtime,['first'],{'example':skill},receipts.append)
    if stale or not connected:
        with pytest.raises(RuntimeError,match='mismatch|disconnected'):asyncio.run(operation)
        assert receipts[0]=={'directory':'first','disposed':True,'verified':False}
        assert all(not receipt['verified'] for receipt in receipts)
        if stale:assert receipts[-1]['mismatches']==[{'name':'example','reason':'content'}]
    else:
        result=asyncio.run(operation);assert result[0]['verified'];assert len(receipts)==2
    assert runtime.disposed==['first']


def test_refuses_live_application_before_reading_database(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen()
        with pytest.raises(RuntimeError,match='requires_app_offline'):
            maintenance_directories(tmp_path,listener.getsockname()[1])


@pytest.mark.parametrize('pending',['turn','context','goal','training_wait','synthetic_wait',None])
def test_offline_refresh_checks_durable_work(tmp_path,monkeypatch,pending):
    def offline(*args,**kwargs):raise ConnectionRefusedError()
    monkeypatch.setattr(socket,'create_connection',offline)
    (tmp_path/'state').mkdir()
    with sqlite3.connect(tmp_path/'state/pathoreason.sqlite3') as db:
        db.executescript('CREATE TABLE turns(status);CREATE TABLE context_operations(status);CREATE TABLE research_goals(document);CREATE TABLE conversations(directory,native_session);')
        db.execute('INSERT INTO conversations VALUES(?,?)',('/project','session'))
        if pending=='turn':db.execute("INSERT INTO turns VALUES('recovery_required')")
        if pending=='context':db.execute("INSERT INTO context_operations VALUES('running')")
        if pending=='goal':db.execute('INSERT INTO research_goals VALUES(?)',(json.dumps({'state':'active'}),))
        if pending in ('training_wait','synthetic_wait'):
            db.execute('INSERT INTO research_goals VALUES(?)',(json.dumps({'state':'waiting','wait_for':{'kind':'training_run' if pending=='training_wait' else 'synthetic_run','run_id':'fixture'}}),))
    if pending and pending!='training_wait':
        with pytest.raises(RuntimeError,match='unresolved|active'):maintenance_directories(tmp_path,1)
    else:assert maintenance_directories(tmp_path,1)==['/project']


def test_catalog_finds_new_skills_and_rejects_ambiguous_names(tmp_path):
    root=tmp_path/'skills';root.mkdir()
    config={'skills':{'paths':['skills']}}
    def add(folder,name):
        p=root/folder/'SKILL.md';p.parent.mkdir();p.write_text(f'---\nname: {name}\ndescription: example\n---\nbody')
        return p
    first=add('first','first')
    assert configured_skills(tmp_path,config)=={'first':first}
    second=add('second','second')
    assert configured_skills(tmp_path,config)=={'first':first,'second':second}
    add('duplicate','first')
    with pytest.raises(RuntimeError,match='duplicate:first'):configured_skills(tmp_path,config)


@pytest.mark.parametrize('source',['no frontmatter','---\ndescription: missing name\n---\nbody'])
def test_invalid_skill_is_not_silently_omitted(tmp_path,source):
    (tmp_path/'SKILL.md').write_text(source)
    with pytest.raises(RuntimeError,match='invalid'):
        configured_skills(tmp_path,{'skills':{'paths':[str(tmp_path)]}})


def test_audit_reports_missing_skill_without_disposal(tmp_path):
    skill=tmp_path/'SKILL.md';skill.write_text('---\nname: added\n---\nnew instructions')
    runtime=Runtime(skill)
    result=asyncio.run(inspect_skills(runtime,'first',{'added':skill}))
    assert not result['verified'] and result['mismatches']==[{'name':'added','reason':'missing'}]
    assert not runtime.disposed


def test_idle_rechecked_before_each_disposal(tmp_path):
    class BecomesBusy(Runtime):
        checks=0
        async def call(self,method,path,directory):
            if path=='/session/status':
                self.checks+=1
                if self.checks==2:return {'session':{'type':'busy'}}
            return await super().call(method,path,directory)
    runtime=BecomesBusy(tmp_path/'SKILL.md')
    with pytest.raises(RuntimeError,match='busy'):
        asyncio.run(refresh_idle_instances(runtime,['first'],{},lambda r:None))
    assert not runtime.disposed
