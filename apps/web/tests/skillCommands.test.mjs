import test from 'node:test';
import assert from 'node:assert/strict';
const {parseSkillCommand,matchingSkills,skillOptions,resolveSkillMessage}=await import(process.env.SKILL_COMMANDS_MODULE);
const skill={id:'pathology-data-api',title:'病理接口数据接入',runtime_readiness:'ready',capability_refs:['pathoreason:formal_study']};
const context={formal:true,synthetic:false,legacy:false,hasArtifacts:false};
const options=skillOptions([skill,{...skill,id:'locked',title:'尚未就绪',runtime_readiness:'unavailable',unavailable_reason:'依赖未安装'}],context);

test('command and Chinese search resolve the actual catalog ID',()=>{
 assert.deepEqual(resolveSkillMessage('/skill pathology-data-api 检查完整性',null,options),{text:'检查完整性',skillId:skill.id});
 assert.deepEqual(resolveSkillMessage('/skill 病理接口数据接入\n检查完整性',null,options),{text:'检查完整性',skillId:skill.id});
 assert.equal(matchingSkills(parseSkillCommand('/skill 数据'),options)[0].skill.id,skill.id);
 assert.equal(parseSkillCommand('/skill').query,'');
});
test('paths, quoted commands and ordinary messages remain ordinary text',()=>{
 for(const text of ['/skills/info','/skill/file.md','示例 /skill pathology-data-api','```\n/skill pathology-data-api\n```']){
  assert.equal(parseSkillCommand(text),null);
  assert.deepEqual(resolveSkillMessage(text,null,options),{text,skillId:null});
 }
});
test('unknown, disabled and empty command cannot silently dispatch',()=>{
 for(const text of ['/skill','/skill missing 任务','/skill locked 任务','/skill pathology-data-api'])assert.throws(()=>resolveSkillMessage(text,null,options));
 assert.throws(()=>resolveSkillMessage('任务','deleted',options));
});
test('explicit command takes precedence over a previous selected chip',()=>{
 const second={...skill,id:'second',title:'第二技能'};
 assert.equal(resolveSkillMessage('/skill second 任务',skill.id,[...options,{skill:second,reason:null}]).skillId,'second');
 assert.equal(resolveSkillMessage('下一轮任务',null,options).skillId,null);
});
test('selection cannot enable formal or synthetic permissions',()=>{
 const plain={...context,formal:false};
 assert.throws(()=>resolveSkillMessage('/skill pathology-data-api 任务',null,skillOptions([skill],plain)),/正式试验/);
 const synthetic={...skill,id:'dataset_intake',capability_refs:['pathoreason.synthetic_mil:dataset_intake']};
 assert.throws(()=>resolveSkillMessage('任务',synthetic.id,skillOptions([synthetic],plain)),/合成验证/);
 assert.equal(resolveSkillMessage('任务',synthetic.id,skillOptions([synthetic],{...plain,synthetic:true})).skillId,synthetic.id);
});
