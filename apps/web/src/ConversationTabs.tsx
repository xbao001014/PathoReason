import type {ManagedProject} from './generated';
export type ConversationTab='open'|'archived';
export function conversationTab(conversation:{status:string;deletion_state?:string|null},project?:{status:string;deletion_state?:string|null}):ConversationTab{
 if(project?.deletion_state||conversation.deletion_state)return 'open';
 return project?.status==='archived'||conversation.status==='archived'?'archived':'open';
}
export function projectInTab(project:ManagedProject,tab:ConversationTab){
 if(project.deletion_state)return tab==='open';
 return tab==='open'?project.status==='active':project.status==='archived'||(project.archived_conversations??0)>0;
}
export function ConversationTabs({value,onChange,projects,loading}:{value:ConversationTab;onChange:(value:ConversationTab)=>void;projects:ManagedProject[];loading:boolean}){
 const tabs=[{id:'open',label:'对话'},{id:'archived',label:'已归档'}] as const;
 return <div className="conversation-tabs" role="tablist" aria-label="项目与对话分类">{tabs.map((tab,index)=><button key={tab.id} id={'conversation-tab-'+tab.id} role="tab" aria-selected={value===tab.id} aria-controls="conversation-tabpanel" tabIndex={value===tab.id?0:-1} title={loading?'正在读取项目':projects.filter(p=>projectInTab(p,tab.id)).length+' 个项目'} onClick={()=>onChange(tab.id)} onKeyDown={event=>{const next=event.key==='Home'?0:event.key==='End'?1:['ArrowLeft','ArrowRight'].includes(event.key)?1-index:null;if(next===null)return;event.preventDefault();onChange(tabs[next].id);document.getElementById('conversation-tab-'+tabs[next].id)?.focus();}}>{tab.label}<span>（{loading?'…':projects.filter(p=>projectInTab(p,tab.id)).length}）</span></button>)}</div>;
}
