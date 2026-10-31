import {useEffect,useId,useLayoutEffect,useRef,useState,type RefObject,type KeyboardEvent} from 'react';
import {createPortal} from 'react-dom';
import {exactSkill,matchingSkills,parseSkillCommand,type SkillOption} from './skillCommands';
import './skillCommands.css';

type Props={value:string;onChange:(value:string)=>void;onSelect:(id:string)=>void;onSubmit:()=>void;options:SkillOption[];inputRef:RefObject<HTMLTextAreaElement>;disabled:boolean;locked:boolean};

export function SkillCommandInput({value,onChange,onSelect,onSubmit,options,inputRef,disabled,locked}:Props){
 const id=useId(),menu=useRef<HTMLDivElement>(null),composing=useRef(false);
 const [focused,setFocused]=useState(false),[dismissed,setDismissed]=useState<string|null>(null),[active,setActive]=useState(0);
 const [position,setPosition]=useState<{left:number;top:number;width:number;maxHeight:number}|null>(null);
 const command=parseSkillCommand(value),matches=command?matchingSkills(command,options):[];
 const open=Boolean(command&&focused&&!disabled&&!locked&&dismissed!==value);
 const signature=matches.map(o=>o.skill.id+':'+o.reason).join('|');

 function choose(option:SkillOption){
  if(option.reason||locked||disabled||!command)return;
  onSelect(option.skill.id);onChange(command.body);setDismissed(null);inputRef.current?.focus();
 }
 function change(text:string,allowComplete=true){
  setDismissed(null);
  const next=parseSkillCommand(text),exact=next?exactSkill(next,options):undefined;
  if(allowComplete&&!composing.current&&!locked&&next?.hasSeparator&&exact&&!exact.reason){
   onSelect(exact.skill.id);onChange(next.body);
  }else onChange(text);
 }
 useEffect(()=>{setActive(Math.max(0,matches.findIndex(o=>!o.reason)));},[signature]);
 useLayoutEffect(()=>{
  if(!open){setPosition(null);return;}
  const popup=menu.current!;popup.setAttribute('popover','manual');popup.showPopover();
  const place=(event?:Event)=>{
   if(event?.type==='scroll'&&popup.contains(event.target as Node))return;
   const anchor=inputRef.current;if(!anchor)return;
   const rect=anchor.getBoundingClientRect(),tokens=getComputedStyle(anchor);
   const inset=parseFloat(tokens.getPropertyValue('--select-viewport-inset'))||12;
   const gap=parseFloat(tokens.getPropertyValue('--select-popup-gap'))||8;
   const width=Math.min(Math.max(360,Math.min(560,rect.width)),innerWidth-inset*2);
   const above=rect.top-gap-inset,below=innerHeight-rect.bottom-gap-inset;
   const up=above>=below,maxHeight=Math.max(0,Math.min(320,up?above:below));
   const height=Math.min(popup.scrollHeight||320,maxHeight);
   const next={left:Math.max(inset,Math.min(rect.left,innerWidth-width-inset)),top:up?rect.top-gap-height:rect.bottom+gap,width,maxHeight};
   setPosition(previous=>previous&&previous.left===next.left&&previous.top===next.top&&previous.width===next.width&&previous.maxHeight===next.maxHeight?previous:next);
  };
  const observer=new ResizeObserver(()=>place());observer.observe(popup);if(inputRef.current)observer.observe(inputRef.current);
  place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);
  return()=>{if(popup.matches(':popover-open'))popup.hidePopover();observer.disconnect();window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);};
 },[open,signature,inputRef]);
 useLayoutEffect(()=>{
  if(!open||!position)return;
  const popup=menu.current,item=popup?.querySelector<HTMLElement>(`[data-index="${active}"]`);
  if(!popup||!item)return;
  const bounds=popup.getBoundingClientRect(),r=item.getBoundingClientRect();
  if(r.top<bounds.top)popup.scrollTop-=bounds.top-r.top;
  else if(r.bottom>bounds.bottom)popup.scrollTop+=r.bottom-bounds.bottom;
 },[open,active,position?.maxHeight]);
 function keyDown(event:KeyboardEvent<HTMLTextAreaElement>){
  if(event.nativeEvent.isComposing||composing.current||event.keyCode===229)return;
  if(open){
   if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setDismissed(value);return;}
   const enabled=matches.map((o,i)=>o.reason?-1:i).filter(i=>i>=0);
   if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
    event.preventDefault();
    if(!enabled.length)return;
    if(event.key==='Home'||event.key==='End')setActive((event.key==='Home'?enabled[0]:enabled.at(-1))!);
    else {const offset=event.key==='ArrowDown'?1:-1;setActive(enabled[(enabled.indexOf(active)+offset+enabled.length)%enabled.length]);}
    return;
   }
   if((event.key==='Enter'||event.key==='Tab')&&!event.shiftKey){
    if(event.key==='Enter'||enabled.length){event.preventDefault();if(matches[active])choose(matches[active]);return;}
   }
  }
  if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();onSubmit();}
 }
 return <>
  <textarea ref={inputRef} disabled={disabled} role="combobox" aria-label="输入消息" aria-autocomplete="list"
   aria-haspopup="listbox" aria-expanded={open} aria-controls={open?id:undefined}
   aria-activedescendant={open&&matches[active]?`${id}-${active}`:undefined}
   value={value} placeholder="提出问题，或输入 /skill 选择技能…"
   onFocus={()=>setFocused(true)} onBlur={()=>setFocused(false)}
   onCompositionStart={()=>{composing.current=true;}} onCompositionEnd={event=>{composing.current=false;change(event.currentTarget.value);}}
   onChange={event=>change(event.target.value)} onKeyDown={keyDown}/>
  {open&&createPortal(<div ref={menu} id={id} role="listbox" aria-label="选择 Skill" className="composer-select-menu skill-command-menu"
   style={{...position,visibility:position?'visible':'hidden'}} onMouseDown={event=>event.preventDefault()}>
   {matches.length?matches.map((option,index)=><div key={option.skill.id} id={`${id}-${index}`} role="option"
    aria-label={option.skill.title} aria-selected={active===index&&!option.reason} aria-disabled={Boolean(option.reason)}
    data-index={index} className={'composer-select-option skill-command-option'+(active===index?' is-active':'')}
    onPointerMove={()=>{if(!option.reason)setActive(index);}} onClick={()=>choose(option)}>
    <strong>{option.skill.title}</strong><span>{option.skill.id}</span>{option.reason&&<small>{option.reason}</small>}
   </div>):<div className="skill-command-empty" role="status">未找到匹配的 Skill</div>}
  </div>,document.body)}
 </>;
}
