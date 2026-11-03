import {useEffect,useId,useState} from 'react';
import type {GoalView,ContextView} from './generated';
import {formalApi} from './FormalStudy';
import {statusTone} from './status';
import './goals.css';
import {TrainingPanel} from './TrainingPanel';

const labels:Record<string,string>={active:'持续推进',paused:'已暂停',blocked:'遇到阻塞',waiting_input:'需要选择',waiting:'等待作业',completed:'Agent 已报告完成',budget_exhausted:'额度已用完',cancelled:'目标已取消'};
const contextReasons=new Set(['context_window_requires_compaction_or_handoff','context_operation_unresolved','context_budget_exhausted','context_usage_unverified','context_recovery_failed','context_recovery_running']);
const reasons:Record<string,string>={training_budget_exhausted:'训练预算或单元尝试次数已达到上限，请在训练设置中核对并调整；已有消耗保留。',training_stopped:'训练已停止，可在训练设置中查看记录并决定是否恢复。',training_needs_reconciliation:'训练控制进程已退出，需在训练设置中核对日志和产物；未知尝试的预留消耗保留。',training_cancelled:'实验已取消，已有结果和消耗保留。',goal_permissions_updated:'工具权限已更新。旧权限阻塞需按新设置重新核对，点击“核对权限并继续”推进。',budget_updated:'额度已更新，可以继续推进。',context_window_requires_compaction_or_handoff:'上下文不足以容纳下一轮，目标和已完成进展已保留。请压缩后继续，或在同一项目换窗接续。',context_operation_unresolved:'上次压缩结果尚未确认。先核对原生结果；不会重复提交压缩。',context_usage_unverified:'摘要已返回，但压缩后的上下文尚未核验。可重新核对或同项目换窗。',context_budget_exhausted:'本项目压缩次数已用完，可在同项目换窗接续；原消耗保持不变。',context_recovery_failed:'压缩未完成，可在剩余额度内重试，或同项目换窗接续。',context_recovery_running:'正在压缩并核验上下文，目标推进已暂缓。',goal_continued_elsewhere:'本目标已在同项目的新对话接续，历史和已用额度保留。',goal_turn_limit:'达到本目标的回合上限，可调整目标额度后继续；项目总预算保持有效。',acceptance_budget_exhausted:'项目预算已耗尽，自动推进已停止。',goal_no_progress:'连续两轮没有可核验的新进展，自动推进已停止。',goal_evidence_changed:'已记录的成果发生变化，需要核对版本。',goal_turn_failed:'上一轮未成功结束，请先核对执行状态。',goal_wait_run_changed:'等待中的作业绑定发生变化，需要核对。',goal_wait_timeout:'等待作业超时，已停止自动接续。',single_turn_selected:'已切换为单步执行。'};

export function GoalPanel({cid,readOnly,running,onChange,onError,onNavigate,onBudget,budgetRefresh}:{cid:string;readOnly:boolean;running:boolean;onChange:()=>void;onError:(e:unknown)=>void;onNavigate:(cid:string)=>void;onBudget:()=>void;budgetRefresh:number}){
 const [trainingStatus,setTrainingStatus]=useState('');
 const [context,setContext]=useState<ContextView|null>(null);
 const bodyId=useId(),[expanded,setExpanded]=useState(false);
 const [goal,setGoal]=useState<GoalView|null>(null),[busy,setBusy]=useState(false),[editing,setEditing]=useState(false),[objective,setObjective]=useState('');
 useEffect(()=>{let live=true;setGoal(null);setEditing(false);async function refresh(){try{const v=await formalApi<GoalView|null>('/conversations/'+cid+'/goal');if(live)setGoal(v);}catch{/* Conversation removal is handled by the parent. */}}refresh();const timer=setInterval(refresh,2000);return()=>{live=false;clearInterval(timer);};},[cid,budgetRefresh]);
 useEffect(()=>{setExpanded(false);},[cid]);
 useEffect(()=>{setEditing(false);},[cid,goal?.id]);
 const needsContext=contextReasons.has(goal?.reason||'');
 useEffect(()=>{if(needsContext||goal?.state==='blocked'||goal?.state==='budget_exhausted')setExpanded(true);},[goal?.reason,goal?.state,goal?.blocker?.kind,needsContext]);
 useEffect(()=>{let live=true;setContext(null);if(!needsContext)return;async function refresh(){try{const res=await fetch('/api/v1/conversations/'+cid+'/context');if(res.ok&&live)setContext(await res.json());}catch{}}refresh();const timer=setInterval(refresh,2500);return()=>{live=false;clearInterval(timer);};},[cid,needsContext,budgetRefresh]);
 async function recover(action:'compact'|'reconcile'|'new_conversation'){
  if(!goal||busy)return;setBusy(true);
  try{const result=await formalApi<GoalView>('/conversations/'+cid+'/goal/context-recovery',{method:'POST',body:JSON.stringify({goal_id:goal.id,expected_revision:goal.revision,action})});setGoal(result);onChange();if(result.conversation_id!==cid)onNavigate(result.conversation_id);}
  catch(e){onError(e);try{setGoal(await formalApi<GoalView|null>('/conversations/'+cid+'/goal'));}catch{}}
  finally{setBusy(false);}
 }
 async function control(action:'pause'|'resume'|'revise'|'cancel',effort?:'low'|'none'){
  if(!goal||busy)return;setBusy(true);
  try{const result=await formalApi<GoalView>('/conversations/'+cid+'/goal',{method:'POST',body:JSON.stringify({expected_revision:goal.revision,action,...(effort?{reasoning_effort:effort}:{}),...(action==='revise'?{objective}:{})})});setGoal(result);setEditing(false);onChange();}
  catch(e){onError(e);try{setGoal(await formalApi<GoalView|null>('/conversations/'+cid+'/goal'));}catch{}}
  finally{setBusy(false);}
 }

 const trainingBlocked=goal?.state==='blocked'&&['training_budget_exhausted','training_stopped','training_needs_reconciliation','training_cancelled'].includes(goal?.reason||'');
 const platformBlocked=goal?.blocker?.capability==='training_execution';
 const progressing=['active','waiting'].includes(goal?.state||''),canResume=['paused','blocked'].includes(goal?.state||'')&&!needsContext&&!goal?.continued_in&&!platformBlocked&&!trainingBlocked;
 const projectExhausted=context?.project_turns_remaining===0||context?.project_agent_seconds_remaining===0;
 const pendingContext=goal?.reason==='context_recovery_running'||context?.operations?.some(o=>o.status==='running');
 const reconcile=context?.operations?.some(o=>o.status==='recovery_required')||context?.source==='post_compaction_bytes_estimate'||goal?.reason==='context_usage_unverified'||goal?.reason==='context_operation_unresolved';
 const statusLabel=goal?.reason==='goal_permissions_updated'?'权限待复核':goal?.continued_in?'已换窗接续':needsContext?(pendingContext?'正在恢复上下文':'上下文待恢复'):goal?.completion_scope==='answer_only'?'已回答':labels[goal?.state||''];
 const compactStatus=goal?.state==='completed'&&goal?.completion_scope!=='answer_only'?'报告完成':goal?.state==='cancelled'?'已取消':goal?.state==='budget_exhausted'?'额度用完':statusLabel;
 return <section className="goal-panel" aria-label="任务进度与训练" data-expanded={expanded} hidden={!goal&&!trainingStatus}>
  <div className="goal-body" id={bodyId} hidden={!expanded}>
   <TrainingPanel key={cid} cid={cid} readOnly={readOnly} onStatus={setTrainingStatus}/>
   {goal&&<div className="goal-progress-details">
   <p className="goal-summary">{reasons[goal.reason||'']||goal.summary||goal.objective}</p>
   {goal.state==='blocked'&&goal.blocker&&goal.reason!=='goal_permissions_updated'&&<p role="status">{{platform:'平台能力待接通',permission:'工具权限不足',input:'需要补充输入',resource:'资源条件不足'}[goal.blocker.kind]}：{goal.blocker.required_action}</p>}
   {!readOnly&&needsContext&&<div className="goal-recovery" aria-label="上下文恢复"><div className="goal-actions"><button disabled={busy||running||projectExhausted||Boolean(pendingContext)||!context||(!reconcile&&(context.compaction_remaining??0)<=0)} onClick={()=>recover(reconcile?'reconcile':'compact')}>{busy||pendingContext?'正在核验…':reconcile?'核对压缩并继续':'压缩并继续'}</button><button disabled={busy||running||projectExhausted||Boolean(pendingContext)} onClick={()=>recover('new_conversation')}>同项目换窗并继续</button></div><p>{projectExhausted?'项目额度已用完，需先补充项目预算；压缩或换窗均不会增加额度。':'压缩会调用模型；两种方式均保留目标和原额度，核验后接续。'}</p></div>}
   <div className="goal-actions">{!readOnly&&(projectExhausted||goal.state==='budget_exhausted')&&<button onClick={onBudget}>额度设置</button>}{!readOnly&&progressing&&<button disabled={busy} title="暂停 Agent 推进；已提交的外部作业需单独停止" onClick={()=>control('pause')}>暂停</button>}{!readOnly&&canResume&&<button disabled={busy||running} onClick={()=>control('resume',goal.suggested_reasoning_effort||undefined)}>{goal.reason==='goal_permissions_updated'?'核对权限并继续':goal.suggested_reasoning_effort==='none'?'关闭思考重试':goal.suggested_reasoning_effort==='low'?'低思考强度重试':'继续推进'}</button>}{!readOnly&&!goal.continued_in&&!['completed','cancelled'].includes(goal.state)&&<button disabled={busy} aria-expanded={editing} onClick={()=>{setObjective(goal.objective);setEditing(!editing);}}>调整目标</button>}</div>

   {goal.continued_in&&<div className="goal-actions"><button onClick={()=>onNavigate(goal.continued_in!)}>打开接续对话</button></div>}
   {editing?<form className="goal-editor" onSubmit={e=>{e.preventDefault();control('revise');}}><label>目标<textarea required maxLength={16000} value={objective} onChange={e=>setObjective(e.target.value)}/></label><p>保存后暂停，点击“继续推进”应用新目标；仍计入原项目预算。</p><div className="goal-actions"><button type="button" onClick={()=>setEditing(false)}>取消</button><button disabled={busy} type="submit">保存</button></div></form>:<div className="goal-details"><p>{goal.objective}</p>{(goal.completion_criteria??[]).length>0&&<ul>{(goal.completion_criteria??[]).map((s,i)=><li key={i}>{s}</li>)}</ul>}{goal.next_action&&goal.state!=='completed'&&<p>下一步：{goal.next_action}</p>}{goal.state==='completed'&&goal.completion_scope==='evidence_bytes_verified'&&<p>Agent 已报告完成并关联可核验材料；科学审核仍独立进行。</p>}{!readOnly&&!goal.continued_in&&!['completed','cancelled'].includes(goal.state)&&<div className="goal-actions"><button disabled={busy} title="结束本目标，保留成果、失败及预算记录；外部作业需单独停止" onClick={()=>control('cancel')}>取消目标</button></div>}</div>}
   </div>}
  </div>
  <div className="goal-heading">
   <button className="goal-heading-toggle" type="button" aria-expanded={expanded} aria-controls={bodyId} aria-label={expanded?'收起任务进度与训练':'展开任务进度与训练'} onClick={()=>setExpanded(value=>!value)}>
    {trainingStatus&&<span className={'goal-state status-text status-'+statusTone(trainingStatus)}><span className="goal-state-dot" aria-hidden="true"/><span>{{draft:'待确认训练方案',ready:'训练待启动',queued:'训练排队中',running:'训练中',waiting_resource:'等待训练资源',stopping:'训练正在停止',stopped:'训练已停止',failed:'训练需要修复',budget_exhausted:'训练预算耗尽',needs_reconciliation:'训练结果待核对',completed:'训练矩阵已完成',cancelled:'训练已取消'}[trainingStatus]||trainingStatus}</span></span>}
    {goal&&<><span className={'goal-state status-text status-'+statusTone(goal.state)} title={statusLabel}><span className="goal-state-dot" aria-hidden="true"/><span>{compactStatus}</span></span><span className="goal-usage">{goal.turns_used} / {goal.max_turns} 回合</span></>}
    <svg className="goal-heading-chevron" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6"/></svg>
   </button>
  </div>
 </section>;
}
