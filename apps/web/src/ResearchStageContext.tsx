import {createContext,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import type {ResearchStageView} from './generated';
import type {ManuscriptView} from './ManuscriptReview';
import {formalApi} from './FormalStudy';

type State={value:ResearchStageView|null;loaded:boolean;setValue:(value:ResearchStageView|null)=>void;updateReview:(review:ManuscriptView)=>void};
const Context=createContext<State|null>(null);
export function ResearchStageProvider({cid,enabled,running,children}:{cid:string;enabled:boolean;running:boolean;children:ReactNode}){
 const [value,setState]=useState<ResearchStageView|null>(null),[loaded,setLoaded]=useState(false),sequence=useRef(0);
 function setValue(next:ResearchStageView|null){setState(old=>{
  // A poll started before an author decision must not restore an older review.
  if(old?.conversation_id===next?.conversation_id&&Number(old?.manuscript_review?.revision)>Number(next?.manuscript_review?.revision))return {...next!,manuscript_review:old!.manuscript_review};
  return next;
 });}
 function updateReview(review:ManuscriptView){sequence.current++;setState(old=>old?{...old,manuscript_review:review as unknown as Record<string,unknown>}:old);}
 useEffect(()=>{
  if(!enabled)return;
  let alive=true,timer:ReturnType<typeof setTimeout>;
  async function refresh(){const request=++sequence.current;clearTimeout(timer);try{const next=await formalApi<ResearchStageView|null>('/conversations/'+cid+'/stage');if(alive&&request===sequence.current){setValue(next);setLoaded(true);}}catch{}finally{if(alive)timer=setTimeout(()=>{if(document.visibilityState==='visible')void refresh();else timer=setTimeout(refresh,15000);},running?5000:10000);}}
  const changed=(event:Event)=>{if((event as CustomEvent).detail===cid)void refresh();};
  window.addEventListener('pathoreason:stage-changed',changed);void refresh();
  return()=>{alive=false;clearTimeout(timer);window.removeEventListener('pathoreason:stage-changed',changed);};
 },[cid,enabled,running]);
 return <Context.Provider value={{value,loaded,setValue,updateReview}}>{children}</Context.Provider>;
}
export function useResearchStage(){const state=useContext(Context);if(!state)throw new Error('ResearchStageProvider required');return state;}
