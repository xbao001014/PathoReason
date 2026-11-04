// Coalesce invalidations during an in-flight read into one subsequent fresh read.
// A timer only checks for progress; it must not create an ever-growing backlog.
export function createRefreshScheduler(read:()=>Promise<void>){
 let running:Promise<void>|undefined,again=false,disposed=false;
 function request():Promise<void>{
  if(disposed)return Promise.resolve();
  again=true;
  if(!running)running=(async()=>{do{again=false;await read();}while(again&&!disposed);})().finally(()=>{running=undefined;});
  return running;
 }
 return {request,poll:()=>running||request(),dispose:()=>{disposed=true;again=false;}};
}
