"""Small, actionable HTTP/validation receipts without request values or grants."""
import json,re


def http_failure(exc,fallback='bridge_request_failed'):
    result={'error':fallback,'http_status':exc.code}
    try:detail=json.loads(exc.read(65536)).get('detail')
    except (ValueError,AttributeError):return result
    if isinstance(detail,str) and re.fullmatch(r'[a-zA-Z0-9_.:-]{1,300}',detail):result['error']=detail
    elif isinstance(detail,list):
        result['error']='invalid_request_fields'
        result['issues']=[{'loc':e.get('loc',[]),'type':e.get('type','invalid')} for e in detail[:10] if isinstance(e,dict)]
    if result['error']=='publish_result_area_required':
        result['next']='Publish a non-sensitive result or summary under outputs/, figures/ or manuscript/. The registered training plan remains available in Training; do not move or overwrite its source to hide this failure.'
    hints={
        'guidance_goal_scope_conflict':'An unfinished goal cannot offer direction-only clarify choices. For a decision that advances authorized work, including summaries or saved reports without training, correct the option to continue (inherits scope), or inspect for read-only work. Never widen user permissions. Record a user-requested pause/cancel with a checkpoint.',
        'goal_outside_turn_scope':'The turn is bound to the goal, but its frozen dialogue scope forbids file/task/run evidence. This is not missing tool approval. Correct the checkpoint in this turn: blocked, blocker kind=input explaining scope, and no out-of-scope evidence. Do not claim completion or repeat the same failing checkpoint. If uncorrected, the controller stops with the scope error.'
    }
    if result['error'] in hints:result['next']=hints[result['error']]
    return result


def validation_failure(exc):
    return {'error':'invalid_tool_arguments','issues':exc.errors(include_input=False,include_context=False,include_url=False)[:10]}
