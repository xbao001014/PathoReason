import {memo,useEffect,useId,useState} from 'react';
import type {ToolSummary,TurnView} from './generated';
import {statusTone} from './status';
import './turnProcess.css';

const actions:Record<string,string>={bash:'执行命令',read:'读取文件',write:'写入文件',edit:'编辑文件',apply_patch:'修改文件',glob:'查找文件',grep:'检索文件内容',list:'列出目录',webfetch:'读取网页',websearch:'搜索网页',skill:'加载 Skill',task:'调用子任务',todowrite:'更新任务清单',todoread:'读取任务清单',pathoreason_research:'调用研究工具'};
const liveStatuses=['queued','running','interrupt_requested','recovery_required'];
const toolLabels:Record<string,string>={completed:'完成',running:'进行中',pending:'待处理',error:'失败',failed:'失败',cancelled:'已取消',interrupted:'已停止',unknown:'结果未确认'};
const describe=(tool:ToolSummary)=>tool.summary||actions[tool.name]||'调用工具';
function duration(ms:number){const seconds=Math.max(0,Math.floor(ms/1000));return seconds<60?seconds+'秒':Math.floor(seconds/60)+'分'+seconds%60+'秒';}
const recordedDuration=(seconds:number|null|undefined)=>seconds==null?'—':duration(seconds*1000);
type Group={key:string;summary:string;status:string;tools:ToolSummary[];repeat:string|null;name:string;objects:string};
function groups(tools:ToolSummary[],active:boolean){
 const result:Group[]=[];
 for(const tool of tools){
  const summary=describe(tool),status=!active&&['running','pending'].includes(tool.status)?'unknown':tool.status;
  const previous=result.at(-1),repeat=tool.repeat_key??null,objects=JSON.stringify([tool.targets||[],tool.operation||null,tool.working_directory||null]);
  // Only verified identical read/status operations collapse. Training and generic commands stay separate.
  if(status==='completed'&&repeat&&previous?.status===status&&previous.repeat===repeat&&previous.summary===summary&&previous.name===tool.name&&previous.objects===objects){previous.tools.push(tool);}
  else result.push({key:tool.id,summary,status,tools:[tool],repeat,name:tool.name,objects});
 }
 return result;
}
function ProcessIcon({status}:{status:string}){
 const tone=statusTone(status);
 return <svg className={'process-icon status-text status-'+tone} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
  {tone==='success'?<path d="m4 10 4 4 8-8"/>:tone==='danger'?<><path d="m6 6 8 8M14 6l-8 8"/></>:tone==='info'?<><circle cx="10" cy="10" r="6.5"/><path d="M10 6v4l2.5 1.5"/></>:<><circle cx="10" cy="10" r="6.5"/><path d="M10 6.5v4M10 13.5h.01"/></>}
 </svg>;
}
function ToolResult({tool,status,showDuration=true}:{tool:ToolSummary;status:string;showDuration?:boolean}){
 const label=status==='completed'&&tool.name==='bash'?'已返回':toolLabels[status]||'状态未知';
 return <span className="process-result"><span className={'status-text status-'+statusTone(status)}>{label}</span>{showDuration&&tool.duration_ms!=null&&<span className="process-duration">{duration(tool.duration_ms)}</span>}</span>;
}
const objectActions:Record<string,string>={read:'读取',write:'写入',edit:'修改',delete:'删除',run:'运行'};
const objectKinds:Record<string,string>={file:'文件',directory:'目录',script:'脚本',website:'网页',skill:'Skill',experiment:'实验',pattern:'文件范围'};
function objectPreview(tool:ToolSummary){
 const target=tool.targets?.[0];
 if(!target)return tool.name+(tool.operation?' · '+tool.operation:'');
 const path=['file','directory','script'].includes(target.kind)?target.label.split('/').filter(Boolean).slice(-2).join('/')||target.label:target.label;
 return (target.action&&['bash','apply_patch'].includes(tool.name)?objectActions[target.action]+' · ':'')+path;
}
function ObjectDetails({tool}:{tool:ToolSummary}){
 const remaining=Math.max(0,(tool.target_count||0)-(tool.targets?.length||0));
 return <dl className="process-object-facts">
  <div><dt>工具</dt><dd><code>{tool.name}</code>{tool.operation&&<><span aria-hidden="true"> · </span><code>{tool.operation}</code></>}</dd></div>
  {tool.working_directory&&<div><dt>工作目录</dt><dd><code>{tool.working_directory}</code></dd></div>}
  {tool.targets?.map((target,index)=><div key={index}><dt>{target.action?objectActions[target.action]:objectKinds[target.kind]}</dt><dd><code>{target.label}</code></dd></div>)}
  {remaining>0&&<div><dt>其他</dt><dd>另 {remaining} 项，仅显示前 {tool.targets?.length} 项</dd></div>}
 </dl>;
}
function ObjectPreview({tool}:{tool:ToolSummary}){
 const count=tool.target_count||tool.targets?.length||0;
 return <span className="process-object-preview"><code>{objectPreview(tool)}</code>{count>1&&<span className="process-object-count">+{count-1}</span>}</span>;
}
function ToolObjects({tool}:{tool:ToolSummary}){
 return <details className="process-objects"><summary aria-label={'查看 '+tool.name+' 的调用对象'}><ObjectPreview tool={tool}/><svg className="process-object-chevron" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m7 5 5 5-5 5"/></svg></summary><ObjectDetails tool={tool}/></details>;
}

export const TurnProcess=memo(function TurnProcess({view}:{view:TurnView}){
 const status=view.turn.status,active=liveStatuses.includes(status),responding=view.usage.activity_phase==='responding'||(!view.usage.activity_phase&&Boolean(view.text));
 const [expanded,setExpanded]=useState(active&&!responding),[showHelp,setShowHelp]=useState(false),[clock,setClock]=useState(Date.now),id=useId();
 useEffect(()=>{if(responding||!active)setExpanded(false);},[responding,active]);
 useEffect(()=>{if(!active||status==='recovery_required')return;const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[active,status]);
 const tools=Array.from(new Map(view.tools.map(t=>[t.id,t])).values()),rows=groups(tools,active),failed=tools.filter(t=>['error','failed'].includes(t.status)).length;
 const current=[...tools].reverse().find(t=>['running','pending'].includes(t.status));
 const title=status==='queued'?'等待执行':status==='recovery_required'?'执行状态待核对':status==='interrupt_requested'?'正在停止':active?(responding?'正在输出回答':current?(current.status==='pending'?'等待工具执行':describe(current)):'正在处理'):status==='completed'?'执行过程':status==='interrupted'?'执行已停止':'执行未完成';
 const start=Date.parse(view.turn.created_at),end=view.turn.finished_at?Date.parse(view.turn.finished_at):active&&status!=='recovery_required'?clock:NaN;
 const elapsed=Number.isFinite(start)&&Number.isFinite(end)&&end>=start?duration(end-start):null;
 const hasTiming=view.timing?.mode==='tool_excluded_v1',hasCommand=tools.some(t=>t.name==='bash'),hasHelp=hasTiming||hasCommand;
 return <section className="turn-process" aria-label="本轮执行过程">
  <button className="process-toggle" type="button" aria-expanded={expanded} aria-controls={id} onClick={()=>setExpanded(v=>!v)}>
   <ProcessIcon status={status}/>
   <span className="process-heading"><span className="process-title">{title}</span><span className="process-count"><span>{tools.length} 次调用</span>{elapsed&&<><span aria-hidden="true"> · </span><span>总历时 {elapsed}</span></>}</span></span>
   {failed>0&&<span className="status-text status-danger process-failures">{failed} 次失败</span>}
   <svg className="process-chevron" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d={expanded?'m5 12 5-5 5 5':'m5 8 5 5 5-5'}/></svg>
  </button>
  <div id={id} hidden={!expanded} className="process-content">
   {rows.length>0?<ol className="process-timeline" tabIndex={0} aria-label="工具调用记录">{rows.map(row=><li key={row.key} className={'process-step status-'+statusTone(row.status)+(row.status==='running'?' is-current':'')+(['error','failed'].includes(row.status)?' is-failed':'')}>
    <span className="process-node"><ProcessIcon status={row.status}/></span>
    {row.tools.length>1?<details className="process-repeated"><summary><span className="process-description"><span className="process-action">{row.summary}</span><ObjectPreview tool={row.tools[0]}/></span><span className="process-repeat-count">{row.tools.length} 次</span><ToolResult tool={row.tools[0]} status={row.status} showDuration={false}/><svg className="process-repeat-chevron" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m7 5 5 5-5 5"/></svg></summary><ObjectDetails tool={row.tools[0]}/><ol aria-label={row.summary+'的重复调用'}>{row.tools.map((tool,index)=><li key={tool.id}><span>第 {index+1} 次</span><ToolResult tool={tool} status={row.status}/></li>)}</ol></details>:<div className="process-step-body"><div className="process-description"><span className="process-action">{row.summary}</span><ToolObjects tool={row.tools[0]}/></div><ToolResult tool={row.tools[0]} status={row.status}/></div>}
   </li>)}</ol>:<p className="process-empty">暂无工具调用</p>}
   {(hasHelp||view.usage.compaction_observed)&&<footer className="process-footer">
    {hasTiming&&<dl className="process-timing"><div><dt>Agent</dt><dd>{recordedDuration(view.timing?.agent_seconds)}</dd></div><div><dt>工具 / 等待</dt><dd>{recordedDuration(view.timing?.tool_seconds)}</dd></div></dl>}
    {view.usage.compaction_observed&&<span className="process-compaction">上下文已压缩</span>}
    {hasHelp&&<button className="process-help-toggle" type="button" aria-label="计时与状态说明" title="计时与状态说明" aria-expanded={showHelp} aria-controls={id+'-help'} onClick={()=>setShowHelp(v=>!v)}><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="M10 9v5M10 6h.01"/></svg></button>}
   </footer>}
   {hasHelp&&<div id={id+'-help'} hidden={!showHelp} className="process-help">
    {hasTiming&&<p>Agent 计时扣除已记录的工具与等待区间；总历时包含等待。两者均非 GPU 耗时。</p>}
    {hasCommand&&<p>命令返回仅表示调用结束，研究结果以验收为准。</p>}
   </div>}
  </div>
 </section>;
});
