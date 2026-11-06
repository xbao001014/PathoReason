"""Deployment-local provider profiles. Secrets never enter native config or API views."""
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = {
    'deepseek-direct': {'title':'DeepSeek 官方', 'key_env':'DEEPSEEK_API_KEY',
        'base_url':'https://api.deepseek.com/v1', 'models':['deepseek-v4-pro','deepseek-flash']},
    'dashscope-deepseek': {'title':'阿里云百炼 · DeepSeek', 'key_env':'DASHSCOPE_API_KEY',
        'base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'models':['deepseek-v4-pro','deepseek-v4.1-flash']},
}


def private_directory(config):
    path=Path(config['data_root'])/'runtime/providers'
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('provider_storage_invalid')
    return path


def atomic_private(path, data):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('provider_storage_invalid')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name+'-')
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def state(config):
    if not config.get('provider_profiles_enabled'):return None
    value=json.loads((private_directory(config)/'profiles.json').read_text())
    if value.get('active') not in PROVIDERS or type(value.get('revision')) is not int:
        raise ValueError('provider_configuration_invalid')
    for pid,spec in PROVIDERS.items():
        p=value['profiles'][pid]
        validate_endpoint(pid,p['base_url'])
        if p['model'] not in spec['models']:raise ValueError('model_not_configured')
    return value


def validate_endpoint(pid, endpoint):
    if not isinstance(endpoint,str) or len(endpoint)>300:
        raise ValueError('provider_endpoint_invalid')
    try:u=urlsplit(endpoint);port=u.port
    except ValueError:raise ValueError('provider_endpoint_invalid') from None
    if u.scheme!='https' or u.username or u.password or u.query or u.fragment or port not in (None,443):
        raise ValueError('provider_endpoint_invalid')
    if pid=='deepseek-direct':
        valid=u.hostname=='api.deepseek.com' and u.path.rstrip('/')=='/v1'
    elif pid=='dashscope-deepseek':
        host=u.hostname or ''
        valid=(host in {'dashscope.aliyuncs.com','dashscope-intl.aliyuncs.com','dashscope-us.aliyuncs.com','cn-hongkong.dashscope.aliyuncs.com'}
            or re.fullmatch(r'[a-zA-Z0-9-]+\.(?:cn-beijing|ap-southeast-1|us-east-1|eu-central-1|ap-northeast-1|cn-hongkong)\.maas\.aliyuncs\.com',host))
        valid=bool(valid) and u.path.rstrip('/')=='/compatible-mode/v1'
    else:valid=False
    if not valid:raise ValueError('provider_endpoint_invalid')
    return endpoint.rstrip('/')


def read_key(path, env_name):
    path=Path(path)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:return ''
        for line in path.read_text().splitlines():
            name,sep,value=line.removeprefix('export ').partition('=')
            if sep and name.strip()==env_name:return value.strip().strip('\"\'')
    except OSError:pass
    return ''


def key_for(config, pid):
    return read_key(private_directory(config)/(pid+'.env'),PROVIDERS[pid]['key_env'])


def initialize(config, legacy_key):
    directory=private_directory(config);directory.mkdir(parents=True,exist_ok=True,mode=0o700);directory.chmod(0o700)
    if (directory/'profiles.json').exists():raise ValueError('provider_profiles_already_initialized')
    profiles={pid:{'base_url':s['base_url'],'model':s['models'][0]} for pid,s in PROVIDERS.items()}
    if config.get('provider',{}).get('model') in PROVIDERS['deepseek-direct']['models']:
        profiles['deepseek-direct']['model']=config['provider']['model']
    atomic_private(directory/'deepseek-direct.env',('DEEPSEEK_API_KEY='+legacy_key+'\n').encode())
    atomic_private(directory/'dashscope-deepseek.env',b'DASHSCOPE_API_KEY=\n')
    atomic_private(directory/'profiles.json',(json.dumps({'revision':1,'active':'deepseek-direct','profiles':profiles},indent=2)+'\n').encode())


def effective_settings(config):
    value=state(config)
    if value:
        pid=value['active'];profile=value['profiles'][pid]
        config={**config,'provider':{'id':pid,'model':profile['model'],'endpoint':profile['base_url'],
            'credential_ref':PROVIDERS[pid]['key_env']},'credential_file':str(private_directory(config)/(pid+'.env')),
            'provider_revision':value['revision']}
    return config


def native_config(config=None):
    if config is None:
        from .settings import settings
        config=settings()
    base=Path(config.get('opencode_config_file',ROOT/'config/opencode.json'))
    result=json.loads(base.read_text())
    current=state(config)
    if not current:return result
    pid=current['active'];profile=current['profiles'][pid]
    if pid=='deepseek-direct':
        provider=copy.deepcopy(json.loads((ROOT/'config/opencode.json').read_text())['provider']['deepseek-direct'])
    else:
        models={}
        for model in PROVIDERS[pid]['models']:
            variants={'none':{'enable_thinking':False},'high':{'enable_thinking':True,'reasoningEffort':'high'},
                      'max':{'enable_thinking':True,'reasoningEffort':'max'}}
            if model=='deepseek-v4.1-flash':variants['low']={'enable_thinking':True,'reasoningEffort':'low'}
            item={'name':model,'tool_call':True,'reasoning':True,'interleaved':{'field':'reasoning_content'},
                  'variants':variants,'options':{'enable_thinking':True},
                  'limit':{'context':1000000,'input':991808,'output':8192}}
            if model=='deepseek-v4.1-flash':item.update(attachment=True,modalities={'input':['text','image'],'output':['text']})
            models[model]=item
            for limit in [32768,65536]:
                models[f'pathoreason-output-{limit}-{model}']={**copy.deepcopy(item),'id':model,
                    'limit':{'context':1000000,'input':1000000-limit,'output':limit}}
        provider={'npm':'@ai-sdk/openai-compatible','name':PROVIDERS[pid]['title'],'options':{},'models':models}
    provider['options'].update(baseURL=profile['base_url'],apiKey='{env:PATHOREASON_PROVIDER_API_KEY}')
    result.update(provider={pid:provider},enabled_providers=[pid],model=pid+'/'+profile['model'],small_model=pid+'/'+profile['model'])
    return result
