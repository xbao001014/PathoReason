import {useEffect,useId,useState} from 'react';
import type {ToolSummary,TurnView} from './generated';
import {statusTone} from './status';
import './turnProcess.css';

const actions:Record<string,string>={bash:'执行命令',read:'读取文件',write:'写入文件',edit:'编辑文件',apply_patch:'修改文件',glob:'查找文件',grep:'检索文件内容',list:'列出目录',webfetch:'读取网页',websearch:'搜索网页',skill:'加载 Skill',task:'调用子任务',todowrite:'更新任务清单',todoread:'读取任务清单',pathoreason_research:'调用研究工具'};
const liveStatuses=['queued','running','interrupt_requested','recovery_required'];
const toolLabels:Record<string,string>={completed:'调用完成',running:'进行中',pending:'待处理',error:'调用失败',failed:'调用失败',cancelled:'已取消',interrupted:'已停止',unknown:'结果未确认'};
const describe=(tool:ToolSummary)=>tool.summary||actions[tool.name]||'调用工具';
function duration(ms:number){const seconds=Math.max(0,Math.floor(ms/1000));return seconds<60?seconds+'秒':Math.floor(seconds/60)+'分'+seconds%60+'秒';}
type Group={key:string;summary:string;status:string;count:number;duration:number|null};
function groups(tools:ToolSummary[],active:boolean){
 const result:Group[]=[];
 for(const tool of tools){
  const summary=describe(tool),status=!active&&['running','pending'].includes(tool.status)?'unknown':tool.status;
  const previous=result.at(-1),ms=tool.duration_ms??null;
  // Only consecutive completed calls are grouped. Failures stay individually visible.
  if(status==='completed'&&previous?.status===status&&previous.summary===summary){previous.count++;previous.duration=previous.duration!==null&&ms!==null?previous.duration+ms:null;}
  else result.push({key:tool.id,summary,status,count:1,duration:ms});
 }
 return result;
}
export function TurnProcess({view}:{view:TurnView}){
 const status=view.turn.status,active=liveStatuses.includes(status),responding=view.usage.activity_phase==='responding'||(!view.usage.activity_phase&&Boolean(view.text));
 const [expanded,setExpanded]=useState(active&&!responding),[clock,setClock]=useState(Date.now),id=useId();
 // Fold on output and completion boundaries, not on every streamed text update.
 // A manual expansion during output remains open until the next boundary.
 useEffect(()=>{if(responding||!active)setExpanded(false);},[responding,active]);
 useEffect(()=>{if(!active||status==='recovery_required')return;const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[active,status]);
 const tools=Array.from(new Map(view.tools.map(t=>[t.id,t])).values()),rows=groups(tools,active),failed=tools.filter(t=>['error','failed'].includes(t.status)).length;
 const current=[...tools].reverse().find(t=>['running','pending'].includes(t.status));
 const title=status==='queued'?'等待执行':status==='recovery_required'?'等待核对执行状态':status==='interrupt_requested'?'正在停止':active?(responding?'正在输出回答':current?(current.status==='pending'?'等待工具执行':'正在'+describe(current)):'模型处理中'):status==='completed'?'执行过程':status==='interrupted'?'执行已停止':'执行未完成';
 const start=Date.parse(view.turn.created_at),end=view.turn.finished_at?Date.parse(view.turn.finished_at):active&&status!=='recovery_required'?clock:NaN;
 const elapsed=Number.isFinite(start)&&Number.isFinite(end)&&end>=start?duration(end-start):null;
 return <section className="turn-process" aria-label="本轮执行过程">
  <button className="process-toggle" type="button" aria-expanded={expanded} aria-controls={id} onClick={()=>setExpanded(v=>!v)}>
   <span className={'process-symbol status-text status-'+statusTone(status)} aria-hidden="true">{active?'◉':status==='completed'?'✓':'!'}</span>
   <span className="process-title">{title}</span>
   <span className="process-count">{tools.length} 次工具调用{elapsed?' · '+(active?'已运行 ':'耗时 ')+elapsed:''}</span>
   {failed>0&&<span className="status-text status-danger process-failures">{failed} 次失败</span>}
   <span className="process-chevron" aria-hidden="true">{expanded?'⌃':'⌄'}</span>
  </button>
  <div id={id} hidden={!expanded} className="process-content">
   {rows.length>0?<ol className="process-timeline" tabIndex={0} aria-label="工具调用记录">{rows.map(row=><li key={row.key}><span className={'status-text status-'+statusTone(row.status)} aria-hidden="true">{row.status==='completed'?'✓':['error','failed'].includes(row.status)?'!':'•'}</span><span className="process-action">{row.summary}{row.count>1?' × '+row.count:''}</span><span className={'process-result status-text status-'+statusTone(row.status)}>{toolLabels[row.status]||'状态未知'}{row.duration!==null?' · '+(row.count>1?'合计 ':'')+duration(row.duration):''}</span></li>)}</ol>:<p className="process-empty">{active?'尚无工具调用记录':'本轮无工具调用记录'}</p>}
   {view.usage.compaction_observed&&<p className="process-note">原生上下文已有压缩记录</p>}
  </div>
 </section>;
}
