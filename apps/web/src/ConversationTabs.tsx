import type {ManagedConversation} from './generated';
export type ConversationTab='open'|'archived';
// Incomplete deletions remain reachable in the current list for reconciliation.
export function conversationTab(conversation:{status:string;deletion_state?:string|null}):ConversationTab{
 return conversation.status==='archived'&&!conversation.deletion_state?'archived':'open';
}
export function ConversationTabs({value,onChange,sessions,loading}:{value:ConversationTab;onChange:(value:ConversationTab)=>void;sessions:ManagedConversation[];loading:boolean}){
 const tabs=[{id:'open',label:'对话'},{id:'archived',label:'已归档'}] as const;
 return <div className="conversation-tabs" role="tablist" aria-label="当前项目对话分类">{tabs.map((tab,index)=><button key={tab.id} id={'conversation-tab-'+tab.id} role="tab" aria-selected={value===tab.id} aria-controls="conversation-tabpanel" tabIndex={value===tab.id?0:-1} onClick={()=>onChange(tab.id)} onKeyDown={event=>{
  const next=event.key==='Home'?0:event.key==='End'?1:['ArrowLeft','ArrowRight'].includes(event.key)?1-index:null;
  if(next===null)return;event.preventDefault();onChange(tabs[next].id);document.getElementById('conversation-tab-'+tabs[next].id)?.focus();
 }}>{tab.label}<span>（{loading?'…':sessions.filter(s=>conversationTab(s)===tab.id).length}）</span></button>)}</div>;
}
