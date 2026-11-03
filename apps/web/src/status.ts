/** design.md: status meaning is shared; unknown states remain neutral. */
export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';
const tones: Record<string, StatusTone> = {
  gpu_idle:'success',gpu_busy:'danger',
  admitted:'success',awaiting_review:'warning',needs_repair:'danger',needs_reconciliation:'warning',budget_exhausted:'danger',
  active:'info',paused:'danger',blocked:'warning',waiting_input:'warning',waiting:'warning',
  running:'info', interrupt_requested:'info', pending_login:'info',
  completed:'success', passed:'success', connected:'success', authenticated:'success', ready:'success',
  failed:'danger', error:'danger', cancelled:'danger', interrupted:'danger', stopped:'danger', runtime_unavailable:'danger',
  draft:'warning',waiting_resource:'warning',stopping:'info',
  queued:'warning', pending:'warning', recovery_required:'warning', credential_missing:'warning', reload_required:'warning',
  not_checked:'neutral', not_authenticated:'neutral', unavailable:'neutral', not_started:'neutral', unknown:'neutral',
};
export function statusTone(status: string | undefined): StatusTone {return tones[status || 'unknown'] || 'neutral';}
const labels: Record<string,string>={completed:'已完成',running:'进行中',pending:'待处理',queued:'待处理',error:'失败',failed:'失败',cancelled:'已取消',interrupted:'已停止',stopped:'已停止'};
export function statusLabel(status:string):string{return labels[status] || status;}
export function factTone(label:string,value:string):StatusTone {
  if(label==='完整研究目标')return value==='已达成'?'success':'warning';
  if(label==='投稿就绪')return value==='是'?'success':'warning';
  if(label==='独立科学审核')return value==='尚未完成'?'warning':'neutral';
  if(label==='论文状态')return value==='可供作者审阅'?'warning':'neutral';
  return 'neutral';
}
