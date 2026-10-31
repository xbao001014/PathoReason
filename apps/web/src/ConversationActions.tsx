import {useEffect,useRef,useState} from 'react';
import type {ManagedConversation,ConversationLifecycleView} from './generated';
import './conversationLifecycle.css';

const errors:Record<string,string>={conversation_busy:'会话仍在执行，请等待完成或停止后再操作。',context_operation_unresolved:'压缩结果尚未确认，请先核对上下文状态。',conversation_permission_pending:'仍有工具等待确认，请先处理。',permission_outcome_requires_native_reconciliation:'工具执行结果尚未确认，请先核对原生执行状态。',native_state_unavailable:'暂时无法核对引擎状态，请稍后重试。',native_deletion_unsupported:'此执行引擎暂不支持彻底删除，请使用归档。',native_child_sessions_exist:'原生会话包含派生会话，需先核对其归属；当前不会级联删除。',native_session_shared:'原生会话仍被其他对话引用，当前不会删除。',native_session_scope_mismatch:'原生会话所属目录不一致，已阻止删除。',native_deletion_unconfirmed:'原生删除尚未确认，请重试清理。',conversation_cleanup_incomplete:'清理未完成，请重试。'};
export function clearConversationCache(cid:string){
 try{for(const key of Object.keys(localStorage)){
  if(['draft:','skill:','model:','execution-mode:','refs:'].some(p=>key==='pathoreason:'+p+cid)||key.startsWith('pathoreason:reasoning:'+cid+':')||(key.startsWith('pathoreason:conversation:')&&localStorage.getItem(key)===cid))localStorage.removeItem(key);
 }}catch{/* Browser storage can be unavailable. */}
}
export function ConversationActions({conversation,onChange,close}:{conversation:ManagedConversation;onChange:(view:ConversationLifecycleView)=>Promise<void>;close:()=>void}){
 const ref=useRef<HTMLDialogElement>(null),[confirm,setConfirm]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[state,setState]=useState<ConversationLifecycleView|null>(null);
 useEffect(()=>{const dialog=ref.current!,previous=document.activeElement;dialog.showModal();return()=>{dialog.close();if(previous instanceof HTMLElement&&previous.isConnected)previous.focus();else document.querySelector<HTMLButtonElement>('.new-conversation')?.focus();};},[]);
 const removing=Boolean(conversation.deletion_state)||state?.state==='failed'||state?.state==='deleting';
 async function act(action:'archive'|'restore'|'delete'){
  setBusy(true);setError('');
  try{
   const base='/api/v1/conversations/'+conversation.id;
   const response=await fetch(base+(action==='delete'?(removing?'/deletion/reconcile':''):'/'+action),{method:action==='delete'&&!removing?'DELETE':'POST',headers:{'Content-Type':'application/json'},...(action==='delete'?{body:JSON.stringify({confirm:true})}:{})});
   const body=await response.json();if(!response.ok)throw new Error(errors[body.detail]||body.detail||'请求未完成，请重试。');
   const result=body as ConversationLifecycleView;setState(result);
   if(['deleting','failed','deleted'].includes(result.state))clearConversationCache(conversation.id);
   await onChange(result);
   if(result.state==='failed'||result.state==='deleting')setError(errors[result.error_code||'']||'清理未完成，可重试核对。');else close();
  }catch(e){setError(e instanceof Error?e.message:'请求未完成，请核对会话状态后重试。');}finally{setBusy(false);}
 }
 return <dialog ref={ref} className="conversation-dialog" aria-labelledby="conversation-dialog-title" onCancel={e=>{e.preventDefault();if(!busy)close();}}>
  <header><h2 id="conversation-dialog-title">{confirm||removing?'删除会话':'管理会话'}</h2><button className="icon-button" aria-label="关闭" disabled={busy} onClick={close}>×</button></header>
  <div className="dialog-body"><p className="conversation-name">{conversation.title}</p>
   {confirm||removing?<><p>将永久清除该会话的聊天、上下文快照和 OpenCode 原生会话，无法恢复。</p><p>项目数据、模型写入的项目文件、成果、执行来源和已用预算保留。已导出的副本和备份不在本次清理范围。</p>{removing&&<p className="status-text status-warning">上次清理尚未完成；核对原生状态后继续清理。</p>}</>:<p>{conversation.status==='archived'?'恢复后可继续对话。':'归档后从默认列表隐藏，历史与上下文保留，可随时恢复。'}</p>}
   {error&&<p role="alert" className="status-text status-danger">{error}</p>}
   <footer><button disabled={busy} onClick={close}>取消</button>{confirm||removing?<button className="delete-conversation" disabled={busy} onClick={()=>act('delete')}>{busy?'正在核对与清理…':removing?'重试清理':'永久删除'}</button>:<><button disabled={busy} className="delete-conversation" onClick={()=>setConfirm(true)}>删除…</button><button className="primary-button" disabled={busy} onClick={()=>act(conversation.status==='archived'?'restore':'archive')}>{busy?'正在处理…':conversation.status==='archived'?'恢复会话':'归档会话'}</button></>}</footer>
  </div>
 </dialog>;
}
