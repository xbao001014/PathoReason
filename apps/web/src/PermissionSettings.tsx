import {ComposerSettingIcon,ComposerSettingValue} from './ComposerSetting';
import {useEffect,useRef,useState} from 'react';
import {ComposerSelect} from './ComposerSelect';
import {formalApi} from './FormalStudy';
import type {PermissionSettings as Policy,PermissionSettingsView} from './generated';
import './permissions.css';

const modes={ask:'逐次确认',auto:'自动批准',custom:'自定义'};
const permissionIcons={ask:'permissionAsk',auto:'permissionAuto',custom:'permissionCustom'} as const;
const tools={bash:'命令执行',edit:'文件修改',webfetch:'网络访问',external_directory:'外部目录'};
type Tool=keyof typeof tools;
function effective(policy:Policy):Record<Tool,'allow'|'ask'|'deny'>{
 return Object.fromEntries(Object.keys(tools).map(key=>[key,policy.mode==='auto'?'allow':policy.mode==='custom'?(policy[key as Tool]||'ask'):'ask'])) as Record<Tool,'allow'|'ask'|'deny'>;
}
function policyLabel(policy:Policy){return modes[policy.mode||'ask'];}
const errors:Record<string,string>={permission_settings_turn_active:'当前回合仍在执行，请结束后修改权限。',permission_settings_revision_conflict:'权限已在其他窗口更新，请关闭并重新打开设置。',permission_settings_native_mismatch:'原生权限尚未确认，未发送新请求。'};

export function PermissionSettings({cid,active}:{cid:string;active:boolean}){
 const [value,setValue]=useState<PermissionSettingsView|null>(null),[draft,setDraft]=useState<Policy|null>(null);
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const dialog=useRef<HTMLDialogElement>(null),trigger=useRef<HTMLButtonElement>(null);
 useEffect(()=>{let live=true;formalApi<PermissionSettingsView>('/conversations/'+cid+'/permission-settings').then(v=>{if(live){setValue(v);setDraft(v.settings);}}).catch(e=>{if(live)setError(String(e));});return()=>{live=false;};},[cid]);
 useEffect(()=>{if(open){dialog.current?.showModal();}return()=>{dialog.current?.close();};},[open]);
 function close(){if(busy)return;dialog.current?.close();setOpen(false);trigger.current?.focus();}
 async function show(){setOpen(true);setError('');setDraft(null);try{const v=await formalApi<PermissionSettingsView>('/conversations/'+cid+'/permission-settings');setValue(v);setDraft(v.settings);}catch(e){setError(e instanceof Error?e.message:String(e));}}
 async function save(){if(!value||!draft)return;setBusy(true);setError('');try{const v=await formalApi<PermissionSettingsView>('/conversations/'+cid+'/permission-settings',{method:'PUT',body:JSON.stringify({expected_revision:value.revision,settings:draft})});setValue(v);setDraft(v.settings);dialog.current?.close();setOpen(false);trigger.current?.focus();}catch(e){const message=e instanceof Error?e.message:String(e);setError(errors[message]||message);}finally{setBusy(false);}}
 return <>
  <button ref={trigger} type="button" className="permission-trigger composer-setting-trigger" aria-label="权限设置" aria-description={value?policyLabel(value.settings):'加载中'} aria-haspopup="dialog" aria-expanded={open} onClick={show}><ComposerSettingIcon name={value?permissionIcons[value.settings.mode||'ask']:'permission'}/><span>权限</span><ComposerSettingValue value={value?policyLabel(value.settings):'加载中'}/></button>
  {open&&<dialog ref={dialog} className="permission-dialog" onCancel={e=>{e.preventDefault();close();}} onClick={e=>{if(e.target===dialog.current)close();}}>
   <header><h2>权限设置</h2><button type="button" className="icon-button" aria-label="关闭权限设置" disabled={busy} onClick={close}>×</button></header>
   <form className="dialog-body" onSubmit={e=>{e.preventDefault();save();}}>
    {draft&&<>
     <fieldset disabled={busy||active}><legend>当前对话</legend><div className="permission-modes">{Object.entries(modes).map(([key,label])=><label key={key}><input type="radio" name="permission-mode" checked={draft.mode===key} onChange={()=>{const next={...draft,mode:key as Policy['mode']};setDraft({...next,...effective(next)});}}/>{label}</label>)}</div></fieldset>
     {draft.mode==='auto'&&<p className="permission-consequence">允许全部四项工具直接执行，可能修改文件、启动进程或产生费用。</p>}
     {draft.mode==='custom'&&<fieldset disabled={busy||active} className="permission-tools"><legend>实际工具权限</legend>{Object.entries(tools).map(([key,label])=><label key={key}>{label}<ComposerSelect label={label} variant="form" disabled={busy||active} value={effective(draft)[key as Tool]} options={[{value:'ask',label:'询问'},{value:'allow',label:'允许'},{value:'deny',label:'禁止'}]} onChange={value=>setDraft({...draft,...effective(draft),mode:'custom',[key]:value})}/></label>)}</fieldset>}
     <div className="permission-notes"><p className="permission-scope">仅作用于当前对话的后续回合。研究预算与审核要求保持不变。</p>
     <details><summary>会话授权与限制</summary><p>“本会话同类操作”按审批卡片展示的规则授权；切回逐次确认不会撤销这些原生会话授权。需要禁止某类操作时使用自定义“禁止”，或新建对话重新授权。工具权限不是操作系统沙箱。</p><a href="https://opencode.ai/docs/permissions/" target="_blank" rel="noreferrer">OpenCode 权限文档 ↗</a></details></div>
    </>}
    {active&&<p role="status">回合执行期间可查看，结束后可保存修改。</p>}
    {error&&<p role="alert" className="status-text status-danger">{error}</p>}
    <footer><button type="button" disabled={busy} onClick={close}>取消</button><button className="primary-button" disabled={!draft||busy||active}>保存权限</button></footer>
   </form>
  </dialog>}
 </>;
}
