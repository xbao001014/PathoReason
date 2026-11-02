import {forwardRef,useEffect,useImperativeHandle,useLayoutEffect,useRef,useState,type ReactNode,type CSSProperties} from 'react';
import {createPortal} from 'react-dom';
import type {TurnView} from './generated';
import {statusLabel,statusTone} from './status';
import './conversation-history.css';

const extraStatus:Record<string,string>={interrupt_requested:'正在停止',recovery_required:'需要核对连接'};
export type HistoryHandle={jumpTo:(id:string)=>boolean};
// A bounded excerpt of the existing text, never an additional model summary.
function excerpt(text:string,limit=160){
 const plain=text.replace(/```[\s\S]*?```/g,' [代码] ').replace(/!\[[^\]]*\]\([^)]*\)/g,' [图片] ').replace(/\[([^\]]+)\]\([^)]*\)/g,'$1').replace(/[#*`_>|]/g,'').replace(/\s+/g,' ').trim();
 return plain.length>limit?plain.slice(0,limit)+'…':plain;
}

export const ConversationHistory=forwardRef<HistoryHandle,{turns:TurnView[];children:ReactNode}>(function ConversationHistory({turns,children},ref){
 const frame=useRef<HTMLDivElement>(null),scroll=useRef<HTMLDivElement>(null),content=useRef<HTMLDivElement>(null);
 const following=useRef(true),closeTimer=useRef<ReturnType<typeof setTimeout>>(),highlightTimer=useRef<ReturnType<typeof setTimeout>>();
 const trigger=useRef<HTMLButtonElement|null>(null),popup=useRef<HTMLDivElement>(null),restoringFocus=useRef(false);
 const [current,setCurrent]=useState(''),[atLatest,setAtLatest]=useState(true),[height,setHeight]=useState(400);
 const [opened,setOpened]=useState<{start:number;end:number;mobile:boolean;top:number;left:number;width:number}|null>(null);
 const [search,setSearch]=useState(''),[navigationCenter,setNavigationCenter]=useState<number>();
 const lastText=turns.at(-1)?.text;
 function updatePosition(){
  const el=scroll.current;if(!el)return;
  const bottom=el.scrollHeight-el.clientHeight-el.scrollTop<32;
  following.current=bottom;setAtLatest(bottom);
  const top=el.getBoundingClientRect().top+32;
  const nodes=Array.from(el.querySelectorAll<HTMLElement>('.turn'));
  let id=nodes[0]?.id||'';
  for(const node of nodes){if(node.getBoundingClientRect().top<=top)id=node.id;else break;}
  if(bottom)id=nodes.at(-1)?.id||id;
  setCurrent(id);
 }
 function latest(dismissPreview=false){
  following.current=true;
  scroll.current?.scrollTo({top:scroll.current.scrollHeight,behavior:'instant'});
  setAtLatest(true);if(dismissPreview)setOpened(null);updatePosition();
 }
 function jumpTo(id:string){
  const node=document.getElementById(id),el=scroll.current;
  if(!node||!el||!el.contains(node))return false;
  following.current=false;setOpened(null);
  el.scrollTo({top:el.scrollTop+node.getBoundingClientRect().top-el.getBoundingClientRect().top-(window.matchMedia('(max-width:760px)').matches?48:16),behavior:'instant'});
  node.focus({preventScroll:true});
  el.querySelector('.history-located')?.classList.remove('history-located');
  node.classList.add('history-located');clearTimeout(highlightTimer.current);
  highlightTimer.current=setTimeout(()=>node.classList.remove('history-located'),1600);
  updatePosition();return true;
 }
 useImperativeHandle(ref,()=>({jumpTo}));
 useLayoutEffect(()=>{if(following.current)latest();},[turns.length,lastText]);
 useEffect(()=>{
  const el=scroll.current,body=content.current,container=frame.current;if(!el||!body||!container)return;
  let raf=0;
  const changed=()=>{cancelAnimationFrame(raf);raf=requestAnimationFrame(updatePosition);};
  const resize=new ResizeObserver(()=>{setHeight(container.clientHeight);const panel=container.parentElement!.getBoundingClientRect();setNavigationCenter(panel.top+panel.height/2-container.getBoundingClientRect().top);if(following.current)latest();else changed();});
  resize.observe(body);resize.observe(container);resize.observe(container.parentElement!);el.addEventListener('scroll',changed,{passive:true});
  // Stop following immediately on upward input, before a streaming update arrives.
  const wheel=(e:WheelEvent)=>{if(e.deltaY<0)following.current=false;};
  el.addEventListener('wheel',wheel,{passive:true});
  return()=>{resize.disconnect();el.removeEventListener('scroll',changed);el.removeEventListener('wheel',wheel);cancelAnimationFrame(raf);clearTimeout(closeTimer.current);clearTimeout(highlightTimer.current);};
 },[]);
 useEffect(()=>{
  if(!opened)return;
  const outside=(e:PointerEvent)=>{if(!popup.current?.contains(e.target as Node)&&!frame.current?.querySelector('.history-navigation')?.contains(e.target as Node))setOpened(null);};
  const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')dismiss();};
  const resize=()=>setOpened(null);
  document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);window.addEventListener('resize',resize);
  return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);window.removeEventListener('resize',resize);};
 },[opened]);
 function dismiss(){setOpened(null);restoringFocus.current=true;trigger.current?.focus();restoringFocus.current=false;}
 function show(button:HTMLButtonElement,start:number,end:number,mobile=false){
  clearTimeout(closeTimer.current);trigger.current=button;
  const rect=button.getBoundingClientRect(),bounds=frame.current!.getBoundingClientRect();
  const width=Math.min(340,mobile?bounds.width-24:window.innerWidth-24);
  const left=mobile?bounds.left+12:Math.min(rect.right+8,window.innerWidth-width-12);
  setSearch('');setOpened({start,end,mobile,width,left,top:Math.max(12,Math.min(rect.top,window.innerHeight-340))});
 }
 function delayClose(){clearTimeout(closeTimer.current);closeTimer.current=setTimeout(()=>{if(!popup.current?.contains(document.activeElement)&&document.activeElement!==trigger.current)setOpened(null);},180);}
 const capacity=Math.max(1,Math.floor((height-72)/18)),size=Math.max(1,Math.ceil(turns.length/capacity));
 const groups=Array.from({length:Math.ceil(turns.length/size)},(_,i)=>({start:i*size,end:Math.min(turns.length,(i+1)*size)}));
 const currentIndex=turns.findIndex(t=>t.turn.id===current);
 const entries=opened?turns.map((turn,index)=>({turn,index})).slice(opened.start,opened.end).filter(({turn})=>!search||((turn.user_text||'')+' '+turn.text).toLocaleLowerCase().includes(search.toLocaleLowerCase())):[];
 return <div className="conversation-timeline" ref={frame} style={{'--history-center':navigationCenter===undefined?'50%':navigationCenter+'px'} as CSSProperties}>
  <div className="message-scroll" ref={scroll}><div className="history-content" ref={content}>{children}</div></div>
  {turns.length>0&&<nav className="history-navigation" aria-label="对话历史导航">
   <div className="history-rail">{groups.map(({start,end})=>{
    const selected=currentIndex>=start&&currentIndex<end,automatic=end-start===1&&turns[start].origin==='goal';
    return <button key={turns[start].turn.id} className={'history-mark'+(selected?' is-current':'')+(automatic?' is-automatic':'')} aria-current={selected?'location':undefined} aria-label={end-start===1?`第 ${start+1} 轮：${excerpt(turns[start].origin==='goal'?turns[start].text:turns[start].user_text,64)||'系统自动推进'}`:`第 ${start+1}–${end} 轮，展开历史概览`} aria-expanded={opened?.start===start&&!opened.mobile} aria-controls="conversation-history-preview"
     onMouseEnter={e=>show(e.currentTarget,start,end)} onMouseLeave={delayClose} onFocus={e=>{if(!restoringFocus.current)show(e.currentTarget,start,end);}} onBlur={delayClose}
     onClick={e=>end-start===1?jumpTo(turns[start].turn.id):show(e.currentTarget,start,end)}
     onKeyDown={e=>{if(e.key==='ArrowRight'){e.preventDefault();popup.current?.querySelector<HTMLButtonElement>('.history-entry')?.focus();}if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const buttons=Array.from(e.currentTarget.parentElement!.querySelectorAll<HTMLButtonElement>('button'));const index=buttons.indexOf(e.currentTarget);buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,index+(e.key==='ArrowDown'?1:-1)))]?.focus();}}}><span/></button>;
   })}</div>
   <button className="history-menu-button" aria-label="浏览对话历史" aria-expanded={Boolean(opened?.mobile)} aria-controls="conversation-history-preview" onClick={e=>opened?.mobile?setOpened(null):show(e.currentTarget,0,turns.length,true)}><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M4 6h16M4 12h12M4 18h8"/></svg></button>
  </nav>}
  {!atLatest&&turns.length>0&&<button className="history-latest" onClick={()=>latest(true)}>↓ 返回最新</button>}
  {opened&&createPortal(<div id="conversation-history-preview" className="history-preview" role="dialog" aria-label="历史对话概览" ref={popup} style={{top:opened.top,left:opened.left,width:opened.width}} onMouseEnter={()=>clearTimeout(closeTimer.current)} onMouseLeave={delayClose} onBlur={delayClose}>
   <header><strong>{opened.mobile?'对话历史':opened.end-opened.start>1?`第 ${opened.start+1}–${opened.end} 轮`:'对话概览'}</strong><button aria-label="关闭历史概览" onClick={dismiss}>×</button></header>
   {opened.mobile&&<input aria-label="搜索对话历史" placeholder="搜索历史内容" value={search} onChange={e=>setSearch(e.target.value)}/>}
   <div className="history-preview-list">{entries.map(({turn:t,index})=><button className="history-entry" key={t.turn.id} onClick={()=>jumpTo(t.turn.id)} aria-current={t.turn.id===current?'location':undefined}>
    <span className="history-entry-meta"><span>第 {index+1} 轮 · {t.origin==='goal'?'自动推进':'你的消息'}</span><span className={'status-text status-'+statusTone(t.turn.status)}>{extraStatus[t.turn.status]||statusLabel(t.turn.status)}</span></span>
    <strong>{t.origin==='goal'?'系统自动推进':excerpt(t.user_text,120)||'无消息正文'}</strong>
    <span className="history-excerpt">{excerpt(t.text,200)||'尚无回复正文'}</span>
    <time dateTime={t.turn.created_at}>{new Date(t.turn.created_at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</time>
   </button>)}{!entries.length&&<p>没有匹配的历史消息</p>}</div>
  </div>,document.body)}
 </div>;
});
