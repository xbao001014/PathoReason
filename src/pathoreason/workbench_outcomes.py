"""Read-only outcomes from platform handoffs and exact manuscript review packets.

Navigation hints never grant approval. Effective approval is taken only from the
workflow's approved slots; invalidated packets remain history. No file reads or
state initialization happen here.
"""
from pathlib import PurePosixPath
import re
from urllib.parse import quote

STAGE = {'data':'data','baseline':'baseline','innovation':'innovation_runs',
         'analysis':'analysis','manuscript':'delivery'}
LABEL = {'data':'数据准备','baseline':'基线实验','innovation':'创新实验',
         'analysis':'分析与验证','manuscript':'稿件与交付'}
GATES = [('blueprint','事实与写作方案'),('draft','初稿与图件'),('review','审稿裁定'),
         ('scientific','修订稿科学内容'),('delivery','最终交付')]


def text(value, limit=1800):
    return value[:limit] if isinstance(value,str) else ''


def lines(value):
    return [text(x,1200) for x in value[:12] if isinstance(x,str)] if isinstance(value,list) else []


def navigation_stage(artifact):
    """Legacy navigation only, used after explicit/schema associations."""
    path=artifact.get('source_ref',{}).get('resource_id',artifact.get('relative_path','')).lower()
    parts=PurePosixPath(path).parts
    if 'manuscript' in parts:return 'delivery'
    if 'analysis' in parts:return 'analysis'
    stem=PurePosixPath(path).stem
    if 'innovation' in parts:
        if re.search(r'(results?|report|review|analysis|consolidation|diagnosis|handover|figure-data|verification|audit)',stem):return 'analysis'
        if re.search(r'(plan|proposal|direction)',stem):return 'innovation'
        return 'innovation_runs'
    if re.search(r'(results-summary|comparison|scientific-review|analysis-report)',stem):return 'analysis'
    return None


def project_outcomes(pid, artifacts, research=None, manuscript=None, visible_conversations=None):
    by_id={a['id']:a for a in artifacts if a.get('project_id',pid)==pid}
    r=research if research and research.get('project_id')==pid else {}
    m=manuscript if manuscript and manuscript.get('project_id')==pid else {}
    if not r and not m:return None,{},[]
    stages={};notices=[]
    def visible(cid):return bool(cid) and (visible_conversations is None or cid in visible_conversations)
    def material(ref,packet=None):
        aid=ref.get('artifact_id') or ref.get('id');a=by_id.get(aid)
        # An identity mismatch must not produce a content URL or leak another project.
        if not a or not ref.get('sha256') or a.get('sha256')!=ref['sha256']:
            notices.append('审核或交接材料缺失／身份不匹配，未提供预览：'+text(aid,160));return None
        url='/api/v1/research-projects/'+quote(pid,safe='')+'/artifacts/'+quote(aid,safe='')+'/content'
        if packet:
            if not visible(packet.get('source_conversation')):return None
            url='/api/v2/research-projects/'+quote(pid,safe='')+'/research-workbench/reviews/'+quote(packet['id'],safe='')+'/materials/'+quote(aid,safe='')
        return {'id':aid,'title':text(ref.get('label') or a.get('title'),240),
                'role':text(ref.get('role'),80),'media_type':a.get('media_type',''),
                'size_bytes':a.get('size_bytes',0),'sha256':a['sha256'],'url':url}
    approved={p['id']:p for p in m.get('approved',[]) if isinstance(p,dict) and p.get('project_id')==pid and visible(p.get('source_conversation'))}
    pending=m.get('pending')
    if not isinstance(pending,dict) or pending.get('project_id')!=pid or not visible(pending.get('source_conversation')):pending=None
    packets={};former_approved=set()
    for h in m.get('history',[]):
        if h.get('action')=='approve' and h.get('packet'):former_approved.add(h['packet']['id'])
        for p in [h.get('packet'),*(h.get('invalidated') or [])]:
            if isinstance(p,dict) and p.get('project_id')==pid and visible(p.get('source_conversation')):packets[p['id']]=p
    packets.update(approved)
    if pending:packets[pending['id']]=pending
    def bundle(p,status):
        req=p.get('request',{});gate=req.get('gate','');items=[]
        for ref in p.get('materials',[]):
            item=material(ref,p)
            if item:items.append(item);stages[item['id']]='delivery'
        return {'id':p['id'],'gate':gate,'title':dict(GATES).get(gate,'稿件材料'),
                'status':status,'status_label':{'approved':'作者已批准','awaiting_review':'待作者审核',
                 'historical_approval':'历史批准 · 已替代','history':'历史审核包'}[status],
                'created_at':p.get('created_at',''),'summary':text(req.get('summary')),
                'key_findings':lines(req.get('key_findings')),'limitations':lines(req.get('key_limitations')),
                'open_questions':lines(req.get('author_questions')),
                'changes':lines(req.get('changes')),'materials':items,
                'conversation_id':p.get('source_conversation') if visible(p.get('source_conversation')) else None}
    # Highest effective content gate supplies the current manuscript. Never select
    # an unreviewed v99 merely because its filename/registration is newer.
    content_gates={'draft':1,'review':2,'scientific':3}
    current_content=None
    if pending and pending.get('request',{}).get('gate') in content_gates:current_content=pending
    else:
        candidates=[p for p in approved.values() if p.get('request',{}).get('gate') in content_gates]
        if candidates:current_content=max(candidates,key=lambda p:content_gates[p['request']['gate']])
    delivery=next((p for p in approved.values() if p.get('request',{}).get('gate')=='delivery'),None)
    if pending and pending.get('request',{}).get('gate')=='delivery':delivery=pending
    current_ids={p['id'] for p in (current_content,delivery,pending) if p}
    bundles={key:bundle(p,'awaiting_review' if pending and key==pending['id'] else 'approved' if key in approved else 'historical_approval' if key in former_approved else 'history') for key,p in packets.items()}
    # All packets bind navigation, but only effective slots bind current status.
    history=[{**b,'status':'historical_approval' if b['status']=='approved' else b['status'],
              'status_label':'此前节点已批准' if b['status']=='approved' else b['status_label']}
             for key,b in bundles.items() if key not in current_ids]
    history.sort(key=lambda b:b['created_at'],reverse=True)
    handoffs=[]
    for h in r.get('history',[]):
        if isinstance(h.get('handoff'),dict):handoffs.append(h['handoff'])
    if isinstance(r.get('handoff'),dict):handoffs.append(r['handoff'])
    projected=[]
    for h in handoffs:
        if h.get('project_id')!=pid:continue
        report=h.get('agent_report',{});items=[];sid=STAGE.get(h.get('source_stage'))
        for ref in h.get('verified_evidence',[]):
            if ref.get('kind')!='artifact':continue
            item=material(ref)
            if item:
                items.append(item)
                if sid:stages.setdefault(item['id'],sid)
        projected.append({'id':h.get('digest',''),'stage_id':h.get('source_stage'),
            'summary':text(report.get('summary')),'key_findings':lines(report.get('decisions')),
            'limitations':lines(report.get('limitations')),'open_questions':lines(report.get('open_questions')),
            'next_action':text(report.get('next_action')),'materials':items,'created_at':h.get('created_at','')})
    latest=projected[-1] if projected else {}
    conclusion=next((h for h in reversed(projected) if h['stage_id']=='analysis'),latest)
    content=bundles.get(current_content['id']) if current_content else None
    delivery_view=bundles.get(delivery['id']) if delivery else None
    focus=bundles.get(pending['id']) if pending else delivery_view or content
    index=m.get('index',0)
    gate=GATES[index][1] if isinstance(index,int) and 0<=index<len(GATES) else '审核完成'
    status=m.get('status') if r.get('stage_id')=='manuscript' or not r else r.get('status')
    status_label={'approved':'全部作者审核已完成','awaiting_review':'待作者审核','preparing':'正在修订／准备',
                  'completed':'阶段已完成','active':'进行中','awaiting_switch':'待切换阶段'}.get(status,'状态待核对')
    return {'stage_id':STAGE.get(r.get('stage_id'),'delivery'),'stage_label':LABEL.get(r.get('stage_id'),'稿件与交付'),
            'node_label':gate if r.get('stage_id')=='manuscript' or not r else LABEL.get(r.get('stage_id'),'研究阶段'),
            'status':status or 'unknown','status_label':status_label,
            'conversation_id':r.get('conversation_id') if visible(r.get('conversation_id')) else None,
            'summary':(focus or {}).get('summary') or latest.get('summary',''),
            'key_findings':conclusion.get('key_findings') or (content or {}).get('key_findings',[]),
            'limitations':conclusion.get('limitations') or (content or {}).get('limitations',[]),
            'open_questions':(focus or {}).get('open_questions',[]) if pending else latest.get('open_questions',[]) if r.get('handoff') else [],
            'next_action':latest.get('next_action','') if r.get('handoff') else '',
            'content':content,'delivery':delivery_view,'pending':bundles.get(pending['id']) if pending else None,
            'history':history,'handoffs':projected,
            'revision':{'research':r.get('revision'),'manuscript':m.get('revision')}},stages,notices


def review_material(service,pid,review_id,artifact_id):
    """Read an immutable review archive even after a same-stage conversation move.

    No workflow get()/owner(): those may initialize state or require the active
    conversation. Project ownership and deleted source conversations still apply.
    """
    import hashlib
    import json
    from .persistence import Missing, Conflict
    service.store.project(pid)
    with service.store.connect() as db:
        row=db.execute('SELECT document FROM manuscript_workflows WHERE project_id=?',(pid,)).fetchone()
        if not row:raise Missing('manuscript_review_not_found')
        w=json.loads(row[0]);packets=[w.get('pending'),*w.get('approved',[])]
        for h in w.get('history',[]):packets.extend([h.get('packet'),*(h.get('invalidated') or [])])
        p=next((p for p in packets if isinstance(p,dict) and p.get('project_id')==pid and p.get('id')==review_id),None)
        if not p:raise Missing('manuscript_review_not_found')
        source=db.execute('SELECT id FROM conversations WHERE id=? AND project_id=? AND NOT EXISTS(SELECT 1 FROM conversation_deletions d WHERE d.conversation_id=conversations.id)',(p.get('source_conversation'),pid)).fetchone()
        if not source:raise Missing('manuscript_review_not_found')
        m=next((m for m in p.get('materials',[]) if m.get('artifact_id')==artifact_id),None)
        if not m or not all(re.fullmatch(r'[A-Za-z0-9_-]+',x) for x in (pid,review_id,artifact_id)):raise Missing('manuscript_material_not_found')
    try:data=(service.manuscripts.root/pid/review_id/artifact_id).read_bytes()
    except FileNotFoundError:raise Missing('manuscript_material_not_found') from None
    if hashlib.sha256(data).hexdigest()!=m.get('sha256'):raise Conflict('manuscript_snapshot_changed')
    return data,m.get('media_type','text/plain')
