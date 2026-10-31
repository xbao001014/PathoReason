import {useEffect,useRef,useState} from 'react';
import type {GpuSettingsView,HardwareSnapshot} from './generated';
import {formalApi} from './FormalStudy';
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
  <div className="hardware-section-heading"><h2>显卡{snapshot?' · '+(snapshot.gpus||[]).length:''}</h2><Info text="利用率为 0 不代表显卡未被占用，请同时查看显存。读数不代表资源预留；切换显卡请打开对话框内的显卡设置。"/></div>
  {snapshot?.gpu_error?<p role="status" className="status-text status-warning">暂时无法读取显卡状态。</p>:snapshot&&(snapshot.gpus||[]).length===0?<p>未检测到 NVIDIA 显卡。</p>:<div className="gpu-grid">{snapshot?.gpus?.map(gpu=><article className="hardware-card" key={gpu.uuid}><header><span className="gpu-index">GPU {gpu.index}</span><h3>{gpu.name}</h3></header><div className="gpu-metrics"><div><span>GPU 利用率</span><strong>{pct(gpu.utilization_percent)}</strong></div><div><span>显存已用 / 总计</span><strong>{gib(gpu.memory_used_mb)} / {gib(gpu.memory_total_mb)}</strong></div><div><span>温度</span><strong>{gpu.temperature_c==null?'未报告':gpu.temperature_c+' °C'}</strong></div></div>{gpu.memory_used_mb!=null&&gpu.memory_total_mb!=null&&<progress aria-label={'GPU '+gpu.index+' 显存使用率'} max={gpu.memory_total_mb} value={gpu.memory_used_mb}/>}<details className="gpu-identity"><summary>设备标识</summary><code>{gpu.uuid}</code></details></article>)}</div>}
 </section>;
}

export function GpuSelector({cid,disabled}:{cid:string;disabled:boolean}){
 const generation=useRef(0),request=useRef<AbortController|null>(null),saving=useRef(false);
 const dialog=useRef<HTMLDialogElement>(null),trigger=useRef<HTMLButtonElement>(null);
 const [setting,setSetting]=useState<GpuSettingsView|null>(null),[hardware,setHardware]=useState<HardwareSnapshot|null>(null);
 const [open,setOpen]=useState(false),[draft,setDraft]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(false);
 useEffect(()=>{const current=generation.current,controller=new AbortController();formalApi<GpuSettingsView>('/conversations/'+cid+'/gpu-settings',{signal:controller.signal}).then(v=>{if(!controller.signal.aborted&&current===generation.current)setSetting(v);}).catch(()=>{});return()=>{controller.abort();generation.current++;request.current?.abort();};},[cid]);
 useEffect(()=>{if(open)dialog.current?.showModal();return()=>{dialog.current?.close();};},[open]);
 function close(){if(saving.current)return;generation.current++;request.current?.abort();dialog.current?.close();setOpen(false);trigger.current?.focus();}
 async function refresh(reset=false){
  if(saving.current)return;
  const current=++generation.current;request.current?.abort();const controller=new AbortController();request.current=controller;setLoading(true);setError('');
  try{const [s,h]=await Promise.all([formalApi<GpuSettingsView>('/conversations/'+cid+'/gpu-settings',{signal:controller.signal}),formalApi<HardwareSnapshot>('/hardware',{signal:controller.signal})]);if(current===generation.current){setSetting(s);setHardware(h);setDraft(previous=>reset?s.gpu_uuid||'':previous);}}
  catch(e){if(current===generation.current)setError(e instanceof Error?(gpuErrors[e.message]||e.message):'读取失败');}
  finally{if(current===generation.current)setLoading(false);}
 }
 function show(){setOpen(true);setHardware(null);setDraft('');void refresh(true);}
 async function save(){
  if(!setting||!draft||disabled||loading||saving.current||hardware?.gpu_error||!hardware?.gpus?.some(g=>g.uuid===draft))return;
  saving.current=true;setBusy(true);setError('');
  try{const next=await formalApi<GpuSettingsView>('/conversations/'+cid+'/gpu-settings',{method:'PUT',body:JSON.stringify({expected_revision:setting.revision,gpu_uuid:draft})});setSetting(next);dialog.current?.close();setOpen(false);trigger.current?.focus();}
  catch(e){setError(e instanceof Error?(gpuErrors[e.message]||e.message):'保存失败');}
  finally{saving.current=false;setBusy(false);}
 }
 const selected=hardware?.gpus?.find(g=>g.uuid===setting?.gpu_uuid),mismatch=selected&&setting?.gpu_index!=null&&selected.index!==setting.gpu_index;
 const available=hardware&&!hardware.gpu_error&&hardware.gpus?.some(g=>g.uuid===draft);
 const label=setting?.source==='conversation'&&setting.gpu_index!=null?'GPU '+setting.gpu_index:setting?.source==='project'?'项目默认':'未选择';
 return <>
  <button ref={trigger} type="button" className="permission-trigger" aria-label="显卡设置" aria-haspopup="dialog" onClick={show}>显卡 · {label}</button>
  {open&&<dialog ref={dialog} className="gpu-dialog" aria-labelledby="gpu-dialog-title" onCancel={e=>{e.preventDefault();close();}} onClick={e=>{if(e.target===dialog.current)close();}}>
   <header><h2 id="gpu-dialog-title">训练显卡</h2><button type="button" className="icon-button" aria-label="关闭显卡设置" disabled={busy} onClick={close}>×</button></header>
   <form className="dialog-body" onSubmit={e=>{e.preventDefault();void save();}}>
    <div className="gpu-dialog-toolbar"><span>{hardware?'采样于 '+new Date(hardware.sampled_at).toLocaleTimeString():'读取设备信息'}</span><button type="button" className="text-link" disabled={busy||loading} onClick={()=>void refresh()}>{loading?'读取中…':'刷新状态'}</button></div>
    <div className="gpu-dialog-scroll">
     {mismatch&&<p role="status" className="status-text status-warning">原配置索引与当前设备不一致，请选择并保存以更新绑定。</p>}
     {hardware&&!hardware.gpu_error&&setting?.gpu_uuid&&!selected&&<p role="status" className="status-text status-warning">原绑定设备未识别，请选择当前可用设备。</p>}
     {hardware?.gpu_error?<p role="alert" className="status-text status-warning">暂时无法读取显卡状态，请刷新后重试。</p>:hardware&&(hardware.gpus||[]).length===0?<p>未检测到 NVIDIA 显卡。</p>:null}
     <fieldset className="gpu-choices" disabled={disabled||busy||loading||Boolean(hardware?.gpu_error)}><legend className="sr-only">选择训练显卡</legend>
      {hardware?.gpus?.map(gpu=><label className="gpu-choice" key={gpu.uuid}>
       <span className="gpu-choice-heading"><input type="radio" name="training-gpu" value={gpu.uuid} checked={draft===gpu.uuid} onChange={()=>setDraft(gpu.uuid)} aria-label={'GPU '+gpu.index+' · '+gpu.name}/><span><strong>GPU {gpu.index} · {gpu.name}</strong>{gpu.uuid===setting?.gpu_uuid&&<small>当前绑定</small>}</span></span>
       <span className="gpu-choice-metrics"><span className="gpu-choice-wide"><span>显存已用 / 总计</span><strong>{gib(gpu.memory_used_mb)} / {gib(gpu.memory_total_mb)}</strong></span><span><span>可用显存</span><strong>{gpu.memory_total_mb!=null&&gpu.memory_used_mb!=null?gib(Math.max(0,gpu.memory_total_mb-gpu.memory_used_mb)):'未报告'}</strong></span><span><span>GPU 利用率 / 温度</span><strong>{pct(gpu.utilization_percent)} / {gpu.temperature_c==null?'未报告':gpu.temperature_c+' °C'}</strong></span></span>
       <span className="gpu-choice-uuid">{gpu.uuid}</span>
      </label>)}
     </fieldset>
    </div>
    <p className="gpu-dialog-scope">仅用于当前对话后续的新计算任务，不迁移运行中的任务或预留资源。</p>
    {disabled&&<p role="status">当前会话暂不可修改显卡，可查看设备状态。</p>}
    {error&&<p role="alert" className="status-text status-danger">{error}</p>}
    <footer><button type="button" disabled={busy} onClick={close}>取消</button><button className="primary-button" disabled={!setting||!available||busy||loading||disabled}>{busy?'保存中…':'保存选择'}</button></footer>
   </form>
  </dialog>}
 </>;
}
