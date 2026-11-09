"""Read-only adapter for the versioned CESC development/manuscript archive.

Only registered, hash-checked project artifacts are consumed. No paths from a
report are opened, and no workflow, approval, task, or training record is created.
"""
from collections import defaultdict
import math
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import quote
from pydantic import BaseModel, Field
from .workbench_outcomes import lines, text


class Performance(BaseModel):
    round: Literal['A','B']
    condition: Literal['raw','removal','instance','shared']
    n_cells: int = Field(gt=0,le=5000)
    mean_fold_seed_rmse: float = Field(ge=0,allow_inf_nan=False)
    mean_fold_seed_mae_at_rmse_selected_epoch: float = Field(ge=0,allow_inf_nan=False)


class Cell(BaseModel):
    round: Literal['A','B']
    condition: Literal['raw','removal','instance','shared']
    fold: int = Field(ge=1,le=100)
    seed: int = Field(ge=0)
    best_epoch: int = Field(ge=1)
    val_rmse: float = Field(ge=0,allow_inf_nan=False)
    val_mae: float = Field(ge=0,allow_inf_nan=False)


class Candidate(BaseModel):
    id: str = Field(max_length=100)
    label: str = Field(max_length=200)
    device: str = Field(max_length=100)
    cells: int = Field(gt=0,le=5000)
    raw: float = Field(ge=0,allow_inf_nan=False)
    removal: float = Field(ge=0,allow_inf_nan=False)
    full: float = Field(ge=0,allow_inf_nan=False)
    gain: float = Field(allow_inf_nan=False)
    positive_seeds: int = Field(ge=0,le=100)
    positive_folds: int = Field(ge=0,le=100)


def legacy_outcomes(pid, artifacts, docs):
    """Return the existing outcome view shape plus a qualified historical matrix."""
    arts=[a for a in artifacts if a.get('project_id',pid)==pid and a.get('source_ref',{}).get('adapter')=='auto_research.evidence_file']
    def schema(key,value):
        matches=[a for a in arts if docs.get(a['id'],{}).get(key)==value]
        return matches[0] if len(matches)==1 else None
    conclusion=schema('schema_version','cesc-study-conclusions/1')
    pipeline=schema('schema','cesc-manuscript-delivery/2')
    if not conclusion or not pipeline:return None,{},[]
    notices=[]
    def named(*names):
        matches=[a for a in arts if PurePosixPath(a['relative_path']).name in names]
        if len(matches)>1:
            notices.append('历史文件存在多个候选，未自动选择：'+names[0]);return None
        return matches[0] if matches else None
    def material(a,role='report',title=None):
        if not a:return None
        return {'id':a['id'],'title':title or a['title'],'role':role,'media_type':a['media_type'],
                'size_bytes':a['size_bytes'],'sha256':a['sha256'],
                'url':'/api/v1/research-projects/'+quote(pid,safe='')+'/artifacts/'+quote(a['id'],safe='')+'/content'}
    c=docs[conclusion['id']];p=docs[pipeline['id']]
    stages={conclusion['id']:'analysis',pipeline['id']:'delivery'}
    all_materials=[]
    roles=[(('CESC_manuscript.pdf',),'pdf','论文 PDF · 审阅稿','delivery'),
           (('manuscript.md',),'manuscript','实例线性上下文残差 · 英文论文','delivery'),
           (('CESC_manuscript_source.zip',),'source_package','论文源码与图表完整包','delivery'),
           (('method-v2-style.png','method.png'),'figure','实例上下文残差方法图','innovation'),
           (('result.png','results.png'),'figure','两轮开发复验结果图','analysis'),
           (('dataset_overview.png',),'figure','真实切片总览','data'),
           (('dataset_regions.png',),'figure','真实切片 ROI','data'),
           (('performance.csv',),'report','两轮复验性能汇总','analysis'),
           (('cell_metrics.csv',),'report','逐单元结果明细','innovation_runs'),
           (('registered_intervals.csv',),'report','注册配对比较区间','analysis'),
           (('README.md',),'report','原案例交付说明','delivery'),
           (('AUTHOR_CHECKLIST.json',),'report','作者待确认事项','delivery'),
           (('references.bib',),'report','论文参考文献','delivery')]
    for names,role,title,stage in roles:
        a=named(*names)
        if a:all_materials.append(material(a,role,title));stages[a['id']]=stage
    results=named('results-data.json');matrix=None
    if results:
        try:
            d=docs[results['id']]
            if not 0<len(d['cells'])<=5000 or not 0<len(d['performance'])<=100:raise ValueError('matrix_size')
            cells=[Cell.model_validate(x).model_dump() for x in d['cells']]
            performance=[Performance.model_validate(x).model_dump() for x in d['performance']]
            keys=[(x['round'],x['condition'],x['fold'],x['seed']) for x in cells]
            if len(set(keys))!=len(keys):raise ValueError('duplicate_cell')
            groups=defaultdict(list)
            for row in cells:groups[(row['round'],row['condition'])].append(row)
            if set(groups)!={(r['round'],r['condition']) for r in performance} or len(performance)!=len(groups):raise ValueError('group_mismatch')
            for r in performance:
                group=groups[(r['round'],r['condition'])]
                if len(group)!=r['n_cells']:raise ValueError('cell_count')
                for key,metric in [('mean_fold_seed_rmse','val_rmse'),('mean_fold_seed_mae_at_rmse_selected_epoch','val_mae')]:
                    if not math.isclose(sum(x[metric] for x in group)/len(group),r[key],rel_tol=1e-10,abs_tol=1e-12):raise ValueError('mean_mismatch')
            for filename,rows,model in [('cell_metrics.csv',cells,Cell),('performance.csv',performance,Performance)]:
                a=named(filename)
                if not a:raise ValueError('missing_source')
                references=[s for s in d['sources'] if PurePosixPath(s['path']).name==filename]
                if len(references)!=1 or references[0]['sha256']!=a['sha256']:raise ValueError('source_mismatch')
                original=[model.model_validate(x).model_dump() for x in docs[a['id']]['_legacy_csv']]
                if original!=rows:raise ValueError('csv_mismatch')
            candidates=[Candidate.model_validate(x).model_dump() for x in d.get('exploration',[])[:30]]
            matrix={'source':material(results),'performance':performance,'cells':cells,'candidates':candidates,
                    'patients':c.get('execution',{}).get('patients') if type(c.get('execution',{}).get('patients')) is int else None,'scope':'development',
                    'execution_authority':False,'candidate_basis':'历史候选探索快照；不同设备，不与两轮复验合并计数'}
            stages[results['id']]='analysis'
        except (ValueError,KeyError,TypeError,OverflowError):
            notices.append('历史实验矩阵与来源校验未通过，保留原文件入口，未展示数值。')
    checklist=named('AUTHOR_CHECKLIST.json')
    questions=lines(docs.get(checklist['id'],{}).get('pending')) if checklist else []
    # Never reinterpret older source declarations as newly approved platform gates.
    label='审阅稿 · 待作者最终确认' if p.get('status')=='review_delivery_ready' and p.get('author_approved_exact_artifacts') is False else '历史稿件 · 状态见原文件'
    status='awaiting_review' if p.get('status')=='review_delivery_ready' and p.get('author_approved_exact_artifacts') is False else 'unknown'
    common={'gate':'legacy','status':status,'status_label':label,'summary':text(c.get('headline')),
            'created_at':text(p.get('updated_at')),'key_findings':lines(c.get('conclusions')),'limitations':lines(c.get('limits')),
            'open_questions':questions,'changes':[],'conversation_id':None}
    content={**common,'id':'legacy_content','title':'稿件正文与配套材料','materials':[x for x in all_materials if x['role'] not in {'pdf','source_package'}]}
    delivery={**common,'id':'legacy_delivery','title':'论文交付文件','materials':[x for x in all_materials if x['role'] in {'pdf','source_package'}]}
    return {'origin':'legacy_archive','stage_id':'delivery','stage_label':'稿件与交付','node_label':'历史审阅稿',
            'status':status,'status_label':label,'conversation_id':None,'summary':text(c.get('headline')),
            'key_findings':lines(c.get('conclusions')),'limitations':lines(c.get('limits')),'open_questions':questions,
            'next_action':'核对原作者清单与具体稿件版本。','figures':[x for x in all_materials if x['role']=='figure'],
            'content':content,'delivery':delivery,'pending':None,'history':[], 'handoffs':[],
            'legacy_matrix':matrix,'source_materials':[material(conclusion),material(pipeline)],
            'source_goal_achieved':c.get('goal_achieved_dev') if type(c.get('goal_achieved_dev')) is bool else None,'submission_ready':p.get('submission_ready') if type(p.get('submission_ready')) is bool else None,
            'revision':{'research':None,'manuscript':None}},stages,notices
