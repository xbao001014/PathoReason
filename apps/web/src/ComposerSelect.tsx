import {useEffect,useId,useLayoutEffect,useRef,useState,type KeyboardEvent,type ReactNode} from 'react';
import {createPortal} from 'react-dom';

type Option={value:string;label:string;disabled?:boolean};
type Props={label:string;value:string;options:Option[];onChange:(value:string)=>void;variant:'model'|'mode'|'form';icon?:ReactNode;disabled?:boolean};

/** Select-only combobox; portal keeps the rounded menu outside clipped panels, including modal dialogs. */
export function ComposerSelect({label,value,options,onChange,variant,icon,disabled=false}:Props){
  const id=useId(),trigger=useRef<HTMLButtonElement>(null),menu=useRef<HTMLDivElement>(null);
  const [portalHost,setPortalHost]=useState<HTMLElement>(document.body);
  const [open,setOpen]=useState(false),[active,setActive]=useState(0);
  const [position,setPosition]=useState<{left:number;top:number;width:number;maxHeight:number}|null>(null);
  const search=useRef({text:'',time:0}),revealActive=useRef(false);
  const selected=options.find(o=>o.value===value);
  function show(){if(disabled||trigger.current?.matches(':disabled'))return;setPortalHost(trigger.current?.closest('dialog')||document.body);revealActive.current=true;const index=options.findIndex(o=>o.value===value&&!o.disabled);setActive(index>=0?index:Math.max(0,options.findIndex(o=>!o.disabled)));setOpen(true);}
  function choose(index:number){const option=options[index];if(disabled||trigger.current?.matches(':disabled')||!option||option.disabled)return;onChange(option.value);setOpen(false);trigger.current?.focus();}
  function move(direction:number){revealActive.current=true;for(let step=1;step<=options.length;step++){const next=(active+direction*step+options.length)%options.length;if(!options[next].disabled){setActive(next);break;}}}
  function onKeyDown(event:KeyboardEvent<HTMLButtonElement>){
    if(['ArrowDown','ArrowUp','Enter',' '].includes(event.key)){
      event.preventDefault();
      if(!open){show();return;}
      if(event.key==='ArrowDown'||event.key==='ArrowUp')move(event.key==='ArrowDown'?1:-1);else choose(active);
    }else if(event.key==='Home'||event.key==='End'){
      event.preventDefault();revealActive.current=true;if(!open)show();
      const enabled=options.map((o,i)=>o.disabled?-1:i).filter(i=>i>=0);setActive((event.key==='Home'?enabled[0]:enabled.at(-1))??0);
    }else if(event.key==='Escape'&&open){event.preventDefault();event.stopPropagation();setOpen(false);}
    else if(event.key==='Tab')setOpen(false);
    else if(event.key.length===1&&!event.ctrlKey&&!event.metaKey&&!event.altKey){
      const now=Date.now();search.current={text:(now-search.current.time<700?search.current.text:'')+event.key.toLocaleLowerCase(),time:now};
      const index=options.findIndex(o=>!o.disabled&&o.label.toLocaleLowerCase().startsWith(search.current.text));
      if(index>=0){event.preventDefault();revealActive.current=true;if(!open)show();setActive(index);}
    }
  }
  useLayoutEffect(()=>{
    if(!open){setPosition(null);return;}
    // A top-layer popover remains interactive above its owning modal and escapes clipping.
    const popup=menu.current!;popup.setAttribute('popover','manual');popup.showPopover();
    const place=(event?:Event)=>{
      // Scrolling inside the popup does not move its trigger.
      if(event?.type==='scroll'&&menu.current?.contains(event.target as Node))return;
      const rect=trigger.current!.getBoundingClientRect(),tokens=getComputedStyle(trigger.current!);
      const gutter=parseFloat(tokens.getPropertyValue('--select-viewport-inset')),gap=parseFloat(tokens.getPropertyValue('--select-popup-gap'));
      const maxMenuHeight=parseFloat(tokens.getPropertyValue('--select-menu-max-height'));
      const width=Math.min(Math.max(variant==='form'?rect.width:240,rect.width),window.innerWidth-gutter*2);
      const below=window.innerHeight-rect.bottom-gap-gutter,above=rect.top-gap-gutter;
      const natural=Math.min(menu.current?.scrollHeight||maxMenuHeight,maxMenuHeight);
      const useAbove=below<natural&&above>below;
      const maxHeight=Math.max(0,Math.min(maxMenuHeight,useAbove?above:below));
      const height=Math.min(natural,maxHeight);
      const next={left:Math.max(gutter,Math.min(rect.left,window.innerWidth-width-gutter)),top:useAbove?rect.top-gap-height:rect.bottom+gap,width,maxHeight};
      setPosition(previous=>previous&&previous.left===next.left&&previous.top===next.top&&previous.width===next.width&&previous.maxHeight===next.maxHeight?previous:next);
    };
    const observer=new ResizeObserver(()=>place());if(menu.current)observer.observe(menu.current);if(trigger.current)observer.observe(trigger.current);
    place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);
    return()=>{if(popup.matches(':popover-open'))popup.hidePopover();observer.disconnect();window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);};
  },[open,options.length,portalHost,variant]);
  useEffect(()=>{
    if(!open)return;
    const outside=(event:PointerEvent)=>{if(!trigger.current?.contains(event.target as Node)&&!menu.current?.contains(event.target as Node))setOpen(false);};
    document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside);
  },[open]);
  useLayoutEffect(()=>{
    if(!open||!position||!revealActive.current)return;
    const popup=menu.current,option=popup?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    if(!popup||!option)return;
    revealActive.current=false;
    // Only keyboard navigation/opening reveals an option, and only this menu scrolls.
    const bounds=popup.getBoundingClientRect(),item=option.getBoundingClientRect();
    const top=bounds.top+popup.clientTop,bottom=top+popup.clientHeight;
    if(item.top<top)popup.scrollTop-=top-item.top;
    else if(item.bottom>bottom)popup.scrollTop+=item.bottom-bottom;
  },[open,active,position]);
  useEffect(()=>{if(disabled)setOpen(false);},[disabled]);
  return <>
    <button ref={trigger} type="button" className={'composer-select composer-select-'+variant} role="combobox" disabled={disabled}
      aria-label={label} aria-haspopup="listbox" aria-expanded={open} aria-controls={open?id:undefined}
      aria-activedescendant={open?`${id}-${active}`:undefined} title={selected?.label||value}
      onClick={()=>open?setOpen(false):show()} onKeyDown={onKeyDown} onBlur={()=>setOpen(false)}>
      {icon}<span className="select-value">{selected?.label||value}</span><svg className="select-chevron" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m7 10 5 5 5-5"/></svg>
    </button>
    {open&&createPortal(<div ref={menu} id={id} role="listbox" aria-label={label} className="composer-select-menu"
      style={{...position,visibility:position?'visible':'hidden'}} onMouseDown={e=>e.preventDefault()}>
      {options.map((option,index)=><div key={option.value} id={`${id}-${index}`} role="option" aria-selected={option.value===value}
        aria-disabled={option.disabled||undefined} data-index={index} className={'composer-select-option'+(active===index?' is-active':'')}
        onPointerMove={()=>{if(!option.disabled){revealActive.current=false;setActive(index);}}} onClick={()=>choose(index)}>
        <span>{option.label}</span><span className="option-check" aria-hidden="true">{option.value===value?'✓':''}</span>
      </div>)}
    </div>,portalHost)}
  </>;
}
