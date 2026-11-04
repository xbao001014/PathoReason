import type {SkillDefinition} from './generated';
import {skillOptions} from './skillCommands';
import type {GuideAction} from './usageGuideContent';
export type GuideContext={project:boolean;projectArchived:boolean;moduleState?:'loading'|'ready'|'error';hasGoal?:boolean;hasReview?:boolean;hasTraining?:boolean;conversation:boolean;formal:boolean;readOnly:boolean;deleting:boolean;busy:boolean;ready:boolean;legacy:boolean;hasArtifacts:boolean;synthetic:boolean;businessEnabled:boolean};
export function guideActionReason(action:GuideAction,c:GuideContext,skills:SkillDefinition[]):string|null{
 if(action.kind==='new'||action.kind==='settings'||action.kind==='hardware')return null;
 if(!c.project)return '请先选择或创建项目';
 if(action.kind==='project')return null;
 if(c.deleting)return '请先在项目管理中核对清理状态';
 if(action.kind==='workbench')return null;
 if(!c.conversation)return '请先选择一条对话';
 if(action.kind==='chat'||action.kind==='conversation')return null;
 if(action.kind==='focus'&&['stage','goal','training','review','gpu','permission','mode'].includes(action.target)&&!c.formal&&action.target!=='mode')return '仅正式试验项目提供此入口';
 if(action.kind==='focus'&&['goal','training','review'].includes(action.target)&&c.moduleState){
  if(c.moduleState==='loading')return '正在核对当前对话状态';
  if(c.moduleState==='error')return '状态读取失败，请先刷新状态';
  if(action.target==='goal'&&!c.hasGoal)return '当前对话尚无任务进度，发送任务后查看';
  if(action.target==='review'&&!c.hasReview)return '请先在阶段与交接中打开稿件对话';
  if(action.target==='training'&&!c.hasTraining)return '当前对话暂无训练模块，可在工作台核对已有实验';
 }
 if(action.kind==='budget'&&!c.formal)return '仅正式试验项目提供额度设置';
 if(action.kind==='context'||action.kind==='prompt'||(action.kind==='focus'&&['permission','gpu','output','mode'].includes(action.target))){
  if(c.readOnly)return '当前内容只读，请先恢复项目或对话';
  if(c.busy&&action.kind==='prompt')return '当前任务运行中，请稍后填写';
 }
 if(action.kind==='prompt'&&action.skillId){
  const skill=skills.find(s=>s.id===action.skillId);
  if(!skill||skill.implementation_status!=='implemented')return '此能力尚未接入';
  if(!c.ready)return '请先核对引擎连接';
  if(skill.evidence_scope==='synthetic'&&!c.businessEnabled)return '当前环境未开放合成验证';
  return skillOptions([skill],c)[0].reason;
 }
 return null;
}
