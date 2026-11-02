import {useEffect,useRef,useState} from 'react';
import {ComposerSettingIcon} from './ComposerSetting';
import {formalApi} from './FormalStudy';
import type {BudgetSettingsView,BudgetSettingsUpdate,StudyView} from './generated';
import './permissions.css';
import './budget-settings.css';

const errors:Record<string,string>={budget_revision_conflict:'项目额度已在其他窗口更新，请重新读取后修改。',goal_limit_revision_conflict:'目标或上限已变化，请重新读取后修改。',budget_below_usage:'项目上限不能低于已用量，请重新读取最新消耗。',goal_limit_below_usage:'目标回合上限不能低于已用回合，请重新读取。',goal_already_terminal:'目标已结束，请重新读取。',conversation_archived:'对话已归档，请恢复后修改。',idempotency_key_conflict:'保存请求已变化，请重新读取后修改。'};

export function BudgetSettings({cid,open,onOpen,readOnly,running,onSaved}:{cid:string;open:boolean;onOpen:(open:boolean)=>void;readOnly:boolean;running:boolean;onSaved:(v:StudyView)=>void}){
 const [value,setValue]=useState<BudgetSettingsView|null>(null),[turns,setTurns]=useState(''),[minutes,setMinutes]=useState(''),[goalTurns,setGoalTurns]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[stale,setStale]=useState(false);
 const dialog=useRef<HTMLDialogElement>(null),trigger=useRef<HTMLButtonElement>(null),requestKey=useRef(crypto.randomUUID()),generation=useRef(0);
 async function reload(){const epoch=++generation.current;setValue(null);setError('');setStale(false);try{const v=await formalApi<BudgetSettingsView>('/conversations/'+cid+'/budget-settings');if(epoch!==generation.current)return;setValue(v);setTurns(String(v.project.budget.max_turns));setMinutes(String(v.project.budget.max_wall_seconds/60));setGoalTurns(String(v.goal?.max_turns??8));requestKey.current=crypto.randomUUID();}catch(e){if(epoch===generation.current)setError(e instanceof Error?e.message:String(e));}}
 useEffect(()=>{if(open){dialog.current?.showModal();void reload();}return()=>{generation.current++;dialog.current?.close();};},[open,cid]);
 function close(){if(busy)return;dialog.current?.close();onOpen(false);trigger.current?.focus();}
 function edit(set:(v:string)=>void,v:string){set(v);requestKey.current=crypto.randomUUID();}
 const goal=value?.goal,editableGoal=Boolean(goal&&!goal.continued_in&&!['completed','cancelled'].includes(goal.state));
 const projectChanged=Boolean(value&&(Number(turns)!==value.project.budget.max_turns||Number(minutes)!==value.project.budget.max_wall_seconds/60));
 const goalChanged=Boolean(editableGoal&&Number(goalTurns)!==goal?.max_turns);
 async function save(){if(!value||busy||stale||readOnly)return;setBusy(true);setError('');const epoch=generation.current;
  const body:BudgetSettingsUpdate={request_key:requestKey.current,...(projectChanged?{project:{expected_revision:value.project.budget_revision??0,max_turns:Number(turns),max_wall_seconds:Number(minutes)===value.project.budget.max_wall_seconds/60?value.project.budget.max_wall_seconds:Math.round(Number(minutes)*60)}}:{}),...(goalChanged&&goal?{goal:{goal_id:goal.id,expected_revision:goal.limit_revision??0,max_turns:Number(goalTurns)}}:{})};
  try{const v=await formalApi<BudgetSettingsView>('/conversations/'+cid+'/budget-settings',{method:'PUT',body:JSON.stringify(body)});if(epoch!==generation.current)return;onSaved(v.project);dialog.current?.close();onOpen(false);trigger.current?.focus();}
  catch(e){if(epoch!==generation.current)return;const message=e instanceof Error?e.message:String(e);setError(errors[message]||message);if(errors[message])setStale(true);}
  finally{setBusy(false);}
 }
 return <>
  <button ref={trigger} type="button" className="permission-trigger composer-setting-trigger" aria-label="额度设置" aria-haspopup="dialog" aria-expanded={open} onClick={()=>onOpen(true)}><ComposerSettingIcon name="budget"/><span>额度</span></button>
  {open&&<dialog ref={dialog} className="permission-dialog budget-dialog" aria-labelledby="budget-settings-title" onCancel={e=>{e.preventDefault();close();}} onClick={e=>{if(e.target===dialog.current)close();}}>
   <header><h2 id="budget-settings-title">额度设置</h2><button type="button" className="icon-button" aria-label="关闭额度设置" disabled={busy} onClick={close}>×</button></header>
   <form className="dialog-body" onSubmit={e=>{e.preventDefault();void save();}}><div className="budget-scroll">
    {!value&&!error&&<p role="status">正在读取额度…</p>}
    {value&&<>
     <fieldset disabled={busy||readOnly||stale}><legend>项目额度</legend><p>项目内所有对话共用，填写调整后的总上限。</p><div className="budget-fields"><label>项目回合总上限<input type="number" required min={Math.max(1,value.project.used_turns)} max={1000} step={1} value={turns} onChange={e=>edit(setTurns,e.target.value)}/><span>已用 {value.project.used_turns} 回合 · 当前上限 {value.project.budget.max_turns}</span></label><label>Agent 时间总上限（分钟）<input type="number" required min={1} max={1440} step="any" value={minutes} onChange={e=>edit(setMinutes,e.target.value)}/><span>已用 {((value.project.used_budget_seconds??0)/60).toFixed(1)} 分钟 · 当前上限 {(value.project.budget.max_wall_seconds/60).toFixed(1)}</span></label></div></fieldset>
     <fieldset disabled={busy||readOnly||stale||!editableGoal}><legend>当前目标</legend>{goal?<><label>目标回合上限<input type="number" required min={Math.max(1,goal.turns_used??0)} max={40} step={1} value={goalTurns} onChange={e=>edit(setGoalTurns,e.target.value)}/><span className="budget-meta">已用 {goal.turns_used} 回合 · 当前上限 {goal.max_turns}</span></label><p>{goal.continued_in?'该目标已换窗，请在接续对话调整。':!editableGoal?'目标已结束。':'目标回合也计入项目总额度，最多可设为 40 回合。'}</p></>:<p>尚无持续目标。首次发送持续任务后可调整，默认 8 回合。</p>}</fieldset>
     <p>{running?'本回合继续按启动时的额度执行；修改对后续回合生效。':'已用量和历史记录保留。'} 已暂停或因额度停止的目标，保存后需点击“继续推进”。</p>
     {(value.history??[]).length>0&&<details><summary>最近修改记录</summary><ol className="budget-history">{(value.history??[]).map((item,i)=><li key={i}>{String(item.at).replace('T',' ').slice(0,19)} · 项目 {(item.project_after as {max_turns:number}).max_turns} 回合 / {((item.project_after as {max_wall_seconds:number}).max_wall_seconds/60).toFixed(1)} 分钟{item.goal_after?` · 目标 ${(item.goal_after as {max_turns:number}).max_turns} 回合`:''}</li>)}</ol></details>}
    </>}
    {readOnly&&<p>对话已归档，仅可查看。</p>}
    {error&&<div role="alert"><p className="status-text status-danger">{error}</p><button type="button" disabled={busy} onClick={()=>void reload()}>重新读取</button></div>}
    </div><footer><button type="button" disabled={busy} onClick={close}>取消</button><button className="primary-button" disabled={!value||busy||stale||readOnly||(!projectChanged&&!goalChanged)}>{busy?'正在保存…':'保存额度'}</button></footer>
   </form>
  </dialog>}
 </>;
}
