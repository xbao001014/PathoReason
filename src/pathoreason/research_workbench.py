"""Read-only, evidence-qualified research projection. Never repairs source results.

Legacy file series and conversation episodes are navigation suggestions, not
authoritative task identity, approval, scientific verification or job state.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import csv
import io
import json
import math
from pathlib import PurePosixPath
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from .contracts import canonical_digest
from .persistence import now
from .workbench_outcomes import project_outcomes, navigation_stage

STAGES = [('data','数据与任务'),('plan','研究方案'),('readiness','执行准备'),
          ('baseline','基线实验'),('innovation','创新方案'),('innovation_runs','创新实验'),
          ('analysis','分析与验证'),('delivery','论文交付')]
STAGE_IDS = {s for s,_ in STAGES}
ACTIVE = {'running','queued','interrupt_requested','recovery_required'}
MAX_FILE = 2 * 1024 * 1024
MAX_BYTES = 16 * 1024 * 1024


class WorkbenchLink(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artifact_id: str = Field(min_length=1, max_length=160)
    stage_id: Literal['data','plan','readiness','baseline','innovation','innovation_runs','analysis','delivery']
    family_id: str = Field(min_length=1, max_length=120)
    revision: str = Field(min_length=1, max_length=120)
    supersedes: list[str] = Field(default_factory=list, max_length=100)


class WorkbenchManifest(BaseModel):
    """Agent-declared associations. Never sets execution or approval state."""
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['pathoreason.workbench-manifest/1']
    task_id: str = Field(min_length=1, max_length=160)
    links: list[WorkbenchLink] = Field(max_length=500)


class InnovationProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['pathoreason.innovation-proposal/1']
    proposal_id: str = Field(min_length=1, max_length=120)
    task_id: str = Field(min_length=1, max_length=160)
    revision: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    hypothesis: str = Field(min_length=1, max_length=4000)
    gap: str = Field(default='', max_length=4000)
    mechanism: str = Field(default='', max_length=4000)
    baseline: str = Field(default='', max_length=240)
    selection_reason: str = Field(default='', max_length=4000)
    decision: Literal['proposed','selected','deferred','rejected'] = 'proposed'
    falsification: str = Field(default='', max_length=4000)
    implementation: str = Field(default='', max_length=4000)
    source_refs: list[str] = Field(default_factory=list, max_length=100)
    evidence_artifact_ids: list[str] = Field(default_factory=list, max_length=100)
    parent_proposal_ids: list[str] = Field(default_factory=list, max_length=100)
    conditions: list[dict] = Field(default_factory=list, max_length=100)


class ResearchWorkbenchView(BaseModel):
    schema_version: Literal['pathoreason.research-workbench/1'] = 'pathoreason.research-workbench/1'
    project_id: str
    revision: str
    observed_at: str
    default_task_id: str
    tasks: list[dict]
    families: list[dict]
    changes: list[dict]
    activity: list[dict]
    notices: list[str]
    artifact_count: int
    outcomes: dict | None = None
    execution_authority: Literal[False] = False


def short(value, limit=1600):
    if value is None: return ''
    return (value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,allow_nan=False))[:limit]


def series(path):
    stem = str(PurePosixPath(path).with_suffix(''))
    match = re.search(r'[-_]v(\d+)$',stem,flags=re.I)
    return (stem[:match.start()], match.group(1)) if match else (stem,'')


def view_id(key):
    return 'view_'+hashlib.sha256(key.encode()).hexdigest()[:20]


def base_schema(doc):
    value=doc.get('schema_version','')
    return value.rsplit('/',1)[0] if isinstance(value,str) else ''


def stage_for(a,doc):
    if a.get('stage_ref') in STAGE_IDS: return a['stage_ref'],'explicit'
    name=base_schema(doc).removeprefix('pathoreason.')
    if name in {'task-spec','dataset-profile','dataset-audit','cohort-verification','split-manifest','split-freeze'}:return 'data','schema'
    if name in {'benchmark-plan','method-inventory','holdout-arithmetic','training-scope','regression-options'}:return 'plan','schema'
    if name=='innovation-proposal':return 'innovation','schema'
    if name in {'adapter-status','alignment-check','mil-preflight'}:return 'readiness','schema'
    if name.startswith('smoke') or name=='block-results':return 'baseline','schema'
    if name=='task-switch-audit':return 'analysis','schema'
    if a.get('kind')=='figure' and a.get('evidence_role')=='manuscript_review':return 'delivery','metadata'
    hint=navigation_stage(a)
    return (hint,'navigation_hint') if hint else ('unassigned','unknown')


def references(doc, known):
    found=set()
    def walk(v,depth=0):
        if depth>8:return
        if isinstance(v,dict):
            for item in v.values():walk(item,depth+1)
        elif isinstance(v,list):
            for item in v[:500]:walk(item,depth+1)
        elif isinstance(v,str) and v in known:found.add(known[v])
    walk(doc)
    return found


def plan_summary(doc):
    """Deliberate allowlist: never project patient rows or unbounded raw JSON."""
    validation=doc.get('validation',{})
    validation=validation if isinstance(validation,dict) else {}
    matrix=doc.get('matrix',{})
    matrix=matrix if isinstance(matrix,dict) else {}
    return {
        'objective':short(doc.get('objective'),1200),
        'models':[short(x,120) for x in matrix.get('model_ids',[])[:100]] if isinstance(matrix.get('model_ids'),list) else [],
        'seeds':[x for x in matrix.get('seeds',[])[:100] if type(x) is int] if isinstance(matrix.get('seeds'),list) else [],
        'fits':matrix.get('total_fit_runs') if type(matrix.get('total_fit_runs')) is int else None,
        'folds':matrix.get('folds') if type(matrix.get('folds')) is int else None,
        'validation_method':short(validation.get('method') or doc.get('evaluation_strategy'),400),
        'split_status':short(validation.get('split_status'),120),
        'split_counts':short(doc.get('split_counts'),1200),
        'change_summary':short(doc.get('change_summary'),1800),
        'source_type':'artifact_report', 'adoption_status':'unknown',
    }


def plan_diff(before,after):
    result=[]
    for key,label in [('models','比较模型'),('seeds','训练种子'),('fits','训练次数'),('folds','交叉验证折数'),
                      ('validation_method','验证协议'),('split_status','划分状态声明'),('split_counts','划分人数')]:
        if before.get(key)!=after.get(key):
            result.append({'field':label,'before':short(before.get(key),1200),'after':short(after.get(key),1200)})
    return result


def clean_metrics(value):
    if not isinstance(value,dict):return {}
    keys={'macro_auc','qwk','acc','auc','mae','rmse','macro_f1','bacc','n'}
    return {k:v for k,v in value.items() if k in keys and type(v) in (int,float) and math.isfinite(v)}


def reported_results(doc,aid):
    if base_schema(doc)!='pathoreason.block-results':return []
    result=[]
    rows=doc.get('results',[])
    if not isinstance(rows,list):return []
    for r in rows[:1000]:
        if not isinstance(r,dict) or not isinstance(r.get('model'),str) or type(r.get('seed')) is not int:continue
        value=r.get('val_best')
        result.append({'model':r['model'][:120],'seed':r['seed'],
                       'val_best':value if type(value) in (int,float) and math.isfinite(value) else None,
                       'test':clean_metrics(r.get('test')), 'artifact_id':aid,'state':'reported',
                       'source_type':'artifact_report','plan_binding':'unverified'})
    return result


def project_snapshot(service,pid):
    """One DB read transaction; never initializes or mutates task state."""
    service.store.project(pid)
    with service.store.connect() as db:
        db.execute('BEGIN')
        artifacts=[json.loads(r[0]) for r in db.execute('SELECT document FROM artifacts WHERE project_id=? ORDER BY rowid',(pid,))]
        turns=[dict(r) for r in db.execute('''SELECT t.id,t.conversation_id,t.created_at,t.status,t.user_text,t.text
            FROM turns t JOIN conversations c ON c.id=t.conversation_id
            WHERE t.project_id=? AND NOT EXISTS(SELECT 1 FROM conversation_deletions d WHERE d.conversation_id=t.conversation_id)
            ORDER BY t.created_at,t.id''',(pid,))]
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        code_tasks=[json.loads(r[0]) for r in db.execute('SELECT document FROM task_code_tasks WHERE project_id=? ORDER BY rowid',(pid,))] if 'task_code_tasks' in tables else []
        snapshots=[{'task_id':r[0],**json.loads(r[1])} for r in db.execute('''SELECT s.task_id,s.document FROM task_code_snapshots s
            JOIN task_code_tasks t ON t.id=s.task_id WHERE t.project_id=? ORDER BY s.rowid''',(pid,))] if 'task_code_snapshots' in tables else []
        platform={}
        for table,key in [('research_workflows','research'),('manuscript_workflows','manuscript')]:
            row=db.execute('SELECT document FROM '+table+' WHERE project_id=?',(pid,)).fetchone() if table in tables else None
            platform[key]=json.loads(row[0]) if row else None
        platform['visible_conversations']={r[0] for r in db.execute('SELECT id FROM conversations WHERE project_id=? AND NOT EXISTS(SELECT 1 FROM conversation_deletions d WHERE d.conversation_id=conversations.id)',(pid,))}
    docs={};errors=[];used=0
    for a in artifacts:
        legacy_csv=a.get('source_ref',{}).get('adapter')=='auto_research.evidence_file' and PurePosixPath(a.get('relative_path','')).name in {'performance.csv','cell_metrics.csv'}
        if a.get('media_type')!='application/json' and not legacy_csv:continue
        size=a.get('size_bytes',0)
        if size>MAX_FILE or used+size>MAX_BYTES:
            errors.append(a['id']+'：超过结构化摘要读取范围，原文件仍可查看');continue
        try:
            raw=service.artifact_bytes(a);used+=len(raw)
            if legacy_csv:
                rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
                if len(rows)>5000:raise ValueError('csv_too_large')
                docs[a['id']]={'_legacy_csv':rows};continue
            value=json.loads(raw,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite_json')))
            if isinstance(value,dict):docs[a['id']]=value
        except (ValueError,OSError,KeyError,TypeError,RecursionError):
            errors.append(a['id']+'：来源读取或摘要核验失败，未用于推断状态')
    return build_projection(pid,artifacts,docs,turns,code_tasks,snapshots,errors,**platform)


def build_projection(pid,artifacts,docs,turns,code_tasks=(),snapshots=(),errors=(),*,research=None,manuscript=None,visible_conversations=None):
    outcomes,platform_stages,platform_notices=project_outcomes(pid,artifacts,research,manuscript,visible_conversations)
    legacy=False
    if outcomes is None:
        from .legacy_workbench import legacy_outcomes
        outcomes,platform_stages,platform_notices=legacy_outcomes(pid,artifacts,docs)
        legacy=outcomes is not None
    by_id={a['id']:a for a in artifacts};order={a['id']:i for i,a in enumerate(artifacts)}
    known={a.get('source_ref',{}).get('resource_id',a.get('relative_path','')):a['id'] for a in artifacts}
    paths={a['id']:a.get('source_ref',{}).get('resource_id',a.get('relative_path','')) for a in artifacts}
    origin={};turn_refs={};turn_by_id={r['id']:r for r in turns}
    for t in turns:
        refs=set(re.findall(r'artifact:([A-Za-z0-9_-]+)',t.get('text',''))) & by_id.keys()
        turn_refs[t['id']]=refs
        for aid in refs:origin.setdefault(aid,t)
    tasks={};assignment={};basis={};plan_ids={};family_plans=defaultdict(list)
    for a in artifacts:
        aid=a['id'];doc=docs.get(aid,{})
        if base_schema(doc)=='pathoreason.benchmark-plan':
            key,_=series(paths[aid]);tid=view_id(pid+':'+key)
            family_plans[tid].append(aid);assignment[aid]=tid;basis[aid]='方案文件系列（展示分组）';plan_ids[aid]=tid
            title=short(doc.get('objective') or a['title'],240).split('：')[0]
            tasks[tid]={'id':tid,'title':title,'kind':'historical_projection','basis':'方案文件系列；不代表正式任务注册或采纳',
                        'parent_task_id':None,'code_revision':None,'snapshots':[]}
    for c in code_tasks:
        tid=c['id']
        tasks[tid]={'id':tid,'title':short(c.get('objective') or c.get('title') or tid,240),
                    'kind':'registered_task','basis':'平台任务登记','parent_task_id':c.get('parent_task_id'),
                    'code_revision':c.get('revision'),'snapshots':[
                        {'id':x.get('id'),'scope':x.get('scope','source_only'),'execution_ready':False}
                        for x in snapshots if x.get('task_id')==tid]}
    common='shared';tasks[common]={'id':common,'title':'共享与待归类材料','kind':'unassigned','basis':'归属未确认',
                                 'parent_task_id':None,'code_revision':None,'snapshots':[]}
    explicit={};warnings=[*errors,*platform_notices]
    for a in artifacts:
        aid=a['id'];doc=docs.get(aid,{})
        if doc.get('schema_version')!='pathoreason.workbench-manifest/1':continue
        try:
            m=WorkbenchManifest.model_validate(doc)
            if m.task_id not in tasks:raise ValueError('unknown_task')
            # Validate all links before using any of a manifest. Cross-project and
            # missing references cannot contaminate a partial projection.
            if len({x.artifact_id for x in m.links})!=len(m.links):raise ValueError('duplicate_link')
            for link in m.links:
                if link.artifact_id not in by_id or any(x not in by_id or x==link.artifact_id for x in link.supersedes):raise ValueError('unknown_reference')
            for link in m.links:explicit[link.artifact_id]=(m.task_id,link)
            assignment[aid]=m.task_id;basis[aid]='Agent 关联清单'
        except (ValueError,TypeError):warnings.append(aid+'：关联清单无效，未应用')
    for aid,(tid,link) in explicit.items():assignment[aid]=tid;basis[aid]='Agent 显式关联（非平台审核）'
    family_plans=defaultdict(list)
    for aid in plan_ids:
        plan_ids[aid]=assignment[aid];family_plans[assignment[aid]].append(aid)
    for aid,doc in docs.items():
        if doc.get('schema_version')=='pathoreason.innovation-proposal/1':
            try:
                proposal=InnovationProposal.model_validate(doc)
                if proposal.task_id in tasks and all(x in by_id for x in proposal.evidence_artifact_ids):
                    assignment[aid]=proposal.task_id;basis[aid]='创新方案显式任务引用'
            except ValueError:pass
    # References provide stronger navigation evidence than chronology. Shared
    # dependencies are deliberately left shared, never made exclusive.
    inbound=defaultdict(set)
    for aid,tid in plan_ids.items():
        for ref in references(docs.get(aid,{}),known):inbound[ref].add(tid)
    for aid,tids in inbound.items():
        if aid not in assignment and len(tids)==1:assignment[aid]=next(iter(tids));basis[aid]='方案中的文件引用'
    for aid,doc in docs.items():
        refs=references(doc,known);tids={assignment[x] for x in refs if x in plan_ids}
        if aid not in assignment and len(tids)==1:assignment[aid]=next(iter(tids));basis[aid]='材料中的方案引用'
    # Group unregistered history by a cited plan episode within the SAME
    # conversation. This is marked inferred, never an approval or a parent edge.
    episode={}
    for t in turns:
        anchors={assignment[x] for x in turn_refs[t['id']] if x in plan_ids}
        if len(anchors)==1:episode[t['conversation_id']]=next(iter(anchors))
        elif len(anchors)>1:episode.pop(t['conversation_id'],None)
        for aid in turn_refs[t['id']]:
            if origin.get(aid,{}).get('id')==t['id'] and aid not in assignment and t['conversation_id'] in episode:
                assignment[aid]=episode[t['conversation_id']];basis[aid]='同会话方案阶段关联（待核对）'
    # Pairing by file stem is explicitly a display candidate, not a claim that
    # two formats contain identical semantics or are an adopted revision.
    stem_tasks=defaultdict(set)
    for aid,tid in assignment.items():stem_tasks[str(PurePosixPath(paths[aid]).with_suffix(''))].add(tid)
    for aid in by_id:
        stem=str(PurePosixPath(paths[aid]).with_suffix(''));tids=stem_tasks[stem]
        if aid not in assignment and len(tids)==1:assignment[aid]=next(iter(tids));basis[aid]='同名格式关联（待核对）'
        assignment.setdefault(aid,common);basis.setdefault(aid,'归属未确认')
    # A shared dependency must not acquire exclusive task ownership by an
    # unrelated first chat citation. Explicit associations can disambiguate it.
    for aid,tids in inbound.items():
        if len(tids)>1 and aid not in explicit and aid not in plan_ids:
            assignment[aid]=common;basis[aid]='多个方案共同引用'
    stages={aid:stage_for(by_id[aid],docs.get(aid,{}))[0] for aid in by_id}
    stems=defaultdict(list)
    for aid in by_id:stems[str(PurePosixPath(paths[aid]).with_suffix(''))].append(aid)
    for group in stems.values():
        known_stages={stages[a] for a in group if stages[a]!='unassigned'}
        if len(known_stages)==1:
            for aid in group:
                if stages[aid]=='unassigned':stages[aid]=next(iter(known_stages))
    families={};changes=[];innovations=defaultdict(list)
    for a in artifacts:
        aid=a['id'];tid=assignment[aid];doc=docs.get(aid,{});key,revision=series(paths[aid])
        if aid in explicit:
            _,link=explicit[aid];key='declared:'+link.family_id;revision=link.revision;stages[aid]=link.stage_id
        if aid in platform_stages:stages[aid]=platform_stages[aid];basis[aid]='历史来源文件关联' if legacy else '平台阶段交接／稿件审核包'
        fid=view_id(tid+':'+key)
        family=families.setdefault(fid,{'id':fid,'task_id':tid,'title':re.sub(r'[（(]?v\d+.*$','',a['title'],flags=re.I).rstrip(' ·（('),
                   'stage_id':stages[aid],'stage_basis':('历史材料关联，非平台审核' if legacy else '平台审核／交接关联') if aid in platform_stages else '材料路径归类，非审核记录' if stage_for(a,doc)[1]=='navigation_hint' else '材料字段／结构关联','basis':basis[aid],'versions':[],'latest_order':order[aid]})
        if stages[aid]!='unassigned':family['stage_id']=stages[aid]
        version=next((x for x in family['versions'] if x['label']==revision),None)
        if version is None:
            version={'label':revision,'artifacts':[],'summary':'','status_claim':'','turn':None,'diff':[],
                     'plan':None,'order':order[aid],'association':'Agent 显式关联' if aid in explicit else '文件系列；版本关系待核对'}
            family['versions'].append(version)
        version['artifacts'].append({'id':aid,'title':a['title'],'media_type':a['media_type'],'path':paths[aid],
                                     'sha256':a['sha256'],'size_bytes':a['size_bytes']})
        if doc:
            version['summary']=short(doc.get('change_summary') or doc.get('conclusion') or doc.get('note') or doc.get('caveat'),1800)
            version['status_claim']=short(doc.get('status'),160)
        t=origin.get(aid)
        if t:
            version['turn']={'id':t['id'],'conversation_id':t['conversation_id'],'created_at':t['created_at'],
                             'user_text':short(t['user_text'],1000),'association':'首次可见对话引用'}
        if aid in plan_ids:version['plan']=plan_summary(doc)
        version['order']=max(order[aid],version['order']);family['latest_order']=order[aid]
        if doc.get('schema_version')=='pathoreason.innovation-proposal/1':
            try:
                proposal=InnovationProposal.model_validate(doc)
                if proposal.task_id not in tasks or any(x not in by_id for x in proposal.evidence_artifact_ids):raise ValueError('invalid_reference')
                # Explicit proposal identity wins over historical episode grouping.
                innovations[proposal.task_id].append({**proposal.model_dump(),'artifact_id':aid,'source_type':'artifact_report'})
            except ValueError:warnings.append(aid+'：创新方案字段或引用无效，保留原文件')
    for family in families.values():
        family['versions'].sort(key=lambda x:x['order'],reverse=True)
        prev=None
        for v in reversed(family['versions']):
            if v['plan']:
                if prev:v['diff']=plan_diff(prev,v['plan'])
                prev=v['plan']
            if v['turn']:
                changes.append({'id':family['id']+':'+str(v['order']),'task_id':family['task_id'],
                    'family_id':family['id'],'title':v['summary'] or family['title'],
                    'kind':'方案修订' if v['plan'] else '研究材料登记','turn':v['turn'],
                    'artifact_ids':[x['id'] for x in v['artifacts']],'diff':v['diff'],'order':v['order']})
    activity=[{'id':t['id'],'conversation_id':t['conversation_id'],'status':t['status'],'created_at':t['created_at'],
               'user_text':short(t['user_text'],240)} for t in turns if t['status'] in ACTIVE]
    for tid,task in tasks.items():
        mine=[f for f in families.values() if f['task_id']==tid]
        mine.sort(key=lambda f:f['latest_order'],reverse=True)
        plans=[(aid,plan_summary(docs[aid])) for aid in family_plans.get(tid,[])]
        task['plan']={**plans[-1][1],'artifact_id':plans[-1][0]} if plans else None
        task['family_ids']=[x['id'] for x in mine]
        task['latest_order']=max([x['latest_order'] for x in mine],default=-1)
        task['focus_stage']=next((x['stage_id'] for x in mine if x['stage_id'] in STAGE_IDS),'data')
        task['stages']=[{'id':sid,'title':title,'status':'unknown',
            'material_count':sum(f['stage_id']==sid for f in mine),
            'label':'已有关联材料' if any(f['stage_id']==sid for f in mine) else '尚无关联证据'} for sid,title in STAGES]
        task['innovations']=innovations[tid]
        task['reported_results']=[];task['exposures']=[]
        # Only the latest version of each report series, never sum superseded reports.
        for f in mine:
            for a in f['versions'][0]['artifacts']:
                d=docs.get(a['id'],{})
                task['reported_results'].extend(reported_results(d,a['id']))
                if d.get('test_exposure'):task['exposures'].append({'artifact_id':a['id'],'text':short(d['test_exposure'],1200)})
        task['execution_state']='unknown'
    task_list=sorted((t for t in tasks.values() if t['kind']!='historical_projection' or t['family_ids']),
                     key=lambda t:(t['id']!=common,t['latest_order']),reverse=True)
    # Default is the latest plan episode, not the largest version number across tasks.
    default=max(plan_ids,key=lambda a:order[a]) if plan_ids else None
    default_task=plan_ids[default] if default else next((t['id'] for t in task_list if t['kind']=='registered_task'),common)
    if outcomes:
        aggregate={'id':'project_outcomes','title':'当前项目成果','kind':'project_outcomes','basis':'历史成果与来源记录' if legacy else '平台阶段与作者审核记录',
            'parent_task_id':None,'code_revision':None,'snapshots':[],'plan':None,
            'family_ids':list(families),'latest_order':len(artifacts),'focus_stage':outcomes['stage_id'],
            'stages':[{'id':sid,'title':title,'status':outcomes['status'] if sid==outcomes['stage_id'] else 'unknown',
                'material_count':sum(len(v['artifacts']) for f in families.values() if f['stage_id']==sid for v in f['versions']),
                'label':outcomes['status_label'] if sid==outcomes['stage_id'] else '尚无关联材料' if legacy and not any(f['stage_id']==sid for f in families.values()) else '关联材料'} for sid,title in STAGES],
            'innovations':[p for t in task_list for p in t['innovations']],
            'reported_results':[p for t in task_list for p in t['reported_results']],
            'exposures':[p for t in task_list for p in t['exposures']],'execution_state':'unknown'}
        task_list.insert(0,aggregate);default_task='project_outcomes'
    payload={'outcomes':outcomes,'project_id':pid,'default_task_id':default_task,'tasks':task_list,
        'families':sorted(families.values(),key=lambda f:f['latest_order'],reverse=True),
        'changes':sorted(changes,key=lambda x:x['order'],reverse=True), 'activity':activity,
        'notices':warnings,'artifact_count':len(artifacts)}
    return ResearchWorkbenchView(**payload,revision=canonical_digest(payload),observed_at=now()).model_dump(mode='json')
