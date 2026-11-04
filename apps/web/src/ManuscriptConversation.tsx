import {useEffect,useRef} from 'react';
import {ManuscriptReview,type ManuscriptView} from './ManuscriptReview';
import {useResearchStage} from './ResearchStageContext';

export function ManuscriptConversation({cid,readOnly,running,onChange,onError,onLocate}:{cid:string;readOnly:boolean;running:boolean;onChange:()=>void;onError:(e:unknown)=>void;onLocate:(id:string)=>void}){
 const {value,updateReview}=useResearchStage(),locate=useRef(onLocate);
 locate.current=onLocate;
 const owner=value?.conversation_id===cid,review=owner?value?.manuscript_review as unknown as ManuscriptView|undefined:undefined;
 useEffect(()=>{const open=(event:Event)=>{if((event as CustomEvent).detail===cid)locate.current('manuscript-review-'+cid);};window.addEventListener('pathoreason:open-manuscript-review',open);return()=>window.removeEventListener('pathoreason:open-manuscript-review',open);},[cid]);
 if(!review)return null;
 return <article id={'manuscript-review-'+cid} className="manuscript-conversation" tabIndex={-1} aria-label="稿件审核与作者决定">
  <div className="manuscript-conversation-meta"><span>作者审核</span><span className={'status-text status-'+(review.status==='awaiting_review'?'warning':review.index===5?'success':'info')}>{review.status==='awaiting_review'?'待你审阅':review.index===5?'交付已确认':'准备中'}</span></div>
  <ManuscriptReview key={cid} cid={cid} value={review} readOnly={readOnly} running={running} onError={onError} onUpdate={next=>{updateReview(next);onChange();}}/>
 </article>;
}
