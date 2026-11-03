import {useEffect,useRef,useState} from 'react';
import {formalApi} from './FormalStudy';
import type {TrainingView,TrainingBudget,TrainingDecision} from './generated';
import './training.css';
import {statusTone} from './status';
import {ComposerSelect} from './ComposerSelect';

export type TrainingSection='plan'|'budget'|'history';

const labels:Record<string,string>={draft:'待确认方案与预算',ready:'可以启动',queued:'排队中',running:'训练中',waiting_resource:'等待计算资源',stopping:'正在停止',stopped:'已停止',failed:'需要修复',budget_exhausted:'训练预算耗尽',needs_reconciliation:'执行结果待核对',completed:'矩阵已完成',cancelled:'已取消'};
const errors:Record<string,string>={training_preparation_turn_active:'Agent 正在完成方案准备，请等待本轮结束。',training_revision_conflict:'实验已更新，请载入最新方案后核对。',training_budget_below_consumption:'总上限不能低于已用量。',training_attempt_limit_below_usage:'尝试次数上限不能低于已发生的尝试。',training_budget_exhausted:'训练预算已耗尽，请先保存新的总上限。',training_gpu_budget_required:'使用 GPU 时需要设置 GPU 时长上限。',training_unknown_attempt_acknowledgement_required:'请先核对未知尝试；重新尝试会保留原预留消耗并创建新记录。'};
const hours=(s:number)=>Number((s/3600).toFixed(4));
export function TrainingPanel({cid,readOnly,onStatus,section,onSectionChange}:{cid:string;readOnly:boolean;onStatus:(status:string)=>void;section:TrainingSection;onSectionChange:(section:TrainingSection)=>void}){
 const [items,setItems]=useState<TrainingView[]>([]),[selected,setSelected]=useState(''),[draft,setDraft]=useState<TrainingView|null>(null);
 const [wall,setWall]=useState(''),[gpu,setGpu]=useState(''),[unit,setUnit]=useState(''),[retries,setRetries]=useState('0'),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const generation=useRef(0);
 async function load(){const epoch=generation.current;const v=await formalApi<TrainingView[]>('/conversations/'+cid+'/training');if(epoch===generation.current)setItems(v);return v;}
 useEffect(()=>{generation.current++;setItems([]);setDraft(null);setSelected('');let live=true;void load().catch(()=>{});const timer=setInterval(()=>{if(live)void load().catch(()=>{});},4000);return()=>{live=false;generation.current++;clearInterval(timer);};},[cid]);
 useEffect(()=>{if(items.length&&!items.some(v=>v.id===selected))choose(items.find(v=>v.status==='draft')||items[0]);},[items,selected]);
 const display=items.find(v=>v.id===selected)||items.find(v=>v.status==='draft')||items[0];
 useEffect(()=>{onStatus(display?.status||'');},[display?.status,onStatus]);
 function choose(v:TrainingView){setSelected(v.id);setDraft(v);setError('');const b=v.budget||v.plan.proposed_budget;setWall(b?String(hours(b.max_wall_seconds)):'');setGpu(b?String(hours(b.max_gpu_seconds)):v.plan.gpu_uuid?'':'0');setUnit(b?String(hours(b.max_unit_seconds)):'');setRetries(b?String(b.max_attempts_per_unit-1):'0');}
 async function act(action:TrainingDecision['action']){
  if(!draft||readOnly||busy)return;const epoch=generation.current;setBusy(true);setError('');
  try{const previous=draft.budget||draft.plan.proposed_budget;
   const seconds=(text:string,old:number|undefined)=>old!==undefined&&text===String(hours(old))?old:Number(text)*3600;
   const budget:TrainingBudget={max_wall_seconds:seconds(wall,previous?.max_wall_seconds),max_gpu_seconds:seconds(gpu,previous?.max_gpu_seconds),max_unit_seconds:seconds(unit,previous?.max_unit_seconds),max_attempts_per_unit:Number(retries)+1};
   if(['authorize','budget'].includes(action)&&(!Number.isFinite(budget.max_wall_seconds)||budget.max_wall_seconds<=0||!Number.isFinite(budget.max_gpu_seconds)||budget.max_gpu_seconds<0||!Number.isFinite(budget.max_unit_seconds)||budget.max_unit_seconds<=0||budget.max_unit_seconds>budget.max_wall_seconds||!Number.isInteger(budget.max_attempts_per_unit)||budget.max_attempts_per_unit<1||budget.max_attempts_per_unit>10))throw new Error('请填写有效预算：单元时长不能超过累计上限，重试次数为 0–9 的整数。');
   const body:TrainingDecision={expected_revision:draft.revision,request_key:'training_'+crypto.randomUUID().replaceAll('-',''),action,...(action==='resume'&&draft.status==='needs_reconciliation'?{acknowledge_unknown:true}:{}),...(['authorize','budget'].includes(action)?{budget}:{})};
   const v=await formalApi<TrainingView>('/conversations/'+cid+'/training/'+draft.id,{method:'POST',body:JSON.stringify(body)});if(epoch!==generation.current)return;choose(v);await load();
  }catch(e){if(epoch!==generation.current)return;const message=e instanceof Error?e.message:String(e);setError(errors[message]||message);}finally{setBusy(false);}
 }
 const current=items.find(x=>x.id===selected)||draft;
 const stale=Boolean(current&&draft&&current.revision!==draft.revision);
 const active=current&&['queued','running','waiting_resource','stopping'].includes(current.status);
 if(!items.length&&!error)return null;
 const fit=draft?.plan.units.filter(x=>x.phase==='fit').length||0,evaluate=draft?.plan.units.filter(x=>x.phase==='evaluate').length||0;
 return <section className="training-inline" aria-label="训练方案与预算">
  {items.length>1&&<label className="training-picker"><span>实验</span><ComposerSelect label="选择实验" variant="form" value={selected} disabled={busy} options={items.map(v=>({value:v.id,label:v.plan.title}))} onChange={id=>{const item=items.find(v=>v.id===id);if(item)choose(item);}}/></label>}
  {draft&&current&&<>
   <header className="training-summary">{items.length===1&&<h3>{draft.plan.title}</h3>}<div className="training-summary-meta"><span role="status" className={'status-text status-'+statusTone(current.status)}>{labels[current.status]||current.status}</span><span>{fit} 个训练 · {evaluate} 个评估</span></div></header>
   <div className="training-module" hidden={section!=='plan'}>
    <div className="training-plan-grid">
     <section className="training-card"><h4>执行范围</h4><dl><div><dt>方式</dt><dd>{draft.plan.gpu_uuid?'单 GPU 顺序执行':'CPU 顺序执行'}</dd></div><div><dt>内存上限</dt><dd>{draft.plan.memory_gib??16} GiB</dd></div><div><dt>开发输入</dt><dd>{draft.plan.inputs?.filter(f=>f.role==='development').length||0} 份</dd></div><div><dt>封存输入</dt><dd>{draft.plan.inputs?.filter(f=>f.role==='sealed').length||0} 份</dd></div></dl></section>
     <section className="training-card"><h4>评估范围</h4><p>{draft.plan.evaluation==='development_only'?'仅训练与验证，不读取封存测试。':draft.plan.evaluation==='previously_exposed'?'包含已暴露数据的评估，不作为独立盲测。':'完成全部训练单元后进行留出评估，保留测试暴露记录。'}</p>{draft.plan.gpu_uuid&&<details className="training-device"><summary>训练设备</summary><p>{draft.plan.gpu_uuid}</p></details>}</section>
    </div>
    <details className="training-matrix"><summary>实验矩阵（{draft.plan.units.length} 个单元）</summary><p>{draft.plan.protocol}</p><ul>{draft.plan.units.map(u=><li key={u.id}><strong>{u.label}</strong><span>{u.phase==='fit'?'训练':'评估'}{Object.keys(u.parameters||{}).length>0&&' · '+Object.entries(u.parameters||{}).map(([k,v])=>k+'='+String(v)).join('，')}</span></li>)}</ul></details>
    <footer><button type="button" onClick={()=>onSectionChange('budget')}>{draft.status==='draft'&&!readOnly?'设置预算并确认':'查看训练预算'}</button>{current.attempts.length>0&&<button type="button" onClick={()=>onSectionChange('history')}>查看执行记录</button>}</footer>
   </div>
   <div className="training-module" hidden={section!=='budget'}>
    <fieldset disabled={busy||readOnly||stale}><legend>本实验训练预算</legend><p className="training-note">累计总上限，失败、修复和重试共用；与 Agent 额度分开计量。</p>
     <div className="training-fields"><label>累计执行时长（小时）<input type="number" min="0.0001" step="any" value={wall} onChange={e=>setWall(e.target.value)}/><span>已用 {hours(current.used_wall_seconds)} 小时</span></label><label>累计 GPU 时长（GPU·小时）<input type="number" min="0" step="any" value={gpu} disabled={!draft.plan.gpu_uuid} onChange={e=>setGpu(e.target.value)}/><span>已用 {hours(current.used_gpu_seconds)} GPU·小时</span></label><label>单元最长执行时间（小时）<input type="number" min="0.0001" step="any" value={unit} onChange={e=>setUnit(e.target.value)}/></label><label>每单元最多重试次数<input type="number" min="0" max="9" step="1" value={retries} onChange={e=>setRetries(e.target.value)}/></label></div>
    </fieldset>
    <div className="training-consequences"><p>停止生成或 Agent 额度用完不会停止已授权训练；达到训练上限则停止并保留结果。</p>
     {draft.status==='draft'&&<p>开始训练将授权当前矩阵、资源、预算及范围内的修复重试；持续模式按原项目额度接续核验，科学审核独立进行。</p>}
     {current.status==='needs_reconciliation'&&<p>旧执行结果未知。请核对日志与产物；重新尝试会保留旧预留消耗并创建新记录。</p>}
    </div>
    {!stale&&!readOnly&&<footer>{draft.status==='draft'?<button type="button" className="primary-button" disabled={busy||!current.approval_ready||!wall||!unit||(Boolean(draft.plan.gpu_uuid)&&!gpu)} onClick={()=>void act('authorize')}>按此方案开始训练</button>:<>
     <button type="button" disabled={busy||!wall||!unit} onClick={()=>void act('budget')}>保存训练预算</button>
     {active?<button type="button" className="primary-button" disabled={busy||current.status==='stopping'} onClick={()=>void act('stop')}>停止训练</button>:['stopped','failed','budget_exhausted','ready','needs_reconciliation'].includes(current.status)&&<button type="button" className="primary-button" disabled={busy} onClick={()=>void act('resume')}>{current.status==='needs_reconciliation'?'核对后重新尝试':'继续训练'}</button>}
    </>}</footer>}
   </div>
   <div className="training-module" hidden={section!=='history'}>
    {current.attempts.length>0?<ol className="training-attempts" aria-label="执行记录">{current.attempts.map(a=><li key={String(a.id)}><strong>{String(a.unit_id)}</strong><span className={'status-text status-'+statusTone(String(a.status))}>{labels[String(a.status)]||String(a.status)}</span><span className="training-attempt-time">{Number(a.charged_seconds??a.observed_seconds??0).toFixed(1)} 秒</span>{Boolean(a.error)&&<p className="status-text status-danger">{String(a.error)}</p>}</li>)}</ol>:<p className="training-empty">暂无执行记录</p>}
   </div>
   {!current.approval_ready&&current.status==='draft'&&<p className="training-notice">Agent 正在完成方案准备，本轮结束后可确认启动。</p>}
   {current.error&&<p role="alert" className="status-text status-danger">{current.error}</p>}
  </>}
  {stale&&current&&<div className="training-stale"><p role="status">方案或预算已更新，载入最新版本后再操作。</p><button type="button" disabled={busy} onClick={()=>choose(current)}>载入最新方案</button></div>}
  {error&&<p role="alert" className="status-text status-danger">{error}</p>}
 </section>;
}
