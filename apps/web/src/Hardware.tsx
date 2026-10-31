import {useEffect,useRef,useState} from 'react';
import type {GpuSettingsView,HardwareSnapshot} from './generated';
import {formalApi} from './FormalStudy';
import {ComposerSelect} from './ComposerSelect';
import {Info} from './BusinessPanel';
import './hardware.css';

const gib=(mb:number|null|undefined)=>mb==null?'未报告':(mb/1024).toFixed(1)+' GiB';
const pct=(value:number|null|undefined)=>value==null?'未报告':value.toFixed(0)+'%';
const gpuErrors:Record<string,string>={conversation_busy:'当前回合仍在执行，请结束后切换。',conversation_archived:'请先恢复会话。',conversation_deletion_pending:'会话正在清理。',gpu_settings_revision_conflict:'其他窗口已更新选择，请刷新后重试。',gpu_not_found:'这张显卡已不在当前设备列表中，请刷新。',gpu_metrics_unavailable:'暂时无法读取显卡，未更改选择。',compute_config_unavailable:'项目计算配置尚未就绪，暂不能绑定显卡。',compute_config_changed:'计算配置已变化，请先核对配置。',native_state_unavailable:'暂时无法核对执行状态，请稍后重试。',context_operation_unresolved:'上下文操作结果尚未确认，请先核对。'};

export function HardwarePage(){
 const [snapshot,setSnapshot]=useState<HardwareSnapshot|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[revision,setRevision]=useState(0);
 useEffect(()=>{let stopped=false,timer:ReturnType<typeof setTimeout>|undefined,controller:AbortController|undefined;
  async function refresh(){if(stopped||document.hidden)return;const request=new AbortController();controller=request;setLoading(true);try{const next=await formalApi<HardwareSnapshot>('/hardware',{signal:request.signal});if(!stopped&&!request.signal.aborted){setSnapshot(next);setError('');}}catch(e){if(!stopped&&!request.signal.aborted)setError('读取失败；已有读数为上次采样，请稍后重试。');}finally{if(!stopped&&controller===request){setLoading(false);if(!document.hidden&&!request.signal.aborted)timer=setTimeout(refresh,5000);}}}
  function visibility(){clearTimeout(timer);controller?.abort();if(!document.hidden)refresh();}
  refresh();document.addEventListener('visibilitychange',visibility);return()=>{stopped=true;clearTimeout(timer);controller?.abort();document.removeEventListener('visibilitychange',visibility);};
 },[revision]);
 return <section className="hardware-page"><header className="hardware-heading"><div><h1>硬件设备</h1><p>{snapshot?.environment||'服务器'} · 当前页面可见时每 5 秒刷新{snapshot?' · '+new Date(snapshot.sampled_at).toLocaleTimeString():''}</p></div><button className="outline-button" disabled={loading} onClick={()=>setRevision(r=>r+1)}>{loading?'读取中…':'刷新'}</button></header>
  {error&&<p role="alert" className="status-text status-danger">{error}</p>}
  <div className="host-metrics"><article className="hardware-card"><h2>CPU</h2><strong className="hardware-number">{pct(snapshot?.cpu_percent)}</strong><p>{snapshot?.cpu_count??'—'} 个逻辑核心</p>{snapshot?.cpu_percent!=null&&<progress aria-label="CPU 使用率" max={100} value={snapshot.cpu_percent}/>}</article><article className="hardware-card"><h2>内存</h2><strong className="hardware-number">{gib(snapshot?.memory_used_mb)}</strong><p>总计 {gib(snapshot?.memory_total_mb)}</p>{snapshot?.memory_used_mb!=null&&snapshot.memory_total_mb!=null&&<progress aria-label="内存使用率" max={snapshot.memory_total_mb} value={snapshot.memory_used_mb}/>}</article></div>
  {snapshot?.cpu_error&&<p className="status-text status-warning">CPU 或内存读数暂不可用。</p>}
  <div className="hardware-section-heading"><h2>显卡{snapshot?' · '+(snapshot.gpus||[]).length:''}</h2><Info text="利用率为 0 不代表显卡未被占用，请同时查看显存。读数不代表资源预留；切换显卡在对话框下方操作。"/></div>
  {snapshot?.gpu_error?<p role="status" className="status-text status-warning">暂时无法读取显卡状态。</p>:snapshot&&(snapshot.gpus||[]).length===0?<p>未检测到 NVIDIA 显卡。</p>:<div className="gpu-grid">{snapshot?.gpus?.map(gpu=><article className="hardware-card" key={gpu.uuid}><header><span className="gpu-index">GPU {gpu.index}</span><h3>{gpu.name}</h3></header><div className="gpu-metrics"><div><span>GPU 利用率</span><strong>{pct(gpu.utilization_percent)}</strong></div><div><span>显存已用 / 总计</span><strong>{gib(gpu.memory_used_mb)} / {gib(gpu.memory_total_mb)}</strong></div><div><span>温度</span><strong>{gpu.temperature_c==null?'未报告':gpu.temperature_c+' °C'}</strong></div></div>{gpu.memory_used_mb!=null&&gpu.memory_total_mb!=null&&<progress aria-label={'GPU '+gpu.index+' 显存使用率'} max={gpu.memory_total_mb} value={gpu.memory_used_mb}/>}<details className="gpu-identity"><summary>设备标识</summary><code>{gpu.uuid}</code></details></article>)}</div>}
 </section>;
}

export function GpuSelector({cid,disabled}:{cid:string;disabled:boolean}){
 const generation=useRef(0);
 const [setting,setSetting]=useState<GpuSettingsView|null>(null),[hardware,setHardware]=useState<HardwareSnapshot|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let live=true;setSetting(null);setError('');Promise.all([formalApi<GpuSettingsView>('/conversations/'+cid+'/gpu-settings'),formalApi<HardwareSnapshot>('/hardware')]).then(([s,h])=>{if(live){setSetting(s);setHardware(h);}}).catch(e=>{if(live)setError(gpuErrors[e.message]||e.message);});return()=>{live=false;};},[cid]);
 async function refresh(){const request=++generation.current;try{const [s,h]=await Promise.all([formalApi<GpuSettingsView>('/conversations/'+cid+'/gpu-settings'),formalApi<HardwareSnapshot>('/hardware')]);if(request===generation.current){setSetting(s);setHardware(h);setError('');}}catch(e){if(request===generation.current)setError(e instanceof Error?(gpuErrors[e.message]||e.message):'读取失败');}}
 async function choose(uuid:string){if(!setting)return;generation.current++;setBusy(true);setError('');try{setSetting(await formalApi<GpuSettingsView>('/conversations/'+cid+'/gpu-settings',{method:'PUT',body:JSON.stringify({expected_revision:setting.revision,gpu_uuid:uuid})}));}catch(e){setError(e instanceof Error?(gpuErrors[e.message]||e.message):'保存失败');}finally{setBusy(false);}}
 const selected=hardware?.gpus?.find(g=>g.uuid===setting?.gpu_uuid),mismatch=selected&&setting?.gpu_index!=null&&selected.index!==setting.gpu_index;
 const options=(hardware?.gpus||[]).map(g=>({value:g.uuid,label:'GPU '+g.index+' · '+g.name.replace('NVIDIA GeForce ','')+' · '+(g.memory_total_mb!=null&&g.memory_used_mb!=null?gib(Math.max(0,g.memory_total_mb-g.memory_used_mb))+' 可用':'显存未知')}));
 if(!options.some(o=>o.value===setting?.gpu_uuid))options.unshift({value:setting?.gpu_uuid||'',label:setting?.gpu_uuid?'原绑定设备未识别':'选择训练显卡'});
 return <div className="gpu-selector"><span className="gpu-selector-label">训练显卡</span><ComposerSelect label="选择训练显卡" variant="mode" value={setting?.gpu_uuid||''} options={options.map(o=>({...o,disabled:!o.value||!hardware?.gpus?.some(g=>g.uuid===o.value)}))} disabled={disabled||busy||!setting||Boolean(hardware?.gpu_error)} onOpen={refresh} onChange={choose}/><button className="text-link" type="button" disabled={busy} onClick={refresh} aria-label="刷新显卡状态">刷新</button><Info text="仅作用于当前对话后续回合的新计算任务，运行中的任务保持原显卡。按设备 UUID 绑定，不预留资源；既有训练授权和预算保持不变。"/>{busy&&<span role="status">正在保存…</span>}{mismatch&&<p className="status-text status-warning">原配置索引与当前设备不一致，请重新选择显卡。</p>}{hardware?.gpu_error&&<p className="status-text status-warning">显卡状态暂不可用。</p>}{error&&<p role="alert" className="status-text status-danger">{error}</p>}</div>;
}
