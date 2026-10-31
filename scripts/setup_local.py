"""Bootstrap isolated local Codex storage; reuse only this machine's existing login."""
import json,os,shutil,secrets
from pathlib import Path
root=Path(__file__).resolve().parents[1];data=Path.home()/'.local/share/PathoReason';data.mkdir(parents=True,exist_ok=True);data.chmod(0o700)
for name in ('projects','artifacts','state','acceptance','scratch','runtime/control','runtime/codex'):(data/name).mkdir(parents=True,exist_ok=True)
native=data/'runtime/codex';native.chmod(0o700)
auth=Path.home()/'.codex/auth.json'
if not auth.exists():raise SystemExit('Local Codex login required')
link=native/'auth.json'
if not link.exists():link.symlink_to(auth)
if link.resolve()!=auth.resolve():raise SystemExit('Unexpected auth binding')
skill=native/'skills/results-explanation';skill.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'skills/results-explanation/SKILL.md',skill/'SKILL.md')
cfg=root/'config/pathoreason.local.json'
if not cfg.exists():
 value={'schema_version':'pathoreason.config/1','data_root':str(data),'execution_environment':'local','primary_runtime':'codex','seed_legacy':False,'business_enabled':False,'api_port':8530,'opencode_port':8532,'codex_binary':shutil.which('codex'),'legacy_root':'/nonexistent/pathoreason-local-legacy','p1_test_limits':{'max_turns':12,'max_wall_seconds':1200,'concurrency':1,'automatic_retries':0},'context_limits':{'max_operations':4,'timeout_seconds':70},'codex':{'model':'gpt-6.1-sol','models':['gpt-6.1-sol','gpt-6-luna'],'effort':'low','local_auth':'local_codex_login'}}
 cfg.write_text(json.dumps(value,indent=2)+'\n');cfg.chmod(0o600)
value=json.loads(cfg.read_text());cache=Path.home()/'.codex/models_cache.json'
if cache.exists():
 models=json.loads(cache.read_text()).get('models',[])
 metadata={m['slug']:{'context_window':int(m['context_window']*m.get('effective_context_window_percent',100)/100) if m.get('context_window') else None,'tool_support':'supported' if m.get('shell_type') else 'unknown','source':'local Codex cache, effective_context_window_percent applied; not entitlement verification'} for m in models if m['slug'] in value['codex']['models']}
 (native/'model-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
# Own configuration never inherits unrelated MCP servers, agents or project instructions.
config='''model = "gpt-6.1-sol"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
model_reasoning_effort = "low"
[features]
shell_tool = false
apply_patch_freeform = false
multi_agent = false
apps = false
code_mode = false
[mcp_servers.pathoreason_context]
'''
config+='command = '+json.dumps(str(root/'.venv/bin/python'))+'\nargs = ['+json.dumps(str(root/'src/pathoreason/context_mcp.py'))+']\n'
if not (native/'config.toml').exists():(native/'config.toml').write_text(config)
print(json.dumps({'data_root':str(data),'api_port':value['api_port'],'auth':'local_existing_login_reference','models':value['codex']['models']}))
