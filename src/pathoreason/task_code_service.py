"""Current-turn capability wrapper for task source operations; no new budget."""
import hmac
import hashlib
import json
from pathlib import Path
from .persistence import Conflict
from .contracts import canonical_digest
from .settings import ROOT
from .task_workspaces import TaskWorkspaces


class TaskCodeService:
    def __init__(self,service):
        self.s=service
        self.workspaces=TaskWorkspaces(service.store,service.data,source_roots={
            'platform':ROOT,
            'mil_vendor':Path(service.config.get('legacy_root','/home/bxn/projects/auto-research'))/'engines/auto_mil/third_party/MIL_BASELINE'})

    def call(self,body):
        row=self.s.store.turn(body.turn_id)
        self.s.store.conversation(row['conversation_id'],writable=True)
        if row['status']!='running':raise Conflict('task_code_turn_inactive')
        if not self.s.formal.record(row['project_id']):raise Conflict('formal_study_required')
        if not hmac.compare_digest(body.grant,self.s.guidance.grant(body.turn_id)):
            raise Conflict('task_code_grant_invalid')
        turn=json.loads(row['document'])
        with self.s.store.connect() as db:
            runtime=db.execute('SELECT document FROM runtime_configs WHERE digest=?',(turn['config_digest'],)).fetchone()
            context=db.execute('SELECT document FROM turn_guidance_context WHERE turn_id=?',(body.turn_id,)).fetchone()
        if not runtime:raise Conflict('task_code_runtime_binding_missing')
        frozen=json.loads(runtime[0])
        if canonical_digest(frozen)!=turn['config_digest']:raise Conflict('task_code_runtime_binding_changed')
        readonly=body.operation in ('list','inspect','inspect_update')
        if frozen.get('execution_scope')=='dialogue' or (frozen.get('execution_scope')=='inspection' and not readonly):
            raise Conflict('task_code_outside_turn_scope')
        context=json.loads(context[0]) if context else None
        option=next((x for x in context['proposal']['options'] if x['id']==context.get('selected_option_id')),None) if context else None
        scope=option['scope'] if option else None
        if scope=='clarify' or (scope=='inspect' and body.operation not in ('list','inspect','inspect_update')):
            raise Conflict('task_code_outside_turn_scope')
        actor={'kind':'agent','turn_id':body.turn_id,'conversation_id':row['conversation_id'],
               'runtime_binding_id':turn['runtime_binding_id'],'runtime_config_digest':turn['config_digest'],
               'model':turn.get('model'),'skill_sha256':hashlib.sha256((ROOT/'skills/task-code-workspaces/SKILL.md').read_bytes()).hexdigest()}
        return self.workspaces.act(row['project_id'],body.model_dump(mode='json'),actor)

    def prompt(self):
        return ('\nCurrent published task template catalog: '+json.dumps(self.workspaces.catalog(),ensure_ascii=False)+'\nIndependent task code repositories are available through '+str(ROOT/'scripts/task_code.py')+
                '. For task creation, repair, source freezing or template updates, read '+str(ROOT/'skills/task-code-workspaces/SKILL.md')+
                '. Use the current dialogue capability turn_id/grant; never print the grant. '
                'Source freezing is not executable environment readiness or training authorization. '
                'Preserve old research scripts, failures, results, test exposure and budgets.\n')
