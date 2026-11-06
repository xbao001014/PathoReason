"""Initialize deployment-local profiles without changing the active provider.

Run once in each deployment. The current official key is copied, never printed.
An explicitly supplied DashScope env file can contain DASHSCOPE_API_KEY (or
OPENAI_API_KEY), OPENAI_API_BASE (or OPENAI_BASE_URL), and OPENAI_MODEL.
"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.settings import CONFIG,settings,credential
from pathoreason.provider_config import initialize,atomic_private,private_directory,read_key,validate_endpoint,PROVIDERS

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['init'])
    parser.add_argument('--dashscope-env-file',type=Path)
    args=parser.parse_args();cfg=settings()
    if cfg.get('primary_runtime','opencode')!='opencode':raise SystemExit('Provider profiles require the OpenCode runtime.')
    if cfg.get('provider_profiles_enabled'):raise SystemExit('Profiles already initialized; use connection settings.')
    imported={}
    if args.dashscope_env_file:
        p=args.dashscope_env_file
        if p.is_symlink() or p.stat().st_mode & 0o077:raise SystemExit('Private env file must have mode 600.')
        for line in p.read_text().splitlines():
            k,sep,v=line.removeprefix('export ').partition('=')
            if sep:imported[k.strip()]=v.strip().strip('\"\'')
        endpoint=validate_endpoint('dashscope-deepseek',imported.get('OPENAI_API_BASE',imported.get('OPENAI_BASE_URL',PROVIDERS['dashscope-deepseek']['base_url'])))
        model=imported.get('OPENAI_MODEL','deepseek-v4-pro')
        if model not in PROVIDERS['dashscope-deepseek']['models']:raise SystemExit('Unsupported model; use a documented DeepSeek model ID.')
    initialize(cfg,credential())
    if imported:
        directory=private_directory(cfg);value=json.loads((directory/'profiles.json').read_text())
        value['profiles']['dashscope-deepseek']={'base_url':endpoint,'model':model}
        key=read_key(args.dashscope_env_file,'DASHSCOPE_API_KEY') or read_key(args.dashscope_env_file,'OPENAI_API_KEY')
        atomic_private(directory/'dashscope-deepseek.env',('DASHSCOPE_API_KEY='+key+'\n').encode())
        atomic_private(directory/'profiles.json',(json.dumps(value,indent=2)+'\n').encode())
    raw=json.loads(CONFIG.read_text());raw['provider_profiles_enabled']=True
    atomic_private(CONFIG,(json.dumps(raw,indent=2)+'\n').encode())
    print('Independent provider profiles initialized; active provider remains DeepSeek official. Reload idle services to apply.')

if __name__=='__main__':main()
