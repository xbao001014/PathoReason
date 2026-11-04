import type {ReactNode} from 'react';

export function StageDisclosure({title,meta,defaultOpen=false,children}:{title:string;meta?:string;defaultOpen?:boolean;children:ReactNode}){
 return <details className="stage-disclosure" open={defaultOpen}>
  <summary><span className="stage-disclosure-title">{title}</span>{meta&&<span className="stage-disclosure-meta">{meta}</span>}<svg className="stage-disclosure-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg></summary>
  <div className="stage-disclosure-body">{children}</div>
 </details>;
}
