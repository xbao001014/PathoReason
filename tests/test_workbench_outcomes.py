import copy
import hashlib
import json
from types import SimpleNamespace
import pytest
from pathoreason.research_workbench import build_projection,project_snapshot
from pathoreason.workbench_outcomes import review_material
from pathoreason.persistence import Missing,Conflict
from test_research_workbench import artifact,plan
from test_p1_service import fixture
from test_p5_entry import study


def packet(key,gate,aid='paper',pid='p',cid='c'):
    return {'id':key,'project_id':pid,'source_conversation':cid,'created_at':key,
            'request':{'gate':gate,'key_findings':['negative result'],'key_limitations':['not independent']},
            'materials':[{'artifact_id':aid,'role':'manuscript','sha256':'a'*64}]}


def workflow(approved=(),pending=None,index=3,status='preparing'):
    return {'project_id':'p','revision':1,'approved':list(approved),'pending':pending,'index':index,'status':status,'history':[]}


def projection(m,r=None,arts=None,**kwargs):
    return build_projection('p',arts or [artifact('paper','manuscript/paper-v13.md','text/markdown'),artifact('v99','manuscript/paper-v99.md','text/markdown'),artifact('plan','outputs/plan-v7.json')],{'plan':plan()},[],research=r or {'project_id':'p','stage_id':'manuscript','status':'active','revision':1,'conversation_id':'c'},manuscript=m,**kwargs)


def test_default_tracks_platform_stage_not_newer_filename_or_plan():
    m=workflow([packet('review13','scientific')],index=4)
    original=copy.deepcopy(m);out=projection(m)
    assert out['default_task_id']=='project_outcomes'
    assert out['tasks'][0]['focus_stage']=='delivery'
    assert out['outcomes']['content']['materials'][0]['id']=='paper'
    assert out['outcomes']['content']['status']=='approved'
    assert out['outcomes']['status']=='preparing'
    assert m==original and out['execution_authority'] is False
    assert out['tasks'][0]['stages'][-1]['material_count']==2
    assert out['revision']==projection(m)['revision']


def test_pending_reopened_and_invalidated_approvals_are_distinct():
    old=packet('old','scientific');draft=packet('draft','draft','draft')
    new=packet('new','scientific','v99');m=workflow([draft],new,status='awaiting_review')
    m['history']=[{'action':'approve','packet':old},{'event':'revision_routed','invalidated':[old]}]
    out=projection(m)['outcomes']
    assert out['content']['id']=='new' and out['content']['status']=='awaiting_review'
    assert next(h for h in out['history'] if h['id']=='old')['status']=='historical_approval'
    m.update(pending=None,status='preparing');reopened=projection(m)['outcomes']
    assert reopened['status']=='preparing' and reopened['content']['id']=='draft'
    assert projection(m)['revision']!=projection(workflow([old]))['revision']


def test_final_delivery_keeps_scientific_manuscript_and_its_figures():
    science=packet('science','scientific');science['materials'].append({'artifact_id':'figure','role':'figure','sha256':'a'*64})
    final=packet('final','delivery','pdf');final['materials'][0]['role']='pdf'
    arts=[artifact('paper','manuscript/paper.md'),artifact('pdf','manuscript/final.pdf','application/pdf'),artifact('figure','figures/a.png','image/png')]
    out=projection(workflow([science,final],index=5,status='approved'),arts=arts)['outcomes']
    assert out['status_label']=='全部作者审核已完成'
    assert out['content']['id']=='science' and out['delivery']['id']=='final'
    assert '/research-workbench/reviews/science/materials/figure' in out['content']['materials'][1]['url']


@pytest.mark.parametrize('kind',['foreign_packet','foreign_artifact','mismatch','missing','deleted_source'])
def test_untrusted_or_unavailable_reference_has_no_content_link(kind):
    p=packet('p','scientific');a=artifact('paper','manuscript/paper.md');kwargs={}
    if kind=='foreign_packet':p['project_id']='other'
    if kind=='foreign_artifact':a['project_id']='other'
    if kind=='mismatch':p['materials'][0]['sha256']='b'*64
    if kind=='missing':p['materials'][0]['artifact_id']='unknown'
    if kind=='deleted_source':kwargs['visible_conversations']=set()
    out=projection(workflow([p]),arts=[a],**kwargs)['outcomes']
    assert not out['content'] or not out['content']['materials']


def test_handoff_association_and_analysis_fallback_do_not_grant_approval():
    a=artifact('analysis','outputs/innovation/h1-report-v2.md','text/markdown')
    b=artifact('run','outputs/innovation/h1-readiness-v1.md','text/markdown')
    h={'project_id':'p','source_stage':'analysis','digest':'h','agent_report':{'summary':'negative', 'decisions':['no improvement'], 'patient_rows':['private']},'verified_evidence':[{'kind':'artifact','id':'analysis','sha256':'a'*64}]}
    r={'project_id':'p','stage_id':'analysis','status':'completed','handoff':h}
    out=projection(None,r,[a,b]);assert out['tasks'][0]['focus_stage']=='analysis'
    assert out['outcomes']['key_findings']==['no improvement']
    assert not out['outcomes']['content']
    assert 'private' not in json.dumps(out)
    assert {f['stage_id'] for f in out['families']}=={'analysis','innovation_runs'}


def test_agent_manifest_cannot_override_platform_packet_stage():
    p=packet('p','scientific');a=artifact('paper','manuscript/paper.md');manifest=artifact('manifest','outputs/manifest.json')
    doc={'schema_version':'pathoreason.workbench-manifest/1','task_id':'shared','links':[{'artifact_id':'paper','family_id':'paper','revision':'1','stage_id':'data'}]}
    out=build_projection('p',[a,manifest],{'manifest':doc},[],manuscript=workflow([p]))
    assert next(f for f in out['families'] if f['versions'][0]['artifacts'][0]['id']=='paper')['stage_id']=='delivery'


def test_snapshot_and_review_archive_are_read_only_after_conversation_move(fixture):
    s,_,_,_=fixture;v=study(s);pid=v.project_id
    with s.store.connect() as db:cid=db.execute('select id from conversations where project_id=?',(pid,)).fetchone()[0]
    raw=b'Approved manuscript';p=packet('review','scientific',pid=pid,cid=cid);p['materials'][0]['sha256']=hashlib.sha256(raw).hexdigest()
    w=workflow();w.update(project_id=pid,history=[{'event':'revision_routed','invalidated':[p]}])
    with s.store.connect(True) as db:db.execute('INSERT OR REPLACE INTO manuscript_workflows(project_id,document) VALUES(?,?)',(pid,json.dumps(w)))
    root=s.manuscripts.root/pid/'review';root.mkdir(parents=True);(root/'paper').write_bytes(raw)
    with s.store.connect() as db:before=db.execute('select document from manuscript_workflows where project_id=?',(pid,)).fetchone()[0]
    assert review_material(s,pid,'review','paper')==(raw,'text/plain')
    project_snapshot(s,pid)
    with s.store.connect() as db:assert before==db.execute('select document from manuscript_workflows where project_id=?',(pid,)).fetchone()[0]
    with pytest.raises(Missing):review_material(s,pid,'unknown','paper')
    with pytest.raises(Missing):review_material(s,pid,'review','../paper')
    (root/'paper').write_bytes(b'tampered')
    with pytest.raises(Conflict):review_material(s,pid,'review','paper')


def test_review_http_projection_headers_download_and_no_write_route(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    from pathoreason import api
    s,_,_,_=fixture;v=study(s);monkeypatch.setattr(api,'service',lambda:s)
    monkeypatch.setattr(api,'review_material',lambda service,pid,rid,aid:(b'%PDF-test','application/pdf'))
    client=TestClient(api.app);base='/api/v2/research-projects/'+v.project_id+'/research-workbench'
    r=client.get(base);assert r.status_code==200 and 'no-store' in r.headers['cache-control']
    r=client.get(base+'/reviews/review/materials/paper');assert r.headers['content-type']=='application/pdf'
    assert r.headers['x-content-type-options']=='nosniff' and "frame-ancestors 'self'" in r.headers['content-security-policy']
    assert 'content-disposition' not in r.headers
    r=client.get(base+'/reviews/review/materials/paper?download=true');assert 'attachment' in r.headers['content-disposition']
    assert client.post(base+'/reviews/review/materials/paper').status_code==405


def test_review_http_rejects_non_pdf_bytes_and_keeps_text_sandboxed(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    from pathoreason import api
    s,_,_,_=fixture;v=study(s);monkeypatch.setattr(api,'service',lambda:s)
    client=TestClient(api.app);url='/api/v2/research-projects/'+v.project_id+'/research-workbench/reviews/r/materials/a'
    monkeypatch.setattr(api,'review_material',lambda *args:(b'<html>unsafe</html>','application/pdf'))
    assert client.get(url).status_code==409
    monkeypatch.setattr(api,'review_material',lambda *args:(b'<html>plain</html>','text/html'))
    r=client.get(url);assert r.headers['content-type'].startswith('text/plain')
    assert 'sandbox' in r.headers['content-security-policy']


def test_answered_historical_questions_do_not_return_as_current_todos():
    p=packet('approved','scientific');p['request']['author_questions']=['old question']
    r={'project_id':'p','stage_id':'manuscript','status':'active','history':[{'handoff':{'project_id':'p','source_stage':'analysis','agent_report':{'open_questions':['previous stage question']}}}]}
    assert projection(workflow([p]),r)['outcomes']['open_questions']==[]
    p['request']['author_questions']=[]
    assert projection(workflow([],p,status='awaiting_review'),r)['outcomes']['open_questions']==[]
