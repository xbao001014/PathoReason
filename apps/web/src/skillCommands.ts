import type {SkillDefinition} from './generated';

export type SkillContext={formal:boolean;synthetic:boolean;legacy:boolean;hasArtifacts:boolean};
export type SkillOption={skill:SkillDefinition;reason:string|null};

/** This route selects a capability; it never changes the conversation's permissions. */
export function skillOptions(skills:SkillDefinition[],context:SkillContext):SkillOption[]{
 return skills.map(skill=>{
  let reason:string|null=null;
  if(skill.runtime_readiness!=='ready')reason=skill.unavailable_reason||'当前环境不可用';
  else if(skill.capability_refs.includes('pathoreason:formal_study')){
   if(!context.formal)reason='仅正式试验项目可用';
  }else if(context.formal)reason='此场景用于普通项目，请选择正式研究 Skill';
  else if(skill.id==='results_explanation'){
   if(!context.hasArtifacts)reason='当前项目尚无可引用成果';
  }else if(skill.capability_refs.some(ref=>ref.startsWith('pathoreason.synthetic_mil:'))){
   if(context.legacy)reason='已有研究项目只读';
   else if(!context.synthetic)reason='请先将本轮执行权限切换为合成验证';
  }
  return {skill,reason};
 });
}

export type SkillCommand={query:string;body:string;hasSeparator:boolean};
/** Only a leading /skill token is a command; quoted code and file paths remain text. */
export function parseSkillCommand(text:string):SkillCommand|null{
 const match=/^\s*\/skill(?:\s+([\s\S]*))?$/.exec(text);
 if(!match)return null;
 const tail=match[1]||'';
 const parts=/^(\S*)(\s+)?([\s\S]*)$/.exec(tail)!;
 return {query:parts[1],body:parts[3]||'',hasSeparator:Boolean(parts[2])};
}

export function matchingSkills(command:SkillCommand,options:SkillOption[]):SkillOption[]{
 const query=command.query.toLocaleLowerCase();
 return options.filter(({skill})=>skill.id.toLocaleLowerCase().includes(query)||skill.title.toLocaleLowerCase().includes(query));
}

export function exactSkill(command:SkillCommand,options:SkillOption[]):SkillOption|undefined{
 const matches=options.filter(({skill})=>skill.id===command.query||skill.title===command.query);
 return matches.length===1?matches[0]:undefined;
}

export function resolveSkillMessage(text:string,selected:string|null,options:SkillOption[]):{text:string;skillId:string|null}{
 const command=parseSkillCommand(text);
 let skillId=selected,body=text.trim();
 if(command){
  if(!command.query)throw new Error('请选择一个 Skill，并填写任务。');
  const found=exactSkill(command,options);
  if(!found)throw new Error('未找到指定的 Skill，请从 /skill 列表选择。');
  if(found.reason)throw new Error(found.reason);
  skillId=found.skill.id;body=command.body.trim();
 }
 if(skillId){
  const found=options.find(o=>o.skill.id===skillId);
  if(!found)throw new Error('所选 Skill 已不可用，请重新选择。');
  if(found.reason)throw new Error(found.reason);
 }
 if(!body)throw new Error('请填写要交给 Skill 的任务。');
 return {text:body,skillId};
}
