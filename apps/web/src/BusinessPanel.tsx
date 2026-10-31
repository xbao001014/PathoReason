import {useEffect,useRef,useState} from 'react';
import type {BusinessView} from './generated';
import {statusTone} from './status';
const labels:Record<string,string>={not_started:'未开始',admitted:'已接入',awaiting_review:'待确认方案',running:'执行中',completed:'执行完成',needs_repair:'需要恢复',needs_reconciliation:'需要核对',budget_exhausted:'预算已耗尽',stopped:'已停止'};
const operations:Record<string,string>={intake:'任务接入',plan:'方案生成',revise:'反馈修订',execute:'执行矩阵',recover:'恢复任务',stop:'停止任务'};
export function Info({text}:{text:string}){return <span className="info-wrap"><button type="button" className="info-button" aria-label={text}>i</button><span role="tooltip" className="info-tooltip">{text}</span></span>;}
export function BusinessPanel({pid,workbench=false,onChange,onPrompt,onArtifact}:{pid:string;workbench?:boolean;onChange:()=>void;onPrompt:(s:string)=>void;onArtifact:(id:string)=>void}){
 const [data,setData]=useState<BusinessView|null>(null),[error,setError]=useState('');const revision=useRef(''),changed=useRef(onChange);changed.current=onChange;
 useEffect(()=>{let live=true,pending=false;setData(null);setError('');revision.current='';async function refresh(){if(pending)return;pending=true;try{const r=await fetch('/api/v1/research-projects/'+pid+'/business');if(!r.ok)throw new Error('任务状态读取失败');const b:BusinessView=await r.json();if(!live)return;setData(b);setError('');if(revision.current!==b.revision){revision.current=b.revision;changed.current();}}catch(e){if(live)setError((e as Error).message);}finally{pending=false;}}refresh();const timer=setInterval(refresh,4000);return()=>{live=false;clearInterval(timer);};},[pid]);
 if(error)return <div className="business-error" role="status">{error}</div>;
 if(!data||data.status==='not_started')return null;
 const status=labels[data.status]||data.status;const current=data.revisions?.at(-1);
 const phases=[{title:'任务接入',status:'completed'},
 {title:'方案确认',status:data.status==='admitted'?'not_started':data.status==='awaiting_review'?'pending':'completed'},
 {title:'矩阵执行',status:['admitted','awaiting_review'].includes(data.status)?'not_started':data.status},
 {title:'成果归档',status:data.artifact_ids?.length?'completed':'not_started'}];
 const phaseIndex=data.status==='admitted'?0:data.status==='awaiting_review'?1:data.status==='completed'?3:2;
 const artifactOrder=['summary','matrix','metrics','ledger'];
 const artifactIds=[...(data.artifact_ids||[])].sort((a,b)=>artifactOrder.findIndex(k=>a.endsWith('_'+k))-artifactOrder.findIndex(k=>b.endsWith('_'+k)));
 const hasAction=Boolean(data.available_operations?.some(op=>['plan','execute','recover'].includes(op)));
 return <section className={'business-card '+(workbench?'business-expanded':'business-compact')} aria-label="合成验证任务">
  <header className="business-heading">
   <div className="business-heading-main"><h2>{data.question||'合成 MIL 验证'}</h2><div className="business-context"><span>合成验证</span><Info text="仅执行独立 CPU 合成数据。执行完成不代表科学结论成立；真实实验保持原有门禁。"/></div></div>
   <span className={'status-badge business-status status-'+statusTone(data.status)}>{status}</span>
  </header>
  {data.run_id&&<div className="business-metrics" aria-label="执行进度">
   <div className="metric-primary"><div className="metric-value"><strong>{data.completed_units||0}</strong><span>/{data.total_units||8}</span></div><span className="metric-label">已完成单元</span></div>
   <div className="metric-support"><div><span>累计耗时</span><strong>{(data.used_worker_seconds||0).toFixed(1)}<small> 秒</small></strong><Info text="各 worker 墙钟持续时间的累计值，非进程 CPU 时间。"/></div><span className="matrix-spec">2 候选 × 2 折 × 2 种子</span></div>
  </div>}
  {current&&data.status==='awaiting_review'&&<div className="plan-review"><dl><div><dt>基线</dt><dd>AB_MIL · 0.0002</dd></div><div className="plan-primary"><dt>候选学习率</dt><dd>{current.learning_rate}</dd></div><div><dt>训练轮次</dt><dd>1 epoch</dd></div><div><dt>预算上限</dt><dd>600 秒 · 1 次恢复</dd></div></dl>{current.feedback&&<blockquote>{current.feedback}</blockquote>}</div>}
  {workbench&&<ol className="business-stages" aria-label="研究阶段">{phases.map((phase,index)=><li key={phase.title} className={index===phaseIndex?'phase-current':''} aria-current={index===phaseIndex?'step':undefined}><span className="phase-number">{String(index+1).padStart(2,'0')}</span><strong>{phase.title}</strong><span className={'status-text status-'+statusTone(phase.status)}>{({completed:'已完成',pending:'待确认',not_started:'未开始',running:'进行中'} as Record<string,string>)[phase.status]||labels[phase.status]||phase.status}</span></li>)}</ol>}
  {!workbench&&Boolean(data.available_operations?.length)&&<div className="business-controls">{data.available_operations?.includes('plan')&&<button className="primary-button" onClick={()=>onPrompt('请为当前合成任务生成完整矩阵方案，先展示方案供我确认。')}>生成方案</button>}{data.available_operations?.includes('execute')&&<><button className="primary-button" onClick={()=>onPrompt('确认当前方案，请执行独立 CPU 合成验证，保持完整矩阵和预算限制。')}>确认并执行</button><button className="outline-button" onClick={()=>onPrompt('请修订当前方案：')}>反馈修订</button></>}{data.available_operations?.includes('recover')&&<button className="primary-button" onClick={()=>onPrompt('请核对当前异常，在原账本和剩余预算范围内恢复该合成任务。')}>核对并恢复</button>}{data.available_operations?.includes('stop')&&<button className="outline-button" onClick={()=>onPrompt('请停止当前合成研究任务，保留已产出证据和预算记录。')}>停止研究任务</button>}</div>}
  {artifactIds.length>0&&<div className="business-artifacts">{artifactIds.map(id=><button key={id} className={id.endsWith('_summary')&&!hasAction?'primary-button':id.endsWith('_ledger')?'quiet-button':'outline-button'} onClick={()=>onArtifact(id)}>{id.endsWith('_summary')?'查看验证报告':id.endsWith('_matrix')?'矩阵图':id.endsWith('_metrics')?'指标表':'执行账本'}</button>)}</div>}
  {workbench&&<div className="business-evidence"><dl className="business-facts"><div><dt>科学审核</dt><dd className="status-text status-neutral">未进行</dd></div><div><dt>独立验证</dt><dd className="status-text status-warning">未进行</dd></div><div><dt>投稿就绪</dt><dd className="status-text status-neutral">否</dd></div></dl><details><summary>修订与执行记录 <span>{data.actions?.length||0}</span></summary><ol className="business-history">{data.actions?.map(a=><li key={a.id}><strong>{operations[a.operation]||a.operation}</strong><span>{a.workflow_status?labels[a.workflow_status]||a.workflow_status:a.status==='succeeded'?'工具成功':a.status==='waiting_for_workflow'?'等待执行结果':a.status}</span><time>{new Date((data.events?.find(e=>e.action_id===a.id)?.at||0)*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</time></li>)}</ol>{Boolean(data.revisions?.length)&&<ol className="revision-history" aria-label="方案修订">{data.revisions?.map((r,index)=><li key={r.action_id}><strong>方案 {index+1} · 候选学习率 {r.learning_rate}</strong>{r.feedback&&<p>{r.feedback}</p>}</li>)}</ol>}</details></div>}
 </section>;
}
