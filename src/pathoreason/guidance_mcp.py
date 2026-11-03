"""Structured dialogue tool; no filesystem or compute execution surface."""
import sys,json,urllib.request,urllib.error
from pathlib import Path
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pathoreason.guidance import OfferInput
from pathoreason.goals import GoalCheckpoint
from pathoreason.training_contracts import TrainingToolInput
from pathoreason.settings import settings
from pathoreason.bridge_feedback import http_failure

def validation_result(exc):
    # Do not echo input values or Pydantic context: both can contain the grant.
    issues = exc.errors(include_input=False, include_context=False, include_url=False)[:10]
    return {'content': [{'type': 'text', 'text': json.dumps({
        'error': 'invalid_tool_arguments',
        'issues': issues,
        'next': 'Correct the listed fields and retry. Copy turn_id, grant and the current goal revision from trusted turn context; never invent or print the grant.'
    }, ensure_ascii=False)}], 'isError': True}


def main():
    cfg=settings()
    for line in sys.stdin:
        try:
            req=json.loads(line)
            if 'id' not in req:continue
            method=req.get('method')
            if method=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'pathoreason_dialogue','version':'0.4.0'}}
            elif method=='ping':result={}
            elif method=='tools/list':result={'tools':[{'name':'offer','description':'Save a brief clarification or useful next-step choice in the UI. Use early when context already reveals a missing decision; do not audit files first. Use after actual delivery for a next step. One offer per turn; finish your reply after success. Never executes research or grants training. Copy turn_id/grant from current trusted dialogue capability. Within an active goal use clarification choices with continue scope for consequential decisions; the selection immediately advances the original goal without widening its authority. Do not ask for routine draft/check/freeze confirmation. clarify is direction-only and is rejected in unfinished active goals. Saving, publishing or consolidating a report is continue-scoped work, even when no new training is requested. Next-step offers require the current goal completion checkpoint first. options carry visible labels, optional descriptions and continue/clarify/plan/inspect scope. artifact_ids bind relevant registered artifacts.','inputSchema':OfferInput.model_json_schema()},{'name':'checkpoint','description':'Save one goal checkpoint before ending an active goal turn. Use current turn_id/grant and goal revision from trusted context. Report continue with concrete next_action, completed with evidence, needs_input, blocked, paused or waiting for a registered run. For blockers include kind platform/permission/input/resource and required_action; an unavailable training executor uses capability=training_execution. goal_outside_turn_scope means frozen scope restriction, not a detached goal or missing permission; correct the checkpoint with a scope blocker and no forbidden file/task/run evidence. Completion is not scientific approval. Does not launch research.','inputSchema':GoalCheckpoint.model_json_schema()},{'name':'training','description':'Prepare and inspect generic frozen training experiments; manage authorized runs with independent training budgets. Read training-execution Skill first. environment freezes a configured Python runtime, prepare accepts inline plan or a project-local plan_path; never put a grant in the plan file. Receipts are compact by default; inspect include_plan=true for full detail. prepare creates a concrete experiment for the user Training panel. User approval is required once for plan scope and compute limits; this tool cannot approve or increase budgets. Registered runs survive Agent turns. Preserve failures, prior exposure and consumed budget.','inputSchema':TrainingToolInput.model_json_schema()}]}
            elif method=='tools/call':
                name=req['params']['name']
                if name not in ('offer','checkpoint','training'):raise ValueError('unknown_tool')
                args=({'offer':OfferInput,'checkpoint':GoalCheckpoint,'training':TrainingToolInput}[name]).model_validate(req['params']['arguments']).model_dump(mode='json')
                endpoint={'offer':'guidance','checkpoint':'goal-checkpoint','training':'training'}[name]
                token=Path(cfg['data_root'])/'runtime/control/guidance-token'
                if token.is_symlink() or token.stat().st_mode&0o077:raise ValueError('bridge_token_unavailable')
                request=urllib.request.Request(f"http://127.0.0.1:{cfg['api_port']}/internal/{endpoint}",data=json.dumps(args).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token.read_text().strip()})
                try:
                    with urllib.request.urlopen(request,timeout=3600 if name=='training' else 15) as response:value=json.load(response)
                    result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
                except urllib.error.HTTPError as exc:
                    result={'content':[{'type':'text','text':json.dumps(http_failure(exc,'guidance_failed'))}],'isError':True}
            else:raise ValueError('unsupported_method')
            print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':result}),flush=True)
        except ValidationError as exc:
            print(json.dumps({'jsonrpc':'2.0','id':req.get('id'),'result':validation_result(exc)},ensure_ascii=False),flush=True)
        except Exception as exc:
            print(json.dumps({'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32603,'message':type(exc).__name__}}),flush=True)
if __name__=='__main__':main()
