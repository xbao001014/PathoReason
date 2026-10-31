"""Explicit provider capabilities; never infer effort support from a model name alone."""
from typing import Literal
from pydantic import BaseModel

ReasoningEffort=Literal['none','low','high','max']
EFFORTS=('none','low','high','max')
class ReasoningOptions(BaseModel):
    model:str
    efforts:list[ReasoningEffort]
    default:ReasoningEffort='high'

def configured_options(config):
    provider=config.get('provider',{}).get('deepseek-direct',{})
    if provider.get('npm')!='@ai-sdk/openai-compatible':return []
    return [ReasoningOptions(model=name,efforts=list(EFFORTS)).model_dump()
            for name,item in provider.get('models',{}).items()
            if name in {'deepseek-v4-pro','deepseek-flash'}
            and all(item.get('variants',{}).get(v)=={'reasoningEffort':v} for v in EFFORTS)]
