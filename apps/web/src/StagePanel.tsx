import {useEffect,useId,useRef,useState} from 'react';
import type {ResearchStageView,StageAssign} from './generated';
import {formalApi} from './FormalStudy';
import {ComposerSelect} from './ComposerSelect';
import './stages.css';
import {statusTone} from './status';
const stages=[['data','数据准备'],['baseline','基线方案确定与基线实验'],['innovation','创新方案确认与创新实验'],['analysis','结果分析与科学审核'],['manuscript','稿件部分']] as const;
const errors:Record<string,string>={stage_changed:'阶段已更新，请查看最新交接。',stage_goal_changed:'目标已调整，请先完成当前交接。',stage_active_turn:'当前回合尚未结束，请稍后切换。',stage_training_not_terminal:'训练仍在运行或结果待核对，暂不能切换阶段。',stage_evidence_changed:'交接成果已变化，请先在原阶段更新交接。',stage_workflow_already_registered:'项目已关联阶段，请打开当前阶段对话。'};
type Package={agent_report?:{summary?:string;decisions?:string[];limitations?:string[];open_questions?:string[];next_action?:string};verified_evidence?:{kind:string;id?:string;path?:string}[];digest?:string};
export function StagePanel({cid,readOnly,running,onNavigate,onChange,onError}:{cid:string;readOnly:boolean;running:boolean;onNavigate:(id:string)=>void;onChange:()=>void;onError:(e:unknown)=>void}){
 const [value,setValue]=useState<ResearchStageView|null>(null),[loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[expanded,setExpanded]=useState(false),[stage,setStage]=useState<StageAssign['stage_id']>('data');
 const inFlight=useRef(false),container=useRef<HTMLElement>(null),trigger=useRef<HTMLButtonElement>(null),contentId=useId();
 useEffect(()=>{if(!expanded)return;const outside=(e:PointerEvent)=>{if(!container.current?.contains(e.target as Node)&&!(e.target as Element)?.closest?.('[role="listbox"]'))setExpanded(false);};const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){setExpanded(false);trigger.current?.focus();}};document.addEventListener('pointerdown',outside);document.addEventListener('keydown',key);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',key);};},[expanded]);
 useEffect(()=>{let alive=true,timer:ReturnType<typeof setTimeout>;async function refresh(){try{const v=await formalApi<ResearchStageView|null>('/conversations/'+cid+'/stage');if(alive){setValue(v);setLoaded(true);}}catch{}finally{if(alive)timer=setTimeout(()=>{if(document.visibilityState==='visible')void refresh();else timer=setTimeout(refresh,15000);},running?5000:10000);}}void refresh();return()=>{alive=false;clearTimeout(timer);};},[cid,running]);
 useEffect(()=>{if(value?.status==='ready')setExpanded(true);},[value?.revision,value?.status]);
 async function act(kind:'assign'|'switch'){
  if(inFlight.current)return;inFlight.current=true;setBusy(true);
  try{const next=await formalApi<ResearchStageView>('/conversations/'+cid+'/stage'+(kind==='switch'?'/switch':''),{method:'POST',body:JSON.stringify(kind==='switch'?{expected_revision:value!.revision}:{stage_id:stage})});setValue(next);onChange();if(next.conversation_id!==cid)onNavigate(next.conversation_id);}
  catch(e){const message=e instanceof Error?e.message:String(e);onError(new Error(errors[message]||message));try{setValue(await formalApi<ResearchStageView|null>('/conversations/'+cid+'/stage'));}catch{}}
  finally{setBusy(false);inFlight.current=false;}
 }
 if(!loaded)return null;
 const owner=value?.conversation_id===cid,ready=owner&&value?.status==='ready',done=owner&&value?.status==='completed';
 const pack=(owner?(value?.handoff||value?.incoming_handoff):value?.incoming_handoff) as Package|undefined;
 return <section className={'stage-panel'+(ready?' stage-ready':'')} aria-label="研究阶段与会话交接" ref={container}>
  <button type="button" className="stage-toggle" ref={trigger} aria-controls={contentId} aria-expanded={expanded} onClick={()=>setExpanded(x=>!x)}><span title={value?.stage_label}>{value?`${stages.findIndex(s=>s[0]===value.stage_id)+1}/5 · ${value.stage_label}`:'关联研究阶段'}</span><span className={'stage-state'+(!ready&&!done&&owner?' stage-state-current':'')+' status-text status-'+statusTone(ready?'pending':done?'completed':'running')}>{value?(ready?'待切换会话':done?'阶段交付完成':owner?'当前阶段':'其他会话正在推进'):''}</span><span aria-hidden="true">{expanded?'⌃':'⌄'}</span></button>
  {ready&&<div className="stage-reminder" role="status"><span>本阶段已交付 · 下一阶段：{value!.next_stage_label}</span>{!readOnly&&<button type="button" className="primary-button" disabled={busy||running} onClick={()=>act('switch')}>{busy?'正在交接…':'切换并继续'}</button>}</div>}
  {expanded&&<div className="stage-content" id={contentId}>
   {ready&&<p className="stage-next">本阶段已交付 · 下一阶段：{value!.next_stage_label}</p>}
   {!value?<><p>选择当前所处环节。历史环节不会被自动标为完成。</p>{!readOnly&&<div className="stage-setup"><ComposerSelect label="当前研究阶段" variant="form" value={stage||'data'} options={stages.map(([value,label])=>({value,label}))} onChange={v=>setStage(v as StageAssign['stage_id'])}/><button className="primary-button" disabled={busy||running} onClick={()=>act('assign')}>关联当前会话</button></div>}</>:<>
    <ol className="stage-steps">{stages.map(([id,label],i)=><li key={id} aria-current={value.stage_id===id?'step':undefined}><span>{i+1}</span>{label}{value.stage_id===id&&<strong>当前</strong>}</li>)}</ol>
    {!owner&&<button onClick={()=>onNavigate(value.conversation_id)}>打开当前阶段会话</button>}
    {pack&&<details open={ready}><summary>{ready||done?'交接内容':'本会话接收的上下文'}</summary><p>{pack.agent_report?.summary}</p>{[['已确认决定',pack.agent_report?.decisions],['局限与审核边界',pack.agent_report?.limitations],['待解决问题',pack.agent_report?.open_questions]].map(([title,items])=>Array.isArray(items)&&items.length>0?<div key={String(title)}><strong>{String(title)}</strong><ul>{items.map((s:string,i:number)=><li key={i}>{s}</li>)}</ul></div>:null)}{pack.agent_report?.next_action&&<p>下一步：{pack.agent_report.next_action}</p>}<p>已绑定 {pack.verified_evidence?.length||0} 项成果引用。保留原目标、授权边界和已用额度。</p></details>}
    {done&&<p>五阶段交付已完成；科学审核、作者确认及对外发布权限仍分别记录。</p>}
    {(value.history||[]).length>0&&<details><summary>阶段交接记录（{(value.history||[]).length}）</summary><ul>{(value.history||[]).map((h,i)=><li key={i}><button className="text-link" onClick={()=>onNavigate(String(h.conversation_id))}>{stages.find(s=>s[0]===h.stage_id)?.[1]||String(h.stage_id)} · {h.kind==='revision_requested'?'补充修订':'历史会话'}</button></li>)}</ul></details>}
   </>}
  </div>}
 </section>;
}
