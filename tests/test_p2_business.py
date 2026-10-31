"""Business authorization and evidence boundaries, independent of model inference."""
import hashlib,json
from pathlib import Path
import pytest
from pathoreason.business import Business, BusinessRequest, BusinessArtifact, WorkflowRef
from pathoreason.persistence import Conflict
from test_p1_service import fixture

def prepared(fixture,monkeypatch):
    svc,conv,request,runtime=fixture
    project=svc.store.create_project('CPU synthetic','Bounded synthetic research')
    tid='turn_business_test'
    row={'id':tid,'project_id':project['id'],'status':'running','input_digest':'a'*64}
    monkeypatch.setattr(svc.store,'turn',lambda _:row)
    monkeypatch.setattr(svc.business,'mode',lambda _: 'synthetic')
    monkeypatch.setattr(svc.business,'token',lambda:'server-private-token')
    request=dict(turn_id=tid,target=project['id'],grant=svc.business.grant(tid),operation='inspect')
    return svc,row,request

@pytest.mark.parametrize('mutation,error',[
    ('project','business_project_mismatch'),('inactive','business_turn_inactive'),
    ('grant','business_grant_invalid'),('discuss','business_execution_not_enabled'),
    ('legacy','legacy_projects_are_read_only')])
def test_tool_cannot_escape_bound_turn_or_project(fixture,monkeypatch,mutation,error):
    svc,row,body=prepared(fixture,monkeypatch)
    def forbidden(*_):raise AssertionError('Unauthorized request reached execution bridge')
    monkeypatch.setattr(svc.business,'invoke',forbidden)
    if mutation=='project':body['target']='prj_foreign'
    if mutation=='inactive':row['status']='completed'
    if mutation=='grant':body['grant']='0'*64
    if mutation=='discuss':monkeypatch.setattr(svc.business,'mode',lambda _:'discuss')
    if mutation=='legacy':
        row['project_id']=fixture[1]['project_id'];body['target']=row['project_id']
    with pytest.raises(Conflict,match=error):svc.business.call(BusinessRequest(**body))

def test_new_plan_cannot_be_self_approved_in_same_turn(fixture,monkeypatch):
    svc,row,body=prepared(fixture,monkeypatch);calls=[]
    def invoke(value):calls.append(value);return {'snapshot':{'state':{'revisions':[{'turn_id':row['id']}]}}}
    monkeypatch.setattr(svc.business,'invoke',invoke)
    body.update(operation='execute',expected_revision='a'*64,idempotency_key='execute-one')
    with pytest.raises(Conflict,match='plan_requires_next_user_turn'):svc.business.call(BusinessRequest(**body))
    assert [x['method'] for x in calls]==['inspect']

@pytest.mark.parametrize('field',['expected_revision','idempotency_key'])
def test_mutation_requires_revision_and_idempotency(fixture,monkeypatch,field):
    svc,row,body=prepared(fixture,monkeypatch);body.update(operation='plan',expected_revision='a'*64,idempotency_key='once');body.pop(field)
    with pytest.raises(ValueError,match='required'):svc.business.call(BusinessRequest(**body))

def test_model_cannot_override_originating_turn(fixture,monkeypatch):
    svc,row,body=prepared(fixture,monkeypatch)
    monkeypatch.setattr(svc.business,'invoke',lambda _:{'snapshot':{'state':{}}})
    body.update(operation='plan',expected_revision='a'*64,idempotency_key='once',parameters={'turn_id':'turn_foreign'})
    with pytest.raises(ValueError,match='server_owned'):svc.business.call(BusinessRequest(**body))

def test_v2_evidence_does_not_impersonate_legacy_source_or_science(fixture):
    svc,*_=fixture
    project=svc.store.create_project('CPU synthetic','Fixture')
    unit={'candidate':'base','status':'completed','payload':{'request':{'fold':0,'effective_seed':17}},'result':{'verified':{'metrics':{'val_rmse':.25}}}}
    state={'project_id':project['id'],'run_id':'run_test','status':'completed','result':{'status':'completed','goal_achieved_dev':False,'unit_evidence':[unit],'units':[unit]}}
    ids=svc.business.publish(state)
    assert len(ids)==4
    for aid in ids:
        artifact=BusinessArtifact.model_validate(svc.store.artifact(aid,project['id']))
        assert artifact.schema_version=='pathoreason/2' and artifact.evidence_role=='synthetic'
        assert artifact.source_ref.adapter=='pathoreason.synthetic_mil'
        assert artifact.run_ref.resource_id=='run_test'
        blob=svc.artifact_bytes(artifact.model_dump(mode='json'));assert hashlib.sha256(blob).hexdigest()==artifact.sha256
    assert svc.business.publish(state)==ids
    state['result']['goal_achieved_dev']=True
    assert set(svc.business.publish(state)).isdisjoint(ids)
    assert len(svc.store.artifacts(project['id']))==8

def test_internal_bridge_requires_private_auth(fixture):
    from fastapi.testclient import TestClient
    from pathoreason.api import app
    svc,*_=fixture
    path=svc.data/'runtime/control/business-token';path.parent.mkdir(parents=True,exist_ok=True);path.write_text('server-private-token');path.chmod(0o600)
    app.state.service=svc
    client=TestClient(app)
    r=client.post('/internal/business',json={'turn_id':'turn_fake','target':'prj_fake','grant':'a'*64,'operation':'inspect'})
    assert r.status_code==403

def test_native_session_permission_is_upgraded_once_without_replaying_prompt():
    import asyncio
    from pathoreason.runtime import OpenCode
    runtime=OpenCode(Path('/unused'),8522);calls=[];permissions=[]
    async def call(method,path,directory=None,body=None):
        calls.append((method,path,body))
        if method=='GET':return {'permission':list(permissions)}
        if method=='PATCH':permissions.extend(body['permission'])
        return {}
    runtime.call=call
    async def case():
        await runtime.prompt('s','/tmp','m1','deepseek-v4-pro','first')
        await runtime.prompt('s','/tmp','m2','deepseek-v4-pro','second')
    asyncio.run(case())
    assert sum(m=='PATCH' for m,_,_ in calls)==1
    assert sum(m=='POST' for m,_,_ in calls)==2
    assert permissions==[{'permission':'pathoreason_research','pattern':'*','action':'allow'}]


def test_public_text_redacts_current_expired_and_partial_capabilities(fixture,monkeypatch):
    svc,row,body=prepared(fixture,monkeypatch)
    svc.business.token_path=svc.data/'exists';svc.business.token_path.touch()
    monkeypatch.setattr(svc.store,'turns',lambda _:[row])
    grant=svc.business.grant(row['id'])
    assert grant not in svc.business.redact('old capability '+grant,'cid')
    assert grant[:20] not in svc.business.redact('grant `'+grant[:20],'cid')
    assert svc.business.redact('SHA256 '+('b'*64),'cid')=='SHA256 '+('b'*64)
