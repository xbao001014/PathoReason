import {useEffect,useRef,useState} from 'react';
import {ComposerSelect} from './ComposerSelect';
import {statusTone} from './status';
import './trainingProgress.css';

type Attempt={id:string;unit_id:string;phase:string;run_id:string;status:string;error:string|null;started_at:number;finished_at:number|null;elapsed_seconds:number;charged:boolean;current_scope:boolean;plan_digest:string};
type Unit={id:string;label:string;phase:string;parameters:Record<string,unknown>;status:string;attempt_id:string|null;attempt_count:number;retry_count:number};
type Budget={max_wall_seconds:number;max_gpu_seconds:number;max_unit_seconds:number;max_attempts_per_unit:number};
type Experiment={id:string;conversation_id:string;revision:number;status:string;run_id:string|null;authorized:boolean;error:string|null;budget:Budget|null;used_wall_seconds:number;used_gpu_seconds:number;scientific_approval:false;controller_alive:boolean;plan:{title:string;task_id:string;snapshot_id:string;environment_id:string;protocol:string;evaluation:string;gpu_uuid:string|null;memory_gib:number};units:Unit[];attempts:Attempt[];events:{at:number;kind:string;status?:string;error?:string;reason?:string}[];counts:Record<'fit'|'evaluate',{total:number;completed:number}>;current:{unit_id:string;attempt_id:string;last_epoch:number|null;metrics:Record<string,number>}|null};
type Snapshot={schema_version:string;project_id:string;observed_at:string;experiments:Experiment[]};
type Point={epoch:number;metrics:Record<string,number>};
type Telemetry={project_id:string;experiment_id:string;attempt_id:string;observed_at:string;last_epoch:number|null;points:Point[];sources:string[];notices:string[];log:string;log_bytes:number;log_truncated:boolean};
const labels:Record<string,string>={draft:'待确认方案与预算',ready:'待启动',pending:'未开始',queued:'排队中',running:'运行中',waiting_resource:'等待资源',stopping:'正在停止',stopped:'已停止',failed:'失败',budget_exhausted:'预算耗尽',needs_reconciliation:'待核对执行结果',unknown:'结果未知',completed:'已完成',cancelled:'已取消'};
const events:Record<string,string>={user_authorize:'用户已授权',budget_changed:'预算已修改',user_resume:'用户恢复训练',user_budget:'用户保存预算',user_cancel:'用户取消实验',prepared:'方案已登记',plan_prepared:'方案已登记',user_authorized:'用户已授权',budget_updated:'预算已修改',run_queued:'作业已提交',controller_started:'执行器已接续',attempt_started:'尝试开始',attempt_finished:'尝试结束',run_finished:'作业结束',stop_requested:'请求停止'};
const metricNames:Record<string,string>={train_loss:'训练损失',loss:'损失',val_loss:'验证损失',validation_loss:'验证损失','train.loss':'训练损失','val.loss':'验证损失','val.macro_auc':'验证宏平均 AUC','val.qwk':'验证 QWK','val.acc':'验证准确率','val.accuracy':'验证准确率',val_auc:'验证 AUC',val_accuracy:'验证准确率'};
const time=(v:number)=>new Date(v*1000).toLocaleString('zh-CN',{hour12:false});
const hours=(v:number)=>Number((v/3600).toFixed(3)).toLocaleString('zh-CN');
function Status({status}:{status:string}){return <span className={'status-badge status-'+statusTone(status==='pending'?'not_started':status)}>{labels[status]||status}</span>;}
function useRead<T>(url:string|null,valid:(data:T)=>boolean){
 const [value,setValue]=useState<T|null>(null),[error,setError]=useState('');
 const validate=useRef(valid);validate.current=valid;
 useEffect(()=>{setValue(null);setError('');if(!url)return;let live=true,pending=false;let controller:AbortController|null=null;
  async function poll(){if(pending||document.hidden)return;pending=true;controller=new AbortController();const timer=setTimeout(()=>controller?.abort(),15000);
   try{const r=await fetch(url!,{signal:controller.signal});if(!r.ok)throw Error('读取失败（'+r.status+'），显示最后一次记录');const data:T=await r.json();if(!live)return;if(!validate.current(data))throw Error('进度身份不匹配');setValue(data);setError('');}
   catch(e){if(live)setError((e as Error).name==='AbortError'?'更新超时，显示最后一次记录':(e as Error).message);}
   finally{clearTimeout(timer);pending=false;}
  }void poll();const timer=setInterval(poll,4000);document.addEventListener('visibilitychange',poll);return()=>{live=false;controller?.abort();clearInterval(timer);document.removeEventListener('visibilitychange',poll);};
 },[url]);return {value,error};
}
function Curve({points,title,kind}:{points:Point[];title:string;kind:'loss'|'validation'}){
 const keys=[...new Set(points.flatMap(p=>Object.keys(p.metrics)))].filter(k=>kind==='loss'?k.includes('loss'):(k.startsWith('val')||['auc','macro_auc','acc','accuracy','qwk'].includes(k)));
 const [choice,setChoice]=useState('');const key=keys.includes(choice)?choice:keys[0];const target=useRef<HTMLDivElement>(null);const [width,setWidth]=useState(400);
 useEffect(()=>{const observer=new ResizeObserver(rows=>setWidth(Math.max(120,rows[0].contentRect.width)));if(target.current)observer.observe(target.current);return()=>observer.disconnect();},[]);
 const values=points.filter(p=>key&&Number.isFinite(p.metrics[key]));const ys=values.map(p=>p.metrics[key]);const ymin=Math.min(...ys),ymax=Math.max(...ys),pad=(ymax-ymin)*.08||Math.max(Math.abs(ymax)*.05,.01);const lo=ymin-pad,hi=ymax+pad;
 const xmin=values[0]?.epoch||0,xmax=values.at(-1)?.epoch||xmin+1;const x=(v:number)=>48+(v-xmin)/(xmax-xmin||1)*(width-64),y=(v:number)=>16+(hi-v)/(hi-lo)*138;
 return <section className="tp-chart" ref={target} aria-label={title}><h3>{title}</h3>{keys.length>0&&<ComposerSelect label={title+'指标'} variant="form" value={key} options={keys.map(k=>({value:k,label:metricNames[k]||k}))} onChange={setChoice}/>}
  {values.length?<><svg viewBox={`0 0 ${width} 182`} role="img" aria-label={`${metricNames[key]||key}，epoch ${xmin} 至 ${xmax}，${values.length} 个已上报点`}>
   {[0,.5,1].map(t=>{const v=lo+t*(hi-lo);return <g key={t}><line x1={48} x2={width-16} y1={y(v)} y2={y(v)} className="tp-grid"/><text x={42} y={y(v)+4} textAnchor="end">{Number(v.toPrecision(3))}</text></g>;})}
   <polyline points={values.map(p=>`${x(p.epoch)},${y(p.metrics[key])}`).join(' ')} fill="none" className={'tp-line '+kind}/>
   {values.map(p=><circle key={p.epoch} cx={x(p.epoch)} cy={y(p.metrics[key])} r={2.5} className={'tp-dot '+kind}><title>{'Epoch '+p.epoch+' · '+(metricNames[key]||key)+' '+p.metrics[key]}</title></circle>)}
   <text x={48} y={176}>Epoch {xmin}</text>{xmax!==xmin&&<text x={width-16} y={176} textAnchor="end">{xmax}</text>}
  </svg><p className="rw-caption">最后上报：{values.at(-1)!.metrics[key].toPrecision(5)}</p></>:<p className="rw-muted">尚未上报{title}数据</p>}
 </section>;
}
function BudgetView({experiment:e}:{experiment:Experiment}){return <section className="rw-card tp-budget"><header><h2>独立训练预算</h2><span className="rw-caption">失败、修复与重试累计计费</span></header><div className="tp-budget-grid">{[['累计执行时长',e.used_wall_seconds,e.budget?.max_wall_seconds,'小时'],['累计 GPU 时长',e.used_gpu_seconds,e.budget?.max_gpu_seconds,'GPU·小时']].map(([label,used,limit,unit])=><div key={String(label)}><h3>{label}</h3><p><strong>{hours(Number(used))}</strong> / {limit==null?'未授权':hours(Number(limit))} {unit}</p>{limit!=null&&Number(limit)>0&&<progress aria-label={String(label)+'已用比例'} max={Number(limit)} value={Math.min(Number(used),Number(limit))}/>}</div>)}</div><p className="rw-caption">单元最长 {e.budget?hours(e.budget.max_unit_seconds)+' 小时':'未授权'} · 每单元最多重试 {e.budget?e.budget.max_attempts_per_unit-1:'—'} 次 · 对话回合与 Agent 时间另行计量</p></section>;}
export function TrainingProgress({pid,taskId,compact=false,onOpen,onConversation}:{pid:string;taskId?:string;compact?:boolean;onOpen:()=>void;onConversation:(cid:string)=>void}){
 const base='/api/v2/research-projects/'+encodeURIComponent(pid)+'/training-progress';const {value,error}=useRead<Snapshot>(base,v=>v.project_id===pid&&v.schema_version==='pathoreason.training-progress/1');
 const detailRef=useRef<HTMLElement>(null);
 const [experimentId,setExperimentId]=useState(''),[unitId,setUnitId]=useState(''),[attemptId,setAttemptId]=useState(''),[phase,setPhase]=useState('all');
 useEffect(()=>{setExperimentId('');setUnitId('');setAttemptId('');setPhase('all');},[pid,taskId]);
 const experiments=(value?.project_id===pid?value.experiments:[]).filter(e=>!taskId||e.plan.task_id===taskId);
 const e=experiments.find(e=>e.id===experimentId)||experiments.find(e=>['running','queued','waiting_resource'].includes(e.status))||experiments[0];
 const selectedUnit=e?.units.find(u=>u.id===unitId)||e?.units.find(u=>u.id===e.current?.unit_id)||e?.units.find(u=>u.status==='failed')||e?.units[0];
 const attempts=e?.attempts.filter(a=>a.unit_id===selectedUnit?.id)||[];
 const attempt=attempts.find(a=>a.id===attemptId)||attempts.at(-1);
 const read=useRead<Telemetry>(!compact&&e&&attempt?base+'/'+encodeURIComponent(e.id)+'/attempts/'+encodeURIComponent(attempt.id):null,v=>v.project_id===pid&&v.experiment_id===e?.id&&v.attempt_id===attempt?.id);
 const telemetry=read.value?.attempt_id===attempt?.id&&read.value?.experiment_id===e?.id?read.value:null;
 function chooseUnit(id:string,aid=''){setUnitId(id);setAttemptId(aid);if(id)setTimeout(()=>detailRef.current?.scrollIntoView({block:'start'}),0);}
 if(!value)return <section className="rw-card"><p role={error?'alert':'status'}>{error||'正在读取实验进度…'}</p></section>;
 if(!e)return compact?null:<section className="rw-card"><h2>已登记实验进度</h2><p>当前范围尚无公共执行器实验记录。历史报告保留在下方，不计入实时完成数。</p></section>;
 return <div className="tp" aria-label="实时实验进度">
  <section className="rw-card tp-overview"><header><div><p className="rw-caption">{taskId?'本任务已登记实验':'项目已登记实验'} · 每 4 秒更新</p><h2>{e.plan.title}</h2></div><Status status={e.status}/></header>
   {experiments.length>1&&!compact&&<ComposerSelect label="切换已登记实验" variant="form" value={e.id} options={experiments.map(x=>({value:x.id,label:x.plan.title+' · '+(labels[x.status]||x.status)}))} onChange={id=>{setExperimentId(id);chooseUnit('');}}/>}
   <div className="rw-stats tp-counts"><div><strong>{e.counts.fit.completed} / {e.counts.fit.total}</strong><span>训练完成</span></div><div><strong>{e.counts.evaluate.completed} / {e.counts.evaluate.total}</strong><span>评估完成</span></div><div><strong>{e.current?.last_epoch??'—'}</strong><span>当前单元已上报 epoch</span></div></div>
   {e.current&&<p>当前单元：{e.units.find(u=>u.id===e.current!.unit_id)?.label||e.current.unit_id}</p>}
   <div className="tp-boundaries"><span className="status-badge status-warning">科学审核待完成</span><span>{e.plan.evaluation==='previously_exposed'?'已暴露测试 · 非独立、非盲法':e.plan.evaluation==='development_only'?'仅训练与验证':'留出评估 · 独立性仍需审核'}</span></div>
   <p className="rw-caption" role="status">{error?'更新中断 · '+error:'更新于 '+new Date(value.observed_at).toLocaleTimeString('zh-CN',{hour12:false})}{['running','waiting_resource','stopping'].includes(e.status)&&!e.controller_alive?' · 执行器存活未确认':''}</p>
   {e.error&&<p className="rw-error">{e.error}</p>}
   <div className="rw-buttons">{compact?<button className="primary-button" onClick={onOpen}>查看实时矩阵与曲线</button>:<button className="outline-button" onClick={()=>onConversation(e.conversation_id)}>回到对话管理训练</button>}</div>
  </section>
  {!compact&&<>
   <BudgetView experiment={e}/>
   <section className="rw-card"><header><h2>实时实验矩阵</h2><span className="rw-caption">按执行回执统计 · 不包含历史报告</span></header><div className="rw-buttons" aria-label="矩阵阶段筛选">{[['all','全部'],['fit','训练'],['evaluate','评估']].map(([id,label])=><button key={id} aria-pressed={phase===id} className={phase===id?'primary-button':'outline-button'} onClick={()=>setPhase(id)}>{label}</button>)}</div><div className="rw-table-scroll"><table className="tp-matrix"><thead><tr><th>单元</th><th>阶段</th><th>参数</th><th>状态</th><th>尝试 / 重试</th><th>进度</th></tr></thead><tbody>{e.units.filter(u=>phase==='all'||u.phase===phase).map(u=><tr key={u.id} aria-selected={selectedUnit?.id===u.id}><th><button className="text-link" onClick={()=>chooseUnit(u.id)}>{u.label}</button></th><td>{u.phase==='fit'?'训练':'评估'}</td><td><details><summary>{Object.entries(u.parameters||{}).filter(([k])=>['model','model_id','seed','fold'].includes(k)).map(([k,v])=>k+'='+String(v)).join(' · ')||'查看参数'}</summary>{Object.entries(u.parameters||{}).map(([k,v])=><p key={k}>{k}={String(v)}</p>)}</details></td><td><Status status={u.status}/></td><td>{u.attempt_count} / {u.retry_count}</td><td>{u.id===e.current?.unit_id&&e.current.last_epoch!=null?'Epoch '+e.current.last_epoch:u.attempt_id?<button onClick={()=>chooseUnit(u.id)}>曲线与日志</button>:'等待执行'}</td></tr>)}</tbody></table></div></section>
   <section ref={detailRef} className="rw-card tp-detail"><header><div><h2>{selectedUnit?.label||'单元详情'}</h2><p className="rw-caption">曲线与日志按尝试隔离，失败记录保留</p></div><button className="outline-button" onClick={()=>chooseUnit('')}>跟随当前单元</button></header>
    {attempt?<><ComposerSelect label="查看执行尝试" variant="form" value={attempt.id} options={attempts.map((a,i)=>({value:a.id,label:`第 ${i+1} 次 · ${labels[a.status]||a.status} · ${time(a.started_at)}`}))} onChange={setAttemptId}/><p className="rw-caption">本次 {attempt.elapsed_seconds.toFixed(1)} 秒 · {attempt.charged?'已记账':'执行中累计'}{!attempt.current_scope?' · 历史范围':''}</p>
     {read.error&&<p className="rw-error" role="alert">{read.error}</p>}
     {telemetry?<><div className="tp-charts"><Curve points={telemetry.points} title="损失曲线" kind="loss"/><Curve points={telemetry.points} title="验证曲线" kind="validation"/></div><p className="rw-caption">已上报 epoch {telemetry.last_epoch??'未知'} · 指标来自任务输出，未作科学核验</p>{telemetry.notices.map(n=><p className="rw-caption" key={n}>{n}</p>)}<details><summary>指标数值与来源（{telemetry.points.length} 个 epoch）</summary><p className="rw-caption">{telemetry.sources.join('、')||'尚无结构化指标文件'}</p><div className="rw-table-scroll"><table><thead><tr><th>Epoch</th><th>已上报指标</th></tr></thead><tbody>{telemetry.points.map(p=><tr key={p.epoch}><th>{p.epoch}</th><td>{Object.entries(p.metrics).map(([k,v])=>(metricNames[k]||k)+'='+v.toPrecision(5)).join(' · ')}</td></tr>)}</tbody></table></div></details><details className="tp-logs" open><summary>运行日志{telemetry.log_truncated?' · 最近 64 KiB':''}</summary><pre tabIndex={0} aria-label="本次尝试日志">{telemetry.log||'本次尝试尚无日志输出。'}</pre></details></>:<p role="status">正在读取本次尝试的指标与日志…</p>}
    </>:<p className="rw-muted">此单元尚未执行，没有可用曲线或日志。</p>}
   </section>
   <section className="rw-card"><header><h2>失败与重试历史</h2><span className="rw-caption">全部 {e.attempts.length} 次尝试</span></header><div className="rw-table-scroll"><table><thead><tr><th>开始时间</th><th>单元</th><th>状态</th><th>消耗（秒）</th><th>原因与记录</th></tr></thead><tbody>{[...e.attempts].reverse().map(a=><tr key={a.id}><td>{time(a.started_at)}</td><th>{e.units.find(u=>u.id===a.unit_id)?.label||a.unit_id}</th><td><Status status={a.status}/></td><td>{a.elapsed_seconds.toFixed(1)}</td><td>{a.error&&<p>{a.error}</p>}<button onClick={()=>chooseUnit(a.unit_id,a.id)}>查看此次日志</button></td></tr>)}</tbody></table></div>{!e.attempts.length&&<p>尚无执行尝试</p>}<details><summary>最近执行与授权事件（{e.events.length} 条）</summary>{e.events.map((v,i)=><p key={i}>{time(v.at)} · {events[v.kind]||v.kind}{v.status?' · '+(labels[v.status]||v.status):''}{v.error?' · '+v.error:''}{v.reason?' · '+v.reason:''}</p>)}</details></section>
   <details className="rw-card"><summary>冻结方案与执行身份</summary><p>{e.plan.protocol}</p><dl className="rw-facts-list"><dt>实验</dt><dd>{e.id}</dd><dt>登记任务</dt><dd>{e.plan.task_id}</dd><dt>当前运行</dt><dd>{e.run_id||'尚未启动'}</dd><dt>源码快照</dt><dd>{e.plan.snapshot_id}</dd><dt>环境</dt><dd>{e.plan.environment_id}</dd><dt>资源</dt><dd>{e.plan.gpu_uuid||'CPU'} · {e.plan.memory_gib} GiB</dd></dl></details>
  </>}
 </div>;
}
