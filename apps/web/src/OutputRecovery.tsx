import {useEffect,useState} from 'react';
import type {OutputOptions,TurnOutputView,GoalControl} from './generated';
type ReasoningEffort=NonNullable<GoalControl['reasoning_effort']>;
import {formalApi} from './FormalStudy';
import {ComposerSelect} from './ComposerSelect';

export function OutputRecovery({turnId,busy,readOnly,onResume}:{turnId:string;busy:boolean;readOnly:boolean;onResume:(effort:ReasoningEffort,limit:number,model:string)=>Promise<void>}){
 const [info,setInfo]=useState<TurnOutputView|null>(null),[options,setOptions]=useState<OutputOptions|null>(null),[error,setError]=useState('');
 const [effort,setEffort]=useState<ReasoningEffort>('high'),[limit,setLimit]=useState(8192);
 useEffect(()=>{let live=true;setInfo(null);setError('');Promise.all([formalApi<TurnOutputView>('/turns/'+turnId+'/output'),formalApi<OutputOptions[]>('/models/output')]).then(([v,all])=>{if(!live)return;setInfo(v);setOptions(all.find(o=>o.model===v.model)||null);setLimit(v.output_limit_tokens||8192);setEffort(['none','low','high','max'].includes(v.reasoning_effort||'')?v.reasoning_effort as ReasoningEffort:'high');}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[turnId]);
 const count=(v:number|null|undefined)=>v==null?'未记录':v.toLocaleString();
 return <div className="output-recovery" aria-label="输出截断恢复">
  {info?<p className="output-usage">{info.model} 本次响应：思考 {count(info.reasoning_tokens)} · 正文 {count(info.output_tokens)} · 上限 {count(info.output_limit_tokens)} tokens</p>:<p>{error||'正在核对输出用量…'}</p>}
  {!readOnly&&info&&<form onSubmit={e=>{e.preventDefault();void onResume(effort,limit,info.model);}}>
   <div className="output-recovery-fields"><label>单次输出上限<ComposerSelect label="恢复输出上限" variant="form" value={String(limit)} disabled={busy} options={(options?.choices||[]).map(v=>({value:String(v),label:(v/1024)+'K tokens'}))} onChange={v=>setLimit(Number(v))}/></label>
   <label>思考强度<ComposerSelect label="恢复思考强度" variant="form" value={effort} disabled={busy} options={[{value:'none',label:'关闭思考'},{value:'low',label:'低'},{value:'high',label:'高'},{value:'max',label:'最高'}]} onChange={v=>setEffort(v as ReasoningEffort)}/></label></div>
   <p>思考与正文共用单次输出上限；调整不会增加项目总额度。恢复先核对已有成果，再按节点接续；再次截断会停止，不自动重试。</p>
   <button className="outline-button" type="submit" disabled={busy||!options?.choices.includes(limit)}>{busy?'正在恢复…':'按所选设置恢复'}</button>
   {error&&<p role="alert">{error}</p>}
  </form>}
 </div>;
}
