import {useEffect,useId,useState} from 'react';
import type {GoalView} from './generated';
import {formalApi} from './FormalStudy';
import {statusTone} from './status';
import './goals.css';

const labels:Record<string,string>={active:'持续推进',paused:'已暂停',blocked:'遇到阻塞',waiting_input:'需要选择',waiting:'等待作业',completed:'Agent 已报告完成',budget_exhausted:'额度已用完',cancelled:'目标已取消'};
const reasons:Record<string,string>={goal_turn_limit:'达到本目标的回合上限，可调整目标额度后继续；项目总预算保持有效。',acceptance_budget_exhausted:'项目预算已耗尽，自动推进已停止。',goal_no_progress:'连续两轮没有可核验的新进展，自动推进已停止。',goal_evidence_changed:'已记录的成果发生变化，需要核对版本。',goal_turn_failed:'上一轮未成功结束，请先核对执行状态。',goal_wait_run_changed:'等待中的作业绑定发生变化，需要核对。',goal_wait_timeout:'等待作业超时，已停止自动接续。',single_turn_selected:'已切换为单步执行。'};

export function GoalPanel({cid,readOnly,running,onChange,onError}:{cid:string;readOnly:boolean;running:boolean;onChange:()=>void;onError:(e:unknown)=>void}){
 const bodyId=useId(),[expanded,setExpanded]=useState(false);
 const [goal,setGoal]=useState<GoalView|null>(null),[busy,setBusy]=useState(false),[editing,setEditing]=useState(false),[objective,setObjective]=useState(''),[limit,setLimit]=useState(8);
 useEffect(()=>{let live=true;setGoal(null);setEditing(false);async function refresh(){try{const v=await formalApi<GoalView|null>('/conversations/'+cid+'/goal');if(live)setGoal(v);}catch{/* Conversation removal is handled by the parent. */}}refresh();const timer=setInterval(refresh,2000);return()=>{live=false;clearInterval(timer);};},[cid]);
 useEffect(()=>{setExpanded(false);setEditing(false);},[cid,goal?.id]);
 async function control(action:'pause'|'resume'|'revise'|'cancel'){
  if(!goal||busy)return;setBusy(true);
  try{const result=await formalApi<GoalView>('/conversations/'+cid+'/goal',{method:'POST',body:JSON.stringify({expected_revision:goal.revision,action,...(action==='revise'?{objective,max_turns:limit}:{})})});setGoal(result);setEditing(false);onChange();}
  catch(e){onError(e);try{setGoal(await formalApi<GoalView|null>('/conversations/'+cid+'/goal'));}catch{}}
  finally{setBusy(false);}
 }
 if(!goal)return null;
 const progressing=['active','waiting'].includes(goal.state),canResume=['paused','blocked'].includes(goal.state);
 const statusLabel=goal.completion_scope==='answer_only'?'已回答':labels[goal.state];
 const compactStatus=goal.state==='completed'&&goal.completion_scope!=='answer_only'?'报告完成':goal.state==='cancelled'?'已取消':goal.state==='budget_exhausted'?'额度用完':statusLabel;
 return <section className="goal-panel" aria-label="当前目标" data-expanded={expanded}>
  <div className="goal-body" id={bodyId} hidden={!expanded}>
   <p className="goal-summary">{reasons[goal.reason||'']||goal.summary||goal.objective}</p>
   <div className="goal-actions">{!readOnly&&progressing&&<button disabled={busy} title="暂停 Agent 推进；已提交的外部作业需单独停止" onClick={()=>control('pause')}>暂停</button>}{!readOnly&&canResume&&<button disabled={busy||running} onClick={()=>control('resume')}>继续推进</button>}{!readOnly&&!['completed','cancelled'].includes(goal.state)&&<button disabled={busy} aria-expanded={editing} onClick={()=>{setObjective(goal.objective);setLimit(goal.max_turns??8);setEditing(!editing);}}>调整目标</button>}</div>
   {editing?<form className="goal-editor" onSubmit={e=>{e.preventDefault();control('revise');}}><label>目标<textarea required maxLength={16000} value={objective} onChange={e=>setObjective(e.target.value)}/></label><label>本目标回合上限<input required type="number" min={Math.max(1,goal.turns_used??0)} max={40} value={limit} onChange={e=>setLimit(Number(e.target.value))}/></label><p>保存后暂停，点击“继续推进”应用新目标；仍计入原项目预算。</p><div className="goal-actions"><button type="button" onClick={()=>setEditing(false)}>取消</button><button disabled={busy} type="submit">保存</button></div></form>:<div className="goal-details"><p>{goal.objective}</p>{(goal.completion_criteria??[]).length>0&&<ul>{(goal.completion_criteria??[]).map((s,i)=><li key={i}>{s}</li>)}</ul>}{goal.next_action&&goal.state!=='completed'&&<p>下一步：{goal.next_action}</p>}{goal.state==='completed'&&goal.completion_scope==='evidence_bytes_verified'&&<p>Agent 已报告完成并关联可核验材料；科学审核仍独立进行。</p>}{!readOnly&&!['completed','cancelled'].includes(goal.state)&&<div className="goal-actions"><button disabled={busy} title="结束本目标，保留成果、失败及预算记录；外部作业需单独停止" onClick={()=>control('cancel')}>取消目标</button></div>}</div>}
  </div>
  <div className="goal-heading">
   <span className={'goal-state status-text status-'+statusTone(goal.state)} role="status" aria-label={statusLabel} title={statusLabel}><span className="goal-state-dot" aria-hidden="true"/><span>{compactStatus}</span></span>
   <span className="goal-usage">{goal.turns_used} / {goal.max_turns} 回合</span>
   <button className="goal-toggle" type="button" aria-expanded={expanded} aria-controls={bodyId} aria-label={expanded?'收起目标进度':'展开目标进度'} title={expanded?'收起目标进度':'展开目标进度'} onClick={()=>setExpanded(value=>!value)}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6"/></svg></button>
  </div>
 </section>;
}
