"""Explicit per-request output profiles; never change project or training budgets."""
import json
from pydantic import BaseModel
from .settings import ROOT

PROFILE_PREFIX = 'pathoreason-output-'

class OutputOptions(BaseModel):
    model: str
    default: int
    choices: list[int]
    capability_max_tokens: int

class TurnOutputView(BaseModel):
    turn_id: str
    model: str
    output_limit_tokens: int | None = None
    reasoning_effort: str | None = None
    reasoning_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    source: str = 'unavailable'


def configured_options():
    configured=json.loads((ROOT/'config/output-limits.json').read_text())
    native=json.loads((ROOT/'config/opencode.json').read_text())['provider']
    result=[]
    for model,entry in configured['models'].items():
        models=native.get(entry['provider'],{}).get('models',{})
        base=models.get(model)
        if not base:continue
        default=base['limit']['output']
        choices=[default]
        for limit in entry['choices']:
            p=models.get(profile_name(model,limit),{})
            if limit!=default and p.get('id')==model and p.get('limit',{}).get('output')==limit:
                choices.append(limit)
        result.append(OutputOptions(model=model,default=default,choices=sorted(set(choices)),capability_max_tokens=entry['capability_max_tokens']))
    return result


def profile_name(model,limit):
    return f'{PROFILE_PREFIX}{limit}-{model}'


def validate_output(model,limit):
    option=next((o for o in configured_options() if o.model==model),None)
    if type(limit) is not int or not option or limit not in option.choices:
        raise ValueError('output_limit_not_supported')
    return model if limit==option.default else profile_name(model,limit)


async def turn_output(service,tid):
    row=service.store.turn(tid);turn=json.loads(row['document'])
    with service.store.connect() as db:
        frozen=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(turn['config_digest'],)).fetchone()[0])
    result=TurnOutputView(turn_id=tid,model=turn['model']['model'],
        output_limit_tokens=frozen.get('output_limit_tokens') or turn['model'].get('output_limit_tokens'),
        reasoning_effort=frozen.get('reasoning_effort'))
    usage=json.loads(row['usage'])
    if 'last_reasoning_tokens' in usage or 'last_output_tokens' in usage:
        return result.model_copy(update={'reasoning_tokens':usage.get('last_reasoning_tokens'),'output_tokens':usage.get('last_output_tokens'),'finish_reason':usage.get('finish_reason'),'source':'stored_runtime_usage'})
    # Read legacy failed native receipts without rewriting their stored usage or reasoning.
    if service.runtime_name=='opencode' and turn.get('error_code')=='runtime_output_limit':
        try:
            with service.store.connect() as db:
                binding=json.loads(db.execute('SELECT document FROM bindings WHERE id=?',(turn['runtime_binding_id'],)).fetchone()[0])
            directory=str(service.data/'projects'/row['project_id'])
            messages=await service.runtime.messages(binding['native_session_id'],directory)
            matches=[m['info'] for m in messages if m.get('info',{}).get('role')=='assistant' and m['info'].get('parentID')==row['native_message_id']]
            if matches:
                info=matches[-1];tokens=info.get('tokens',{})
                result=result.model_copy(update={'reasoning_tokens':tokens.get('reasoning'),'output_tokens':tokens.get('output'),'finish_reason':info.get('finish'),'source':'native_read_only'})
        except Exception:
            pass # Unknown is not zero; recovery remains possible from the frozen request.
    return result
