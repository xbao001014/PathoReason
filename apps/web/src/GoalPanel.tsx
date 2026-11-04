import {StatusPanelResize} from './StatusPanelResize';
import {useResearchStage} from './ResearchStageContext';
import {ManuscriptReview,type ManuscriptView} from './ManuscriptReview';
import {OutputRecovery} from './OutputRecovery';
import {useEffect,useId,useRef,useState,type KeyboardEvent} from 'react';
import type {GoalView,ContextView,GoalControl} from './generated';
type ReasoningEffort=NonNullable<GoalControl['reasoning_effort']>;
import {formalApi} from './FormalStudy';
import {statusTone} from './status';
import './goals.css';
import {TrainingPanel,type TrainingSection} from './TrainingPanel';
type PanelModule='review'|'goal'|TrainingSection;
const moduleLabels:Record<PanelModule,[string,string]>={review:['稿件审核','审核'],goal:['任务进度','任务'],plan:['训练方案','方案'],budget:['训练预算','预算'],history:['执行记录','记录']};

const labels:Record<string,string>={active:'持续推进',paused:'已暂停',blocked:'遇到阻塞',waiting_input:'需要选择',waiting:'等待作业',completed:'Agent 已报告完成',budget_exhausted:'额度已用完',cancelled:'目标已取消'};
const contextReasons=new Set(['context_window_requires_compaction_or_handoff','context_operation_unresolved','context_budget_exhausted','context_usage_unverified','context_recovery_failed','context_recovery_running']);
const reasons:Record<string,string>={manuscript_review_pending:'稿件材料已就绪，请切换到本栏“稿件审核”处理当前版本。',manuscript_author_review_required:'稿件阶段仍需完成作者审核。',manuscript_evidence_changed:'稿件审核材料发生变化，请核对版本并重新提交审核。',manuscript_review_changed:'稿件审核状态已更新，请查看当前节点。',stage_handoff_ready:'本阶段已交付，请在研究阶段栏切换并进入下一阶段会话。',stage_workflow_completed:'五阶段交付完成；科学审核与作者批准仍独立记录。',stage_changed:'阶段状态已更新，请核对当前阶段后重新提交交接。',stage_training_not_terminal:'后台训练仍需完成或核对，暂不能结束当前阶段。',runtime_output_limit:'模型达到单次输出上限。已保留已有成果和消耗，自动接续已停止；可调整输出上限或思考强度后恢复。',training_budget_exhausted:'训练预算或单元尝试次数已达到上限，请在训练设置中核对并调整；已有消耗保留。',training_stopped:'训练已停止，可在训练设置中查看记录并决定是否恢复。',training_needs_reconciliation:'训练控制进程已退出，需在训练设置中核对日志和产物；未知尝试的预留消耗保留。',training_cancelled:'实验已取消，已有结果和消耗保留。',goal_permissions_updated:'工具权限已更新。旧权限阻塞需按新设置重新核对，点击“核对权限并继续”推进。',budget_updated:'额度已更新，可以继续推进。',context_window_requires_compaction_or_handoff:'上下文不足以容纳下一轮，目标和已完成进展已保留。请压缩后继续，或在同一项目换窗接续。',context_operation_unresolved:'上次压缩结果尚未确认。先核对原生结果；不会重复提交压缩。',context_usage_unverified:'摘要已返回，但压缩后的上下文尚未核验。可重新核对或同项目换窗。',context_budget_exhausted:'本项目压缩次数已用完，可在同项目换窗接续；原消耗保持不变。',context_recovery_failed:'压缩未完成，可在剩余额度内重试，或同项目换窗接续。',context_recovery_running:'正在压缩并核验上下文，目标推进已暂缓。',goal_continued_elsewhere:'本目标已在同项目的新对话接续，历史和已用额度保留。',goal_turn_limit:'达到当前回合上限，可调整额度后继续；审核反馈保存后重新计数，项目总预算保持有效。',acceptance_budget_exhausted:'项目预算已耗尽，自动推进已停止。',goal_scope_blocked:'本轮范围仅允许对话，检查点未能保存，自动接续已停止。',goal_no_progress:'连续两轮没有可核验的新进展，自动推进已停止。',goal_evidence_changed:'已记录的成果发生变化，需要核对版本。',goal_turn_failed:'上一轮未成功结束，请先核对执行状态。',goal_wait_run_changed:'等待中的作业绑定发生变化，需要核对。',goal_wait_timeout:'等待作业超时，已停止自动接续。',single_turn_selected:'已切换为单步执行。'};

export function GoalPanel({cid,readOnly,running,onChange,onError,onNavigate,onBudget,budgetRefresh,onOutputSettings}:{cid:string;readOnly:boolean;running:boolean;onChange:()=>void;onError:(e:unknown)=>void;onNavigate:(cid:string)=>void;onBudget:()=>void;budgetRefresh:number;onOutputSettings:(model:string,effort:ReasoningEffort,limit:number)=>void}){
 const {value:stage,loaded:stageLoaded,updateReview}=useResearchStage();
 const manuscript=stage?.stage_id==='manuscript'&&stage.conversation_id===cid;
 const showTraining=stageLoaded&&!manuscript;
 const review=manuscript?stage.manuscript_review as unknown as ManuscriptView|undefined:undefined;
 const reviewTab=useRef<HTMLButtonElement>(null),heading=useRef<HTMLButtonElement>(null),reviewPanel=useRef<HTMLDivElement>(null);
 const controlInFlight=useRef(false);
 const [trainingStatus,setTrainingStatus]=useState('');
 const [context,setContext]=useState<ContextView|null>(null);
 const bodyId=useId(),[expanded,setExpanded]=useState(false);
 const [module,setModule]=useState<PanelModule>('goal'),moduleChosen=useRef(false);
 const [goal,setGoal]=useState<GoalView|null>(null),[busy,setBusy]=useState(false),[editing,setEditing]=useState(false),[objective,setObjective]=useState('');
 useEffect(()=>{let live=true;setGoal(null);setEditing(false);async function refresh(){try{const v=await formalApi<GoalView|null>('/conversations/'+cid+'/goal');if(live)setGoal(v);}catch{/* Conversation removal is handled by the parent. */}}refresh();const timer=setInterval(refresh,2000);return()=>{live=false;clearInterval(timer);};},[cid,budgetRefresh]);
 useEffect(()=>{setExpanded(false);setModule('goal');moduleChosen.current=false;},[cid]);
 useEffect(()=>{setEditing(false);},[cid,goal?.id]);
 const needsContext=contextReasons.has(goal?.reason||'');
 const needsAttention=needsContext||goal?.state==='blocked'||goal?.state==='budget_exhausted';
 useEffect(()=>{if(needsAttention){setExpanded(true);setModule('goal');}else if(review?.pending){setExpanded(true);setModule('review');}},[needsAttention,review?.pending?.id]);
 useEffect(()=>{if(manuscript){setTrainingStatus('');setModule(needsAttention?'goal':'review');moduleChosen.current=false;}},[manuscript]);
 useEffect(()=>{const open=(event:Event)=>{if((event as CustomEvent).detail!==cid||!review)return;setExpanded(true);setModule('review');requestAnimationFrame(()=>{reviewTab.current?.focus({preventScroll:true});if(reviewPanel.current)reviewPanel.current.scrollTop=0;});};window.addEventListener('pathoreason:open-manuscript-review',open);return()=>window.removeEventListener('pathoreason:open-manuscript-review',open);},[cid,Boolean(review)]);
 useEffect(()=>{let live=true;setContext(null);if(!needsContext)return;async function refresh(){try{const res=await fetch('/api/v1/conversations/'+cid+'/context');if(res.ok&&live)setContext(await res.json());}catch{}}refresh();const timer=setInterval(refresh,2500);return()=>{live=false;clearInterval(timer);};},[cid,needsContext,budgetRefresh]);
 async function recover(action:'compact'|'reconcile'|'new_conversation'){
  if(!goal||busy)return;setBusy(true);
  try{const result=await formalApi<GoalView>('/conversations/'+cid+'/goal/context-recovery',{method:'POST',body:JSON.stringify({goal_id:goal.id,expected_revision:goal.revision,action})});setGoal(result);onChange();if(result.conversation_id!==cid)onNavigate(result.conversation_id);}
  catch(e){onError(e);try{setGoal(await formalApi<GoalView|null>('/conversations/'+cid+'/goal'));}catch{}}
  finally{setBusy(false);}
 }
 async function control(action:'pause'|'resume'|'revise'|'cancel',effort?:ReasoningEffort,limit?:number,model?:string,resumeScope?:'standard'|'inspection'){
  if(!goal||busy||controlInFlight.current)return;controlInFlight.current=true;setBusy(true);
  try{const result=await formalApi<GoalView>('/conversations/'+cid+'/goal',{method:'POST',body:JSON.stringify({expected_revision:goal.revision,action,...(resumeScope?{resume_scope:resumeScope}:{}),...(effort?{reasoning_effort:effort}:{}),...(limit?{output_limit_tokens:limit}:{}),...(action==='revise'?{objective}:{})})});setGoal(result);setEditing(false);if(model&&effort&&limit)onOutputSettings(model,effort,limit);onChange();}
  catch(e){onError(e);try{setGoal(await formalApi<GoalView|null>('/conversations/'+cid+'/goal'));}catch{}}
  finally{controlInFlight.current=false;setBusy(false);}
 }

 useEffect(()=>{if(!manuscript&&!moduleChosen.current&&trainingStatus&&(!goal||['completed','cancelled'].includes(goal.state)))setModule('plan');},[manuscript,trainingStatus,goal?.id,goal?.state]);
 function chooseModule(value:PanelModule){moduleChosen.current=true;setModule(value);}
 function navigateModules(event:KeyboardEvent<HTMLDivElement>){
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  const tabs=Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')),current=tabs.indexOf(document.activeElement as HTMLButtonElement);
  if(current<0)return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(current+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  tabs[next].click();tabs[next].focus();
 }
 const trainingBlocked=goal?.state==='blocked'&&['training_budget_exhausted','training_stopped','training_needs_reconciliation','training_cancelled'].includes(goal?.reason||'');
 const platformBlocked=goal?.blocker?.capability==='training_execution';
 const progressing=['active','waiting'].includes(goal?.state||''),canResume=['paused','blocked'].includes(goal?.state||'')&&!needsContext&&!goal?.continued_in&&!platformBlocked&&!trainingBlocked;
 const projectExhausted=context?.project_turns_remaining===0||context?.project_agent_seconds_remaining===0;
 const pendingContext=goal?.reason==='context_recovery_running'||context?.operations?.some(o=>o.status==='running');
 const reconcile=context?.operations?.some(o=>o.status==='recovery_required')||context?.source==='post_compaction_bytes_estimate'||goal?.reason==='context_usage_unverified'||goal?.reason==='context_operation_unresolved';
 const statusLabel=goal?.reason==='goal_permissions_updated'?'权限待复核':goal?.continued_in?'已换窗接续':needsContext?(pendingContext?'正在恢复上下文':'上下文待恢复'):goal?.completion_scope==='answer_only'?'已回答':labels[goal?.state||''];
 const compactStatus=goal?.state==='completed'&&goal?.completion_scope!=='answer_only'?'报告完成':goal?.state==='cancelled'?'已取消':goal?.state==='budget_exhausted'?'额度用完':statusLabel;
 const modules:PanelModule[]=[...(review?['review' as const]:[]),...(goal?['goal' as const]:[]),...(showTraining&&trainingStatus?['plan' as const,'budget' as const,'history' as const]:[])];
 const selectedModule=modules.includes(module)?module:modules[0]||'goal';
 const summary=goal?.scope_recovery?'此前选项将本轮限制为仅对话，文件操作未开放；工具自动批准设置仍然有效。':goal?(reasons[goal.reason||'']||goal.summary||goal.objective):'';
 const panelLabel=manuscript?'稿件审核与任务进度':'任务进度与训练';
 const reviewStatus=review?.status==='awaiting_review'?'待你审阅':review?.index===5?'交付已确认':running||goal?.state==='active'?'正在准备':'待准备';
 const windowUsed=goal?(goal.turns_used??0)-(goal.turn_window?.start_turns??0):0;
 return <section className={'goal-panel'+(manuscript?' goal-panel-manuscript':'')} aria-label={panelLabel} data-expanded={expanded} hidden={!goal&&!review&&!trainingStatus} onKeyDown={e=>{if(manuscript&&e.key==='Escape'&&!e.defaultPrevented){setExpanded(false);heading.current?.focus();}}}>
  <div className="goal-body" id={bodyId} hidden={!expanded}>
   <StatusPanelResize expanded={expanded} bodyId={bodyId}/>
   <div className="goal-module-tabs" role="tablist" aria-label={manuscript?'审核与任务分类':'任务与训练分类'} onKeyDown={navigateModules} style={{gridTemplateColumns:`repeat(${Math.max(1,modules.length)},minmax(0,1fr))`}}>{modules.map(value=><button key={value} id={bodyId+'-tab-'+value} ref={value==='review'?reviewTab:undefined} type="button" role="tab" aria-label={moduleLabels[value][0]} aria-selected={selectedModule===value} aria-controls={bodyId+(value==='goal'?'-goal':value==='review'?'-review':'-training')} tabIndex={selectedModule===value?0:-1} onClick={()=>chooseModule(value)}><span className="goal-tab-full">{moduleLabels[value][0]}</span><span className="goal-tab-short" aria-hidden="true">{moduleLabels[value][1]}</span></button>)}</div>
   {review&&<div className="goal-module-panel goal-review-panel" role="tabpanel" id={bodyId+'-review'} aria-labelledby={bodyId+'-tab-review'} hidden={selectedModule!=='review'} ref={reviewPanel}>
    <ManuscriptReview key={cid} cid={cid} value={review} readOnly={readOnly} running={running} onError={onError} onUpdate={next=>{updateReview(next);onChange();}}/>
   </div>}
   <div className="goal-module-panel" role="tabpanel" id={bodyId+'-goal'} aria-labelledby={bodyId+'-tab-goal'} hidden={selectedModule!=='goal'}>
   {goal&&<div className="goal-progress-details">
   <p className="goal-summary">{summary}</p>
   {goal.turn_window&&<p>本次审核反馈后已用 {windowUsed} / {goal.max_turns} 回合 · 本目标累计 {goal.turns_used} 回合</p>}
   {goal.state==='blocked'&&!goal.scope_recovery&&goal.blocker&&goal.reason!=='goal_permissions_updated'&&<p role="status">{{platform:'平台能力待接通',permission:'工具权限不足',input:'需要补充输入',resource:'资源条件不足'}[goal.blocker.kind]}：{goal.blocker.required_action}</p>}
   {!readOnly&&needsContext&&<div className="goal-recovery" aria-label="上下文恢复"><div className="goal-actions"><button disabled={busy||running||projectExhausted||Boolean(pendingContext)||!context||(!reconcile&&(context.compaction_remaining??0)<=0)} onClick={()=>recover(reconcile?'reconcile':'compact')}>{busy||pendingContext?'正在核验…':reconcile?'核对压缩并继续':'压缩并继续'}</button><button disabled={busy||running||projectExhausted||Boolean(pendingContext)} onClick={()=>recover('new_conversation')}>同项目换窗并继续</button></div><p>{projectExhausted?'项目额度已用完，需先补充项目预算；压缩或换窗均不会增加额度。':'压缩会调用模型；两种方式均保留目标和原额度，核验后接续。'}</p></div>}
   <div className="goal-actions">{!readOnly&&(projectExhausted||goal.state==='budget_exhausted')&&<button onClick={onBudget}>额度设置</button>}{!readOnly&&progressing&&<button disabled={busy} title="暂停 Agent 推进；已提交的外部作业需单独停止" onClick={()=>control('pause')}>暂停</button>}{!readOnly&&canResume&&goal.reason!=='runtime_output_limit'&&!goal.scope_recovery&&<button disabled={busy||running} onClick={()=>control('resume',goal.suggested_reasoning_effort||undefined)}>{goal.reason==='goal_permissions_updated'?'核对权限并继续':goal.suggested_reasoning_effort==='none'?'关闭思考重试':goal.suggested_reasoning_effort==='low'?'低思考强度重试':'继续推进'}</button>}{!readOnly&&!goal.continued_in&&!['completed','cancelled'].includes(goal.state)&&<button disabled={busy} aria-expanded={editing} onClick={()=>{setObjective(goal.objective);setEditing(!editing);}}>调整目标</button>}</div>

   {goal.scope_recovery&&<div className="goal-scope-recovery"><p>沿用此前任务范围与最新要求；保留当前权限、已用额度和独立训练门禁。</p>{!readOnly&&canResume&&goal.reason!=='runtime_output_limit'&&<div className="goal-actions"><button disabled={busy||running} onClick={()=>control('resume',undefined,undefined,undefined,goal.scope_recovery?.execution_scope)}>{goal.scope_recovery.execution_scope==='inspection'?'按原只读范围继续':'按原任务范围继续'}</button></div>}</div>}
   {goal.reason==='runtime_output_limit'&&<OutputRecovery key={goal.last_turn_id} turnId={goal.last_turn_id} busy={busy||running} readOnly={readOnly||!canResume} onResume={(effort,limit,model)=>control('resume',effort,limit,model,goal.scope_recovery?.execution_scope)}/>}
   {goal.continued_in&&<div className="goal-actions"><button onClick={()=>onNavigate(goal.continued_in!)}>打开接续对话</button></div>}
   {editing?<form className="goal-editor" onSubmit={e=>{e.preventDefault();control('revise');}}><label>目标<textarea required maxLength={16000} value={objective} onChange={e=>setObjective(e.target.value)}/></label><p>保存后暂停，点击“继续推进”应用新目标；仍计入原项目预算。</p><div className="goal-actions"><button type="button" onClick={()=>setEditing(false)}>取消</button><button disabled={busy} type="submit">保存</button></div></form>:<details className="goal-details"><summary>目标与验收</summary>{goal.objective!==summary&&<p>{goal.objective}</p>}{(goal.completion_criteria??[]).length>0&&<ul>{(goal.completion_criteria??[]).map((s,i)=><li key={i}>{s}</li>)}</ul>}{goal.next_action&&goal.state!=='completed'&&<p>下一步：{goal.next_action}</p>}{goal.state==='completed'&&goal.completion_scope==='evidence_bytes_verified'&&<p>Agent 已报告完成并关联可核验材料；科学审核仍独立进行。</p>}{!readOnly&&!goal.continued_in&&!['completed','cancelled'].includes(goal.state)&&<div className="goal-actions"><button disabled={busy} title="结束本目标，保留成果、失败及预算记录；外部作业需单独停止" onClick={()=>control('cancel')}>取消目标</button></div>}</details>}
   </div>}
   </div>
   {showTraining&&<div className="goal-module-panel" role="tabpanel" id={bodyId+'-training'} aria-labelledby={bodyId+'-tab-'+(selectedModule==='goal'||selectedModule==='review'?'plan':selectedModule)} hidden={selectedModule==='goal'||selectedModule==='review'}>
    <TrainingPanel key={cid} cid={cid} readOnly={readOnly} onStatus={setTrainingStatus} section={selectedModule==='goal'||selectedModule==='review'?'plan':selectedModule} onSectionChange={chooseModule}/>
   </div>}
  </div>
  <div className="goal-heading">
   <button className="goal-heading-toggle" ref={heading} type="button" aria-expanded={expanded} aria-controls={bodyId} aria-label={(expanded?'收起':'展开')+panelLabel} onClick={()=>setExpanded(value=>!value)}>
    {review&&<><span className={'goal-state goal-review-state status-text status-'+statusTone(review.status==='awaiting_review'?'pending':review.index===5?'completed':reviewStatus==='正在准备'?'running':'unknown')} title={'稿件审核 · '+review.label+' · '+reviewStatus}><span className="goal-state-dot" aria-hidden="true"/><span>稿件审核 · {reviewStatus}</span></span><span className="goal-review-node" title={review.label}>{review.label}</span></>}
    {showTraining&&trainingStatus&&<span className={'goal-state status-text status-'+statusTone(trainingStatus)}><span className="goal-state-dot" aria-hidden="true"/><span>{{draft:'待确认训练方案',ready:'训练待启动',queued:'训练排队中',running:'训练中',waiting_resource:'等待训练资源',stopping:'训练正在停止',stopped:'训练已停止',failed:'训练需要修复',budget_exhausted:'训练预算耗尽',needs_reconciliation:'训练结果待核对',completed:'训练矩阵已完成',cancelled:'训练已取消'}[trainingStatus]||trainingStatus}</span></span>}
    {goal&&<>{(!manuscript||['paused','blocked','budget_exhausted','cancelled'].includes(goal.state)||needsContext)&&<span className={'goal-state status-text status-'+statusTone(goal.state)} title={statusLabel}><span className="goal-state-dot" aria-hidden="true"/><span>{compactStatus}</span></span>}<span className="goal-usage" title={'本目标累计 '+goal.turns_used+' 回合；项目总额度与已用时间保留'}>{goal.turn_window?'本节点 ':''}{windowUsed} / {goal.max_turns} 回合</span></>}
    <svg className="goal-heading-chevron" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6"/></svg>
   </button>
  </div>
 </section>;
}
