import {useEffect,useRef,useState} from 'react';
import {ComposerSelect} from './ComposerSelect';
import {statusTone} from './status';
import type {ProviderSettingsView,RuntimeStatus} from './generated';
import './provider-settings.css';

const messages:Record<string,string>={provider_switch_busy:'有正在执行或等待处理的任务，请先完成或暂停后再切换。',
 provider_settings_stale:'配置已被其他窗口更新，请重新选择后保存。',provider_key_missing:'请填写此接入方式的 API Key。',
 provider_key_invalid:'API Key 格式无效，请检查是否包含空格或换行。',provider_endpoint_invalid:'请填写所选提供商的有效 HTTPS API 地址。',
 provider_configuration_invalid:'请检查配置内容后重试。',provider_switch_failed:'新配置加载失败，已恢复原配置。',
 provider_rollback_failed:'连接恢复失败，请联系维护者检查服务。',provider_runtime_unavailable:'模型服务暂时无法核对，请稍后重试。',model_not_configured:'请选择支持的模型。'};

async function request(init?:RequestInit):Promise<ProviderSettingsView>{
 const r=await fetch('/api/v1/settings/providers',{cache:'no-store',...init,headers:{'Content-Type':'application/json',...init?.headers}});
 const result=await r.json();if(!r.ok)throw new Error(messages[result.detail]||'配置操作失败，请稍后重试。');return result;
}

export function ProviderPanel({runtime,onApplied}:{runtime:RuntimeStatus;onApplied:(model:string)=>Promise<void>}){
 const [value,setValue]=useState<ProviderSettingsView|null>(null),[selected,setSelected]=useState(''),[model,setModel]=useState('');
 const [endpoint,setEndpoint]=useState(''),[key,setKey]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false);
 const mounted=useRef(true),submitting=useRef(false);
 function load(v:ProviderSettingsView){setValue(v);const p=v.profiles.find(p=>p.id===v.active)!;setSelected(p.id);setModel(p.model);setEndpoint(p.base_url);setKey('');}
 useEffect(()=>{mounted.current=true;const controller=new AbortController();request({signal:controller.signal}).then(v=>{if(mounted.current)load(v);}).catch(e=>{if(mounted.current&&e.name!=='AbortError')setError(e.message);});return()=>{mounted.current=false;controller.abort();};},[]);
 const profile=value?.profiles.find(p=>p.id===selected),active=value?.profiles.find(p=>p.id===value.active);
 function choose(id:string){const p=value!.profiles.find(p=>p.id===id)!;setSelected(id);setModel(p.model);setEndpoint(p.base_url);setKey('');setError('');setSaved(false);}
 async function save(){
  if(submitting.current||!value||!profile)return;
  submitting.current=true;setBusy(true);setError('');setSaved(false);
  try{
   const result=await request({method:'PUT',body:JSON.stringify({expected_revision:value.revision,provider_id:selected,base_url:endpoint.trim(),model,api_key:key.trim()||null})});
   if(mounted.current){load(result);setSaved(true);}
   await onApplied(result.profiles.find(p=>p.id===result.active)!.model);
  }catch(e){if(mounted.current){setError(e instanceof Error?e.message:'配置操作失败');try{const latest=await request();if(mounted.current)load(latest);}catch{/* Retain the actionable failure. */}}}
  finally{submitting.current=false;if(mounted.current){setBusy(false);setKey('');}}
 }
 return <section className="provider-settings" aria-label="模型接入设置" aria-busy={busy}>
  <div className="settings-heading"><div><h3>模型接入</h3><p>当前：{active?.title||runtime.provider_title||'正在读取…'}</p></div>
   <span className={'tag status-badge status-'+statusTone(runtime.connected?'ready':'failed')}>{runtime.connected?'引擎已连接':'引擎未连接'}</span></div>
  {value&&profile&&<><fieldset disabled={busy}>
   <div className="provider-field"><span>接入方式</span><ComposerSelect label="接入方式" value={selected} options={value.profiles.map(p=>({value:p.id,label:p.title}))} onChange={choose} variant="form" disabled={busy}/></div>
   <label>API 地址<input type="url" value={endpoint} onChange={e=>{setEndpoint(e.target.value);setSaved(false);}} autoComplete="off" spellCheck={false}/></label>
   <div className="provider-field"><span>默认模型</span><ComposerSelect label="默认模型" value={model} options={profile.models.map(m=>({value:m,label:m}))} onChange={v=>{setModel(v);setSaved(false);}} variant="form" disabled={busy}/></div>
   <label>API Key<input type="password" value={key} onChange={e=>{setKey(e.target.value);setSaved(false);}} autoComplete="new-password" maxLength={512} spellCheck={false} placeholder={profile.credential_present?'已保存；留空保留原 Key':'填写此接入方式的 Key'} aria-describedby="provider-key-note"/></label>
   <p id="provider-key-note" className="provider-hint">{profile.credential_present?'已保存的 Key 不会显示或回传。':'此接入方式尚未配置 Key。'}</p>
  </fieldset>
  <p className="provider-hint">应用到当前环境的所有对话；开发与交付环境分别保存。切换会重新加载模型连接。</p>
  <div className="provider-actions"><button className="primary-button" disabled={busy||(!profile.credential_present&&!key.trim())} onClick={save}>{busy?'正在应用…':'保存并应用'}</button></div></>}
  {error&&<p role="alert" className={'status-text status-'+statusTone('failed')}>{error}</p>}
  {saved&&<p role="status" className={'status-text status-'+statusTone('ready')}>配置已加载。实际模型调用结果以对话回执为准。</p>}
 </section>;
}
