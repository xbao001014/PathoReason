import {useEffect,useId,useState} from 'react';
import type {ToolSummary,TurnView} from './generated';
import {statusTone} from './status';
import './turnProcess.css';

const actions:Record<string,string>={bash:'执行命令',read:'读取文件',write:'写入文件',edit:'编辑文件',apply_patch:'修改文件',glob:'查找文件',grep:'检索文件内容',list:'列出目录',webfetch:'读取网页',websearch:'搜索网页',skill:'加载 Skill',task:'调用子任务',todowrite:'更新任务清单',todoread:'读取任务清单',pathoreason_research:'调用研究工具'};
const liveStatuses=['queued','running','interrupt_requested','recovery_required'];
const toolLabels:Record<string,string>={completed:'调用完成',running:'进行中',pending:'待处理',error:'调用失败',failed:'调用失败',cancelled:'已取消',interrupted:'已停止',unknown:'结果未确认'};
const describe=(tool:ToolSummary)=>tool.summary||actions[tool.name]||'调用工具';
function duration(ms:number){const seconds=Math.max(0,Math.floor(ms/1000));return seconds<60?seconds+'秒':Math.floor(seconds/60)+'分'+seconds%60+'秒';}
type Group={key:string;summary:string;status:string;tools:ToolSummary[];repeat:string|null;name:string};
function groups(tools:ToolSummary[],active:boolean){
 const result:Group[]=[];
 for(const tool of tools){
  const summary=describe(tool),status=!active&&['running','pending'].includes(tool.status)?'unknown':tool.status;
  const previous=result.at(-1),repeat=tool.repeat_key??null;
  // Only verified identical read/status operations collapse. Training and generic commands stay separate.
  if(status==='completed'&&repeat&&previous?.status===status&&previous.repeat===repeat&&previous.summary===summary&&previous.name===tool.name){previous.tools.push(tool);}
  else result.push({key:tool.id,summary,status,tools:[tool],repeat,name:tool.name});
 }
 return result;
}
export function TurnProcess({view}:{view:TurnView}){
 const status=view.turn.status,active=liveStatuses.includes(status),responding=view.usage.activity_phase==='responding'||(!view.usage.activity_phase&&Boolean(view.text));
 const [expanded,setExpanded]=useState(active&&!responding),[clock,setClock]=useState(Date.now),id=useId();
 useEffect(()=>{if(responding||!active)setExpanded(false);},[responding,active]);
 useEffect(()=>{if(!active||status==='recovery_required')return;const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[active,status]);
 const tools=Array.from(new Map(view.tools.map(t=>[t.id,t])).values()),rows=groups(tools,active),failed=tools.filter(t=>['error','failed'].includes(t.status)).length;
 const current=[...tools].reverse().find(t=>['running','pending'].includes(t.status));
 const title=status==='queued'?'等待执行':status==='recovery_required'?'等待核对执行状态':status==='interrupt_requested'?'正在停止':active?(responding?'正在输出回答':current?(current.status==='pending'?'等待工具执行':describe(current)):'模型处理中'):status==='completed'?'执行过程':status==='interrupted'?'执行已停止':'执行未完成';
 const start=Date.parse(view.turn.created_at),end=view.turn.finished_at?Date.parse(view.turn.finished_at):active&&status!=='recovery_required'?clock:NaN;
 const elapsed=Number.isFinite(start)&&Number.isFinite(end)&&end>=start?duration(end-start):null;
 const resultLabel=(tool:ToolSummary,shownStatus:string)=>shownStatus==='completed'&&tool.name==='bash'?'命令返回':toolLabels[shownStatus]||'状态未知';
 return <section className="turn-process" aria-label="本轮执行过程">
  <button className="process-toggle" type="button" aria-expanded={expanded} aria-controls={id} onClick={()=>setExpanded(v=>!v)}>
   <span className={'process-symbol status-text status-'+statusTone(status)} aria-hidden="true">{active?'◉':status==='completed'?'✓':'!'}</span>
   <span className="process-title">{title}</span>
   <span className="process-count">{tools.length} 次工具调用{elapsed?' · 总历时 '+elapsed:''}</span>
   {failed>0&&<span className="status-text status-danger process-failures">{failed} 次失败</span>}
   <span className="process-chevron" aria-hidden="true">{expanded?'⌃':'⌄'}</span>
  </button>
  <div id={id} hidden={!expanded} className="process-content">
   {view.timing?.mode==='tool_excluded_v1'&&<p className="process-note">Agent 计时 {duration((view.timing.agent_seconds||0)*1000)} · 工具／等待 {duration((view.timing.tool_seconds||0)*1000)}<span className="process-accounting-note">按已记录工具区间扣除；不是 GPU 耗时。</span></p>}
   {rows.length>0?<ol className="process-timeline" tabIndex={0} aria-label="工具调用记录">{rows.map(row=><li key={row.key}>
    <span className={'status-text status-'+statusTone(row.status)} aria-hidden="true">{row.status==='completed'?'✓':['error','failed'].includes(row.status)?'!':'•'}</span>
    {row.tools.length>1?<details className="process-repeated"><summary>{row.summary} · {row.tools.length} 次</summary><ol>{row.tools.map((tool,index)=><li key={tool.id}><span>第 {index+1} 次</span><span>{resultLabel(tool,row.status)}{tool.duration_ms!=null?' · '+duration(tool.duration_ms):''}</span></li>)}</ol></details>:<><span className="process-action">{row.summary}</span><span className={'process-result status-text status-'+statusTone(row.status)}>{resultLabel(row.tools[0],row.status)}{row.tools[0].duration_ms!=null?' · '+duration(row.tools[0].duration_ms):''}</span></>}
   </li>)}</ol>:<p className="process-empty">{active?'尚无工具调用记录':'本轮无工具调用记录'}</p>}
   {tools.some(t=>t.name==='bash')&&<p className="process-note">命令返回不代表训练或研究验收通过。</p>}
   {view.usage.compaction_observed&&<p className="process-note">原生上下文已有压缩记录</p>}
  </div>
 </section>;
}
