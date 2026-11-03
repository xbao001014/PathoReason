import {useEffect,useRef,useState} from 'react';
import {formalApi} from './FormalStudy';
import {ComposerSettingIcon} from './ComposerSetting';
import type {TrainingView,TrainingBudget,TrainingDecision} from './generated';
import './training.css';
import {statusTone} from './status';

const labels:Record<string,string>={draft:'待确认方案与预算',ready:'可以启动',queued:'排队中',running:'训练中',waiting_resource:'等待计算资源',stopping:'正在停止',stopped:'已停止',failed:'需要修复',budget_exhausted:'训练预算耗尽',needs_reconciliation:'执行结果待核对',completed:'矩阵已完成',cancelled:'已取消'};
const errors:Record<string,string>={training_preparation_turn_active:'Agent 正在完成方案准备，请等待本轮结束。',training_revision_conflict:'实验已更新，请重新打开后核对。',training_budget_below_consumption:'总上限不能低于已用量。',training_attempt_limit_below_usage:'尝试次数上限不能低于已发生的尝试。',training_budget_exhausted:'训练预算已耗尽，请先保存新的总上限。',training_gpu_budget_required:'使用 GPU 时需要设置 GPU 时长上限。',training_unknown_attempt_acknowledgement_required:'请先核对未知尝试；重新尝试会保留原预留消耗并创建新记录。'};
const hours=(s:number)=>Number((s/3600).toFixed(4));
export function TrainingPanel({cid,readOnly,openRequest}:{cid:string;readOnly:boolean;openRequest:number}){
 const [items,setItems]=useState<TrainingView[]>([]),[open,setOpen]=useState(false),[selected,setSelected]=useState(''),[draft,setDraft]=useState<TrainingView|null>(null);
 const [wall,setWall]=useState(''),[gpu,setGpu]=useState(''),[unit,setUnit]=useState(''),[retries,setRetries]=useState('0'),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const previousOpen=useRef(openRequest);
 useEffect(()=>{if(openRequest!==previousOpen.current){previousOpen.current=openRequest;void show();}},[openRequest]);
 const dialog=useRef<HTMLDialogElement>(null),generation=useRef(0),trigger=useRef<HTMLButtonElement>(null);
 async function load(){const epoch=generation.current;const v=await formalApi<TrainingView[]>('/conversations/'+cid+'/training');if(epoch===generation.current)setItems(v);return v;}
 useEffect(()=>{generation.current++;setItems([]);setOpen(false);setDraft(null);let live=true;void load().catch(()=>{});const timer=setInterval(()=>{if(live)void load().catch(()=>{});},4000);return()=>{live=false;generation.current++;clearInterval(timer);};},[cid]);
 useEffect(()=>{if(open)dialog.current?.showModal();return()=>dialog.current?.close();},[open]);
 function choose(v:TrainingView){setSelected(v.id);setDraft(v);setError('');const b=v.budget||v.plan.proposed_budget;setWall(b?String(hours(b.max_wall_seconds)):'');setGpu(b?String(hours(b.max_gpu_seconds)):v.plan.gpu_uuid?'':'0');setUnit(b?String(hours(b.max_unit_seconds)):'');setRetries(b?String(b.max_attempts_per_unit-1):'0');}
 async function show(id?:string){setOpen(true);setError('');setDraft(null);try{const v=await load();if(v.length)choose(v.find(x=>x.id===id)||v[0]);}catch(e){setError(String(e));}}
 function close(){if(busy)return;setOpen(false);trigger.current?.focus();}
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
 const pending=items.find(x=>x.status==='draft');const current=items.find(x=>x.id===selected)||draft;
 const active=current&&['queued','running','waiting_resource','stopping'].includes(current.status);
 return <>
  <button type="button" ref={trigger} className="permission-trigger composer-setting-trigger" aria-label="训练与预算" aria-haspopup="dialog" aria-expanded={open} onClick={()=>void show()}><ComposerSettingIcon name="budget"/><span>{pending?'确认训练方案':'训练'}</span></button>
  {open&&<dialog ref={dialog} className="permission-dialog training-dialog" aria-labelledby="training-title" onCancel={e=>{e.preventDefault();close();}} onClick={e=>{if(e.target===dialog.current)close();}}>
   <header><h2 id="training-title">训练与预算</h2><button type="button" className="icon-button" aria-label="关闭训练设置" disabled={busy} onClick={close}>×</button></header>
   <div className="dialog-body"><div className="training-scroll">
    {!items.length&&!error&&<p>Agent 完成实验方案准备后，可在这里一次确认训练方案和预算。训练预算独立于对话额度。</p>}
    {items.length>1&&<nav aria-label="选择实验" className="training-tabs">{items.map(v=><button type="button" key={v.id} disabled={busy} aria-current={v.id===selected?'true':undefined} onClick={()=>choose(v)}>{v.plan.title}</button>)}</nav>}
    {draft&&current&&<>
     <div className="training-summary"><h3>{draft.plan.title}</h3><span role="status" className={'status-text status-'+statusTone(current.status)}>{labels[current.status]||current.status}</span><p>{draft.plan.units.filter(x=>x.phase==='fit').length} 个训练单元 · {draft.plan.gpu_uuid?'单 GPU 顺序执行':'CPU 顺序执行'}</p><p>{draft.plan.protocol}</p><p>内存上限 {draft.plan.memory_gib??16} GiB</p></div>
     <details><summary>实验矩阵与评估范围</summary><p>{draft.plan.evaluation==='development_only'?'仅训练与验证，不读取封存测试。':draft.plan.evaluation==='previously_exposed'?'包含已暴露数据的评估，不作为独立盲测。':'完成全部训练单元后进行留出评估，保留测试暴露记录。'}</p><ul>{draft.plan.units.map(u=><li key={u.id}>{u.label} · {u.phase==='fit'?'训练':'评估'}{Object.keys(u.parameters||{}).length>0&&<span> · {Object.entries(u.parameters||{}).map(([k,v])=>k+'='+String(v)).join('，')}</span>}</li>)}</ul></details>
     <fieldset disabled={busy||readOnly}><legend>本实验训练预算</legend><p>填写累计总上限，失败、修复和重试共用；不扣除对话回合或 Agent 时间。</p>
      <div className="training-fields"><label>累计执行时长（小时）<input type="number" min="0.0001" step="any" value={wall} onChange={e=>setWall(e.target.value)}/><span>已用 {hours(current.used_wall_seconds)} 小时</span></label><label>累计 GPU 时长（GPU·小时）<input type="number" min="0" step="any" value={gpu} disabled={!draft.plan.gpu_uuid} onChange={e=>setGpu(e.target.value)}/><span>已用 {hours(current.used_gpu_seconds)} GPU·小时</span></label><label>单元最长执行时间（小时）<input type="number" min="0.0001" step="any" value={unit} onChange={e=>setUnit(e.target.value)}/></label><label>每单元最多重试次数<input type="number" min="0" max="9" step="1" value={retries} onChange={e=>setRetries(e.target.value)}/></label></div>
     </fieldset>
     <p>后台训练独立运行。停止生成或对话额度用完不会停止已授权训练；达到训练上限则停止并保留已有结果。</p>
     {!current.approval_ready&&<p>Agent 正在完成方案准备，本轮结束后可确认启动。</p>}
     {draft.status==='draft'&&<p>点击开始将授权上述矩阵、资源与预算，以及范围内的修复重试。科学审核与结论仍独立核验。</p>}
     {current.status==='needs_reconciliation'&&<p>旧控制进程已退出，执行结果未知。请核对日志与产物；重新尝试会保留旧预留消耗并创建新尝试。</p>}
     {current.error&&<p role="alert" className="status-text status-danger">{current.error}</p>}
     {current.attempts.length>0&&<details><summary>执行记录（{current.attempts.length} 次尝试）</summary><ul>{current.attempts.map(a=><li key={String(a.id)}>{String(a.unit_id)} · {labels[String(a.status)]||String(a.status)} · {Number(a.charged_seconds??a.observed_seconds??0).toFixed(1)} 秒{a.error?' · '+String(a.error):''}</li>)}</ul></details>}
    </>}
    {error&&<p role="alert" className="status-text status-danger">{error}</p>}
   </div><footer><button type="button" disabled={busy} onClick={close}>关闭</button>{draft&&!readOnly&&<>
    {draft.status==='draft'?<button type="button" className="primary-button" disabled={busy||!current?.approval_ready||!wall||!unit||(Boolean(draft.plan.gpu_uuid)&&!gpu)} onClick={()=>void act('authorize')}>按此方案开始训练</button>:<>
     <button type="button" disabled={busy||!wall||!unit} onClick={()=>void act('budget')}>保存训练预算</button>
     {active?<button type="button" className="primary-button" disabled={busy||current?.status==='stopping'} onClick={()=>void act('stop')}>停止训练</button>:current&&['stopped','failed','budget_exhausted','ready','needs_reconciliation'].includes(current.status)&&<button type="button" className="primary-button" disabled={busy} onClick={()=>void act('resume')}>{current.status==='needs_reconciliation'?'核对后重新尝试':'继续训练'}</button>}
    </>}
   </>}</footer></div>
  </dialog>}
 </>;
}
