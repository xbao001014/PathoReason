import type {GpuSettingsView,HardwareSnapshot} from './generated';

// A sampling estimate, not a process inventory or a resource reservation.
export const GPU_IDLE_MEMORY_MB=16;
export const GPU_SAMPLE_MAX_AGE_MS=15000;
const unknown=(label='未知')=>({state:'unknown',label});
export function gpuAvailability(setting:GpuSettingsView|null,snapshot:HardwareSnapshot|null,readable:boolean,now=Date.now()){
 if(!setting)return unknown('读取中');
 if(!setting.gpu_uuid)return unknown('未选择');
 if(!readable||!snapshot||snapshot.gpu_error)return unknown();
 const sampled=Date.parse(snapshot.sampled_at);
 if(!Number.isFinite(sampled)||now-sampled>GPU_SAMPLE_MAX_AGE_MS||sampled-now>5000)return unknown();
 const gpu=snapshot.gpus?.find(g=>g.uuid===setting.gpu_uuid);
 if(!gpu)return unknown('未识别');
 if(setting.gpu_index!=null&&setting.gpu_index!==gpu.index)return unknown('需核对');
 const used=gpu.memory_used_mb,util=gpu.utilization_percent;
 const memoryValid=typeof used==='number'&&Number.isFinite(used)&&used>=0&&(gpu.memory_total_mb==null||used<=gpu.memory_total_mb);
 const utilizationValid=typeof util==='number'&&Number.isFinite(util)&&util>=0&&util<=100;
 if((memoryValid&&used>GPU_IDLE_MEMORY_MB)||(utilizationValid&&util>0))return {state:'gpu_busy',label:'占用'};
 if(memoryValid&&utilizationValid)return {state:'gpu_idle',label:'空闲'};
 return unknown();
}
