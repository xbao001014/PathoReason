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
    result=[]
    for pid,provider in config.get('provider',{}).items():
        if provider.get('npm')!='@ai-sdk/openai-compatible':continue
        for name,item in provider.get('models',{}).items():
            if name.startswith('pathoreason-output-'):continue
            variants=item.get('variants',{})
            if pid=='deepseek-direct':
                efforts=list(EFFORTS) if all(variants.get(v)=={'reasoningEffort':v} for v in EFFORTS) else []
            elif pid=='dashscope-deepseek':
                efforts=[v for v in EFFORTS if variants.get(v)==({'enable_thinking':False} if v=='none' else {'enable_thinking':True,'reasoningEffort':v})]
            else:efforts=[]
            if 'high' in efforts:result.append(ReasoningOptions(model=name,efforts=efforts).model_dump())
    return result
