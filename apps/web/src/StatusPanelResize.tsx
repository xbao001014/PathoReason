import {useEffect,useRef,useState} from 'react';

const keyForScreen=()=> 'pathoreason:status-panel-height:'+(matchMedia('(max-width:760px)').matches?'compact':'wide');
function readHeight(key:string){try{const raw=localStorage.getItem(key),value=Number(raw);return raw!==null&&Number.isFinite(value)&&value>=0&&value<=4096?value:null;}catch{return null;}}

/** The panel grows upward from the composer; only this small handle re-renders while dragging. */
export function StatusPanelResize({expanded,bodyId}:{expanded:boolean;bodyId:string}){
 const handle=useRef<HTMLDivElement>(null),resize=useRef<(height:number|null)=>void>(()=>{});
 const preferred=useRef<number|null>(null),storageKey=useRef('');
 const drag=useRef<{pointer:number;y:number;height:number;previous:number|null}|null>(null);
 const limits=useRef({min:0,max:0,height:0});
 const [value,setValue]=useState({min:0,max:0,height:0}),[dragging,setDragging]=useState(false);
 function save(){try{if(preferred.current===null)localStorage.removeItem(storageKey.current);else localStorage.setItem(storageKey.current,String(Math.round(preferred.current)));}catch{}}
 function finish(commit:boolean){
  const current=drag.current;if(!current)return;drag.current=null;setDragging(false);
  if(!commit)resize.current(current.previous);else save();
  if(handle.current?.hasPointerCapture(current.pointer))handle.current.releasePointerCapture(current.pointer);
 }
 useEffect(()=>{
  const grip=handle.current,body=grip?.parentElement,chat=body?.closest('.chat-layout'),composer=body?.closest('.composer-area'),timeline=chat?.querySelector('.conversation-timeline');
  if(!grip||!body||!chat||!composer||!timeline||!expanded)return;
  let frame=0;const viewport=window.visualViewport;
  function measure(){
   frame=0;if(!body||!chat||!composer||!timeline)return;
   const key=keyForScreen();if(key!==storageKey.current){storageKey.current=key;preferred.current=readHeight(key);}
   const viewportHeight=viewport?.height??innerHeight,viewportBottom=(viewport?.offsetTop??0)+viewportHeight;
   const bodyHeight=body.getBoundingClientRect().height;
   const overhang=Math.max(0,composer.getBoundingClientRect().bottom-Math.min(chat.getBoundingClientRect().bottom,viewportBottom));
   const compact=matchMedia('(max-width:760px)').matches;
   const reserve=compact?32:Math.min(64,viewportHeight*.12);
   const max=Math.max(0,Math.floor(bodyHeight+timeline.getBoundingClientRect().height-reserve-overhang));
   const min=Math.min(144,max);
   const autoMax=Math.min(max,compact?Math.min(viewportHeight*.25,240):Math.min(viewportHeight*.42,480));
   body.style.maxHeight=(preferred.current===null?autoMax:max)+'px';
   body.style.height=preferred.current===null?'':Math.max(min,Math.min(max,preferred.current))+'px';
   body.toggleAttribute('data-resized',preferred.current!==null);
   const height=Math.round(body.getBoundingClientRect().height);limits.current={min,max,height};
   setValue(old=>old.min===min&&old.max===max&&old.height===height?old:{min,max,height});
  }
  const schedule=()=>{if(!frame)frame=requestAnimationFrame(measure);};
  resize.current=height=>{preferred.current=height;schedule();};
  const observer=new ResizeObserver(schedule);
  for(const element of [chat,composer,timeline,body])observer.observe(element);
  window.addEventListener('resize',schedule);viewport?.addEventListener('resize',schedule);viewport?.addEventListener('scroll',schedule);
  const cancel=()=>finish(false);window.addEventListener('blur',cancel);
  measure();
  return()=>{finish(false);resize.current=()=>{};cancelAnimationFrame(frame);observer.disconnect();window.removeEventListener('resize',schedule);viewport?.removeEventListener('resize',schedule);viewport?.removeEventListener('scroll',schedule);window.removeEventListener('blur',cancel);};
 },[expanded]);
 function reset(){resize.current(null);save();}
 return <div ref={handle} className="status-panel-resize" role="separator" tabIndex={0} aria-label="调整状态面板高度" aria-orientation="horizontal" aria-controls={bodyId} aria-valuemin={Math.min(value.min,value.height)} aria-valuemax={Math.max(value.max,value.height)} aria-valuenow={value.height} aria-valuetext={value.height+' 像素'} title="拖动调整高度，双击恢复默认；方向键微调，回车恢复默认" data-dragging={dragging}
  onPointerDown={event=>{if(!event.isPrimary||event.button!==0)return;event.preventDefault();event.currentTarget.focus({preventScroll:true});event.currentTarget.setPointerCapture(event.pointerId);drag.current={pointer:event.pointerId,y:event.clientY,height:limits.current.height,previous:preferred.current};setDragging(true);}}
  onPointerMove={event=>{const start=drag.current;if(!start||start.pointer!==event.pointerId)return;const {min,max}=limits.current;resize.current(Math.max(min,Math.min(max,start.height+start.y-event.clientY)));}}
  onPointerUp={event=>{if(drag.current?.pointer===event.pointerId)finish(true);}}
  onPointerCancel={()=>finish(false)} onLostPointerCapture={()=>finish(false)} onDoubleClick={reset}
  onKeyDown={event=>{if(event.key==='Escape'&&drag.current){event.preventDefault();event.stopPropagation();finish(false);return;}const {height,min,max}=limits.current;const next=event.key==='ArrowUp'?height+(event.shiftKey?64:24):event.key==='ArrowDown'?height-(event.shiftKey?64:24):event.key==='Home'?min:event.key==='End'?max:null;if(event.key==='Enter'){event.preventDefault();reset();}else if(next!==null){event.preventDefault();resize.current(Math.max(min,Math.min(max,next)));save();}}}
 ><span aria-hidden="true"/></div>;
}
