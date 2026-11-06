import {requestId} from './requestId';
import {StageDisclosure} from './StageDisclosure';
import {useEffect,useRef,useState} from 'react';
import {formalApi} from './FormalStudy';
import {ComposerSelect} from './ComposerSelect';
import './manuscript-review.css';
type Material={role:string;label:string;artifact_id:string;sha256:string};
type Issue={id:string;finding:string;location:string;blocking:boolean;resolved:boolean};
type Packet={id:string;digest:string;materials:Material[];request:{gate:string;summary:string;changes?:string[];key_findings?:string[];key_limitations?:string[];issues:Issue[];author_questions:string[];audit_status:string}};
export type ManuscriptView={revision:number;goal_state?:string|null;index:number;status:string;gate:string;label:string;next_work:string;pending:Packet|null;gates:{id:string;label:string;status:string}[];history:{event:string;action?:string;comment?:string;issues?:{issue_id:string;decision:string;rationale:string}[];at:string;target_gate?:string;question_response?:{questions:string[];answer:string;confirmed_with_plan:boolean};packet?:Packet|null}[];author_content_approved:boolean;delivery_approved:boolean};
export const reviewErrors:Record<string,string>={manuscript_snapshot_changed:'审核存档校验失败，请保留现场并核查存储；不能沿用旧批准。',manuscript_review_changed:'审核版本已更新，请查看最新材料。',manuscript_active_turn:'Agent 回合尚未结束，请稍后提交审核。',manuscript_evidence_changed:'被审阅的原材料已变化，请退回相应节点重新审核。',manuscript_unresolved_blockers:'仍有未解决的完整性阻塞，请先退回修改。',manuscript_author_facts_required:'请答复当前问题；方案阶段可随答复一起确认，后续稿件需先更新材料。',manuscript_answer_confirmation_wrong_gate:'当前节点需要先更新材料，请提交反馈后审阅新版本。',manuscript_written_confirmation_required:'请明确确认当前版本的科学内容或交付文件。',manuscript_each_issue_requires_decision:'每条审稿意见都需要裁定及理由。',manuscript_feedback_required:'请填写修改要求或补充事实。',manuscript_reopen_reason_required:'请填写返工原因。',manuscript_no_pending_review:'当前没有可批准的稿件版本。',manuscript_goal_changed:'稿件目标已变化，请由 Agent 重新提交当前审核。'};
const decisions=[{value:'',label:'选择裁定'},{value:'accept',label:'接受'},{value:'modify',label:'调整后接受'},{value:'reject',label:'拒绝'},{value:'defer',label:'暂缓'}];
const nextActions:Record<string,string>={blueprint:'确认后，Agent 将按方案和你的答复准备初稿与图件。',draft:'确认后，Agent 将检查当前初稿的完整性并开展审稿。',review:'提交后，Agent 将按逐条裁定修订稿件。',scientific:'确认当前版本后，Agent 将进入排版与交付检查。',delivery:'确认后登记最终交付；不包含投稿或对外发布。'};
const actionLabels:Record<string,string>={approve:'已确认',revise:'退回修改',clarify:'补充事实',reopen:'重新审核'};
export function ManuscriptReview({cid,value,readOnly,running,onUpdate,onError}:{cid:string;value:ManuscriptView;readOnly:boolean;running:boolean;onUpdate:(v:ManuscriptView)=>void;onError:(e:unknown)=>void}){
 const [comment,setComment]=useState(''),[ack,setAck]=useState(false),[busy,setBusy]=useState(false),[target,setTarget]=useState(value.gate),[choices,setChoices]=useState<Record<string,{decision:string;rationale:string}>>({});
 const flight=useRef(false),retry=useRef<{signature:string;key:string}>();
 useEffect(()=>{setComment('');setAck(false);setChoices({});setTarget(value.gate);retry.current=undefined;},[value.revision,value.gate]);
 const packet=value.pending,issues=packet?.request.issues||[],questions=packet?.request.author_questions||[],changes=packet?.request.changes||[],findings=packet?.request.key_findings||[],limitations=packet?.request.key_limitations||[],blocked=issues.some(i=>i.blocking&&!i.resolved)||packet?.request.audit_status==='blocked',written=['scientific','delivery'].includes(value.gate);
 const affirm=value.gate==='scientific'?'我已审阅本版修订稿及核验材料，确认科学内容并允许冻结排版；不代表伦理批准、独立外部评审或投稿授权。':'我已审阅本版 PDF、图表及交付清单，确认交付文件；不授权投稿或对外发布。';
 const answerWithPlan=value.gate==='blueprint'&&questions.length>0;
 const needsAnswers=questions.length>0&&(!answerWithPlan||!comment.trim());
 const canApprove=Boolean(packet)&&!blocked&&!needsAnswers&&(!written||ack)&&(value.gate!=='review'||issues.every(i=>choices[i.id]?.decision&&choices[i.id]?.rationale.trim()));
 const disabledReason=blocked?'当前有完整性问题，请提交修改意见。':needsAnswers?(answerWithPlan?'答复以上问题后，即可随答复一起确认方案。':'当前问题需要先补充到稿件，请提交反馈，由 Agent 更新材料后再确认。'):written&&!ack?'请先勾选本版内容的明确确认。':value.gate==='review'&&!canApprove?'请为每条审稿意见选择裁定并填写理由。':running?'Agent 正在执行，结束后即可提交。':'';
 async function act(action:'approve'|'revise'|'clarify'|'reopen'){
  if(flight.current||readOnly||running||(action==='approve'&&!canApprove))return;
  if(action!=='approve'&&!comment.trim()){onError(new Error('请填写修改要求、补充事实或返工原因。'));return;}
  const payload={expected_revision:value.revision,action,...(action==='approve'&&answerWithPlan?{confirm_answers:true}:{}),comment:action==='approve'&&written?affirm+(comment.trim()?'\n'+comment.trim():''):comment.trim(),issues:action==='approve'&&value.gate==='review'?issues.map(i=>({issue_id:i.id,...choices[i.id]})):[],...(action==='reopen'?{target_gate:target}:{})};
  const signature=JSON.stringify(payload);if(!retry.current||retry.current.signature!==signature)retry.current={signature,key:requestId()};
  flight.current=true;setBusy(true);
  try{const result=await formalApi<ManuscriptView>('/conversations/'+cid+'/manuscript-review',{method:'POST',body:JSON.stringify({...payload,request_key:retry.current.key})});retry.current=undefined;onUpdate(result);}
  catch(e){const msg=e instanceof Error?e.message:String(e);onError(new Error(reviewErrors[msg]||msg));try{onUpdate(await formalApi<ManuscriptView>('/conversations/'+cid+'/manuscript-review'));}catch{}}
  finally{flight.current=false;setBusy(false);}
 }
 function materials(p:Packet){return <ul className="manuscript-materials">{p.materials.map((m,i)=><li key={i}><a href={'/api/v2/conversations/'+cid+'/manuscript-review/'+p.id+'/materials/'+m.artifact_id} target="_blank" rel="noreferrer">{m.label} ↗</a></li>)}</ul>;}
 return <section className="manuscript-review" aria-label="稿件作者审核">
  <div className="manuscript-heading"><div><h3>{value.index===5?'交付文件已确认':value.label}</h3></div><span className="manuscript-step-count">{Math.min(value.index+1,5)}<span> / 5</span></span></div>
  <div className="manuscript-current">
  {packet&&<p className="manuscript-next-action">{nextActions[value.gate]}</p>}
  {value.goal_state==='paused'&&<p role="status">目标已暂停。可以保存审核决定；之后需在目标栏恢复执行。</p>}
  {value.goal_state==='completed'&&value.index<5&&<p>审核材料尚待准备，请在对话中发起稿件准备任务。</p>}
  {packet?<>
   {blocked&&<p className="status-text status-warning" role="status">完整性检查仍有阻塞，先处理后再审核。</p>}
   {(changes.length>0||findings.length>0||limitations.length>0)&&<div className="manuscript-overview">
    {changes.length>0&&<section><h4>本版变化</h4><ul>{changes.map((item,i)=><li key={i}>{item}</li>)}</ul></section>}
    {(findings.length>0||limitations.length>0)&&<section><h4>关键结论与限制</h4><ul>{findings.map((item,i)=><li key={'finding-'+i}>{item}</li>)}{limitations.map((item,i)=><li key={'limitation-'+i}><strong>限制：</strong>{item}</li>)}</ul></section>}
   </div>}
   {questions.length>0&&<div className="manuscript-required"><h4>这次需要你决定</h4><ul>{questions.map((q,i)=><li key={i}>{q}</li>)}</ul></div>}

   {(value.gate==='review'||blocked)&&issues.length>0&&<div className="manuscript-issues">{issues.map(i=><div key={i.id} className="manuscript-issue"><strong>{i.id}{i.blocking&&!i.resolved?' · 阻塞':''}</strong><p>{i.finding}</p>{i.location&&<small>{i.location}</small>}{value.gate==='review'&&!readOnly&&<><ComposerSelect label={'裁定 '+i.id} variant="form" value={choices[i.id]?.decision||''} options={decisions} onChange={decision=>setChoices(c=>({...c,[i.id]:{rationale:c[i.id]?.rationale||'',decision}}))}/><label>裁定理由<textarea aria-label={'裁定理由 '+i.id} maxLength={1200} value={choices[i.id]?.rationale||''} onChange={e=>setChoices(c=>({...c,[i.id]:{decision:c[i.id]?.decision||'',rationale:e.target.value}}))}/></label></>}</div>)}</div>}
   {!readOnly&&<>{written&&<label className="manuscript-attestation"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/><span>{affirm}</span></label>}<label>{questions.length?'答复与意见':'补充意见（可选）'}<textarea aria-label="稿件审核意见" maxLength={8000} value={comment} onChange={e=>setComment(e.target.value)} placeholder={questions.length?'可在这里一次答复以上问题；需要修改方案也可直接说明。':'确认时可附带意见；需要修改请说明具体要求。'}/></label>{disabledReason&&<p className="manuscript-submit-hint" id={'manuscript-hint-'+cid}>{disabledReason}</p>}<div className="manuscript-actions"><button className="primary-button" aria-describedby={disabledReason?'manuscript-hint-'+cid:undefined} disabled={busy||running||!canApprove} onClick={()=>act('approve')}>{busy?'正在保存…':answerWithPlan?'提交答复并确认方案':({blueprint:'确认方案并继续',draft:'确认初稿，进入审查',review:'提交裁定并修订',scientific:'确认内容，进入排版',delivery:'确认交付并继续'} as Record<string,string>)[value.gate]}</button><button disabled={busy||running||!comment.trim()} onClick={()=>act('revise')}>按意见修改</button></div></>}
  </>:<p>{value.index===5?'Agent 可登记交接；投稿仍需另行授权。':value.next_work}</p>}
  </div>
  <div className="manuscript-secondary">{packet&&<StageDisclosure title="查看审核材料" meta={`${packet.materials.length} 项`} defaultOpen={value.gate!=='blueprint'}><div className="manuscript-evidence"><div className="manuscript-evidence-heading"><h4>审核材料</h4><small className="manuscript-version">版本 {packet.digest.slice(0,12)}</small></div>{materials(packet)}</div></StageDisclosure>}
  {value.gate!=='review'&&!blocked&&issues.length>0&&<StageDisclosure title="核对记录与限制" meta={`${issues.length} 项`}>{issues.map(i=><div className="manuscript-issue" key={i.id}><p>{i.finding}</p>{i.location&&<small>{i.location}</small>}</div>)}</StageDisclosure>}
  {packet&&<StageDisclosure title="本轮审核说明"><p>{packet.request.summary}</p></StageDisclosure>}
  {!readOnly&&value.revision>0&&<StageDisclosure title="返回之前的审核节点" meta="返工"><p>保留原版本和意见；所选节点及后续批准需要重新取得。</p><ComposerSelect label="返工节点" variant="form" value={target} options={value.gates.slice(0,Math.min(value.index+1,5)).map(g=>({value:g.id,label:g.label}))} onChange={setTarget}/>{!packet&&<label>返工原因<textarea aria-label="稿件返工原因" value={comment} maxLength={8000} onChange={e=>setComment(e.target.value)}/></label>}<button disabled={busy||running} onClick={()=>act('reopen')}>退回所选节点</button></StageDisclosure>}
  {value.history.length>0&&<StageDisclosure title="审核与修订历史" meta={`${value.history.length} 条`}>{value.history.map((h,i)=><div className="manuscript-history" key={i}><strong>{actionLabels[h.action||'']||'材料版本更新'} · {value.gates.find(g=>g.id===h.target_gate)?.label||''}</strong>{h.comment&&<p>{h.comment}</p>}{h.question_response&&<StageDisclosure title="本次答复的问题" meta="随方案确认"><ul>{h.question_response.questions.map((q,i)=><li key={i}>{q}</li>)}</ul></StageDisclosure>}{h.issues&&h.issues.length>0&&<ul>{h.issues.map(x=><li key={x.issue_id}>{x.issue_id} · {decisions.find(d=>d.value===x.decision)?.label}：{x.rationale}</li>)}</ul>}{h.packet&&<StageDisclosure title="当时审阅的材料" meta={`${h.packet.materials.length} 项`}>{materials(h.packet)}</StageDisclosure>}</div>)}</StageDisclosure>}</div>
 </section>;
}

export function ManuscriptProgress({value,onLocate}:{value:ManuscriptView;onLocate:()=>void}){
 return <section className="manuscript-progress" aria-label="稿件生成阶段"><div className="manuscript-progress-heading"><div><span className="stage-eyebrow">稿件生成阶段</span><h3>{value.index===5?'交付文件已确认':value.label}</h3></div><span className="manuscript-step-count">{Math.min(value.index+1,5)}<span> / 5</span></span></div>
 <StageDisclosure title="稿件生成流程" meta={`${value.index}/5 已确认`}><ol className="manuscript-gates">{value.gates.map((g,i)=><li key={g.id} aria-current={g.id===value.gate&&value.index<5?'step':undefined}><span className="manuscript-gate-order" aria-hidden="true">{i+1}</span><span className="manuscript-gate-label">{g.label}</span><small className={'status-text status-'+(g.status==='approved'?'success':g.status==='awaiting_review'?'warning':g.status==='preparing'?'info':'neutral')}>{g.status==='approved'?'已确认':g.status==='awaiting_review'?'待作者审核':g.status==='preparing'?'准备中':'未开始'}</small></li>)}</ol></StageDisclosure>
 <button type="button" className="text-link" onClick={onLocate}>{value.status==='awaiting_review'?'打开稿件审核':'查看审核记录'} →</button></section>;
}
