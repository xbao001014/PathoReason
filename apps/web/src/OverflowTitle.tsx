import {useLayoutEffect,useRef,useState,type CSSProperties} from 'react';

/** Preserve the complete accessible name; pan only titles that actually overflow. */
export function OverflowTitle({text}:{text:string}) {
  const viewport=useRef<HTMLSpanElement>(null),label=useRef<HTMLSpanElement>(null);
  const [distance,setDistance]=useState(0);
  useLayoutEffect(()=>{
    const outer=viewport.current!,inner=label.current!;
    let live=true;
    const measure=()=>{
      if(!live)return;
      const range=document.createRange();
      range.selectNodeContents(inner);
      setDistance(Math.max(0,Math.ceil(range.getBoundingClientRect().width-outer.clientWidth)));
    };
    const observer=new ResizeObserver(measure);
    observer.observe(outer);
    measure();
    document.fonts.ready.then(measure);
    return()=>{live=false;observer.disconnect();};
  },[text]);
  return <span ref={viewport} className={'overflow-title'+(distance>0?' can-pan':'')} title={text}
    style={{'--title-travel':`-${distance}px`,'--title-duration':`${Math.max(3,distance/35+2)}s`} as CSSProperties}>
    <span ref={label} className="overflow-title-text">{text}</span>
  </span>;
}
