import type {GuidanceView,Choice} from './generated';
import './guidance.css';

export function Guidance({value,disabled,onChoose,onWrite}:{value:GuidanceView;disabled:boolean;onChoose:(option:Choice)=>void;onWrite:()=>void}){
 if(value.status==='pending')return null;
 if(value.status==='selected'){
  const choice=value.options.find(o=>o.id===value.selected_option_id);
  return <p className="guidance-history">已选择：{choice?.label||'继续下一步'}</p>;
 }
 if(value.status!=='available')return <details className="guidance-history"><summary>此前选项已失效</summary><p>{value.question}</p></details>;
 return <section className="dialogue-guidance" aria-label={value.kind==='clarification'?'需要选择':'下一步'}>
  <h3>{value.question}</h3>
  <div className="guidance-options">{value.options.map(option=><button type="button" key={option.id} disabled={disabled} className={'guidance-option'+(value.kind==='next_step'&&value.options.length===1?' primary-choice':'')} onClick={()=>onChoose(option)}>
   <strong>{option.label}</strong>{option.description&&<span>{option.description}</span>}<span className="guidance-scope">{{clarify:'仅确定方向',plan:'方案修改与准备',inspect:'只读检查',continue:'按选择继续当前目标'}[option.scope]}</span>
  </button>)}</div>
  <button type="button" className="guidance-freeform text-link" disabled={disabled} onClick={onWrite}>补充或调整</button>
 </section>;
}
