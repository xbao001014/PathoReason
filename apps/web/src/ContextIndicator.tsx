import type {ContextView} from './generated';
import {Info} from './BusinessPanel';
import './context-indicator.css';

const compact=new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1});
export function ContextIndicator({context}:{context?:ContextView|null}){
 const used=context?.context_tokens,limit=context?.context_limit_tokens;
 const known=used!=null&&Number.isFinite(used)&&used>=0;
 const bounded=limit!=null&&Number.isFinite(limit)&&limit>0;
 const percent=known&&bounded?used/limit*100:null;
 const estimated=Boolean(context?.source?.includes('estimate'));
 const pending=context?.operations?.some(op=>op.status==='running'||op.status==='recovery_required');
 const label=pending?'上下文待核对':!known?'上下文未报告':percent==null?'上下文上限未知':'上下文'+(estimated?'约 ':' ')+percent.toFixed(1)+'%';
 const detail=pending?'压缩尚未确认，当前显示上次已知占用。':context?.source==='post_compaction_bytes_estimate'?'压缩后按保留内容字节保守估计，下一次调用后更新。':'随会话事件及每 4 秒刷新，数值来自最近已报告的调用，不代表尚未上报的生成内容。';
 const usage=known?'已用 '+used.toLocaleString()+' tokens；上限 '+(bounded?limit.toLocaleString()+' tokens':'未知')+'。':'运行时尚未报告上下文用量。';
 return <div className="context-indicator" aria-label="当前上下文占用">
  <span className="context-indicator-label">{label}</span>
  {known&&<span className="context-indicator-count">{compact.format(used)} / {bounded?compact.format(limit):'未知'} tokens</span>}
  <Info text={usage+detail}/>
 </div>;
}
