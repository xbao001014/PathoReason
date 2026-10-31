"""Read-only P5 entry verification. Never fetches patient data or invokes a model/image/trainer."""
import argparse,asyncio,hashlib,json,sqlite3,subprocess,urllib.request,importlib.util,os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pathoreason.settings import ROOT,settings
from pathoreason.persistence import Store
from pathoreason.runtime import OpenCode
from pathoreason.formal import private_image_config
cfg=settings();data=Path(cfg['data_root']);out=data/'acceptance/p5-entry-20261030';out.mkdir(parents=True,exist_ok=True)
checks={};store=Store(data/'state/pathoreason.sqlite3');base='http://127.0.0.1:'+str(cfg['api_port'])
def get(path):
 with urllib.request.urlopen(base+path,timeout=20) as r:return json.load(r)
checks['application_phase']=get('/health')['phase']=='P5-entry'
entry=get('/api/v2/formal-entry');checks['server_formal_entry_available']=entry['available']
checks['seedream_configuration_private']=bool(private_image_config(cfg).get('api_key'))
checks['data_interface_configured']=entry['data_endpoint']=='http://ai.gzfxyl.cn/api/v1/pathology/diseases/slides'
manifest=json.loads((ROOT/'config/p5/skill-migration.json').read_text());checks['all_migrated_resources_present']=all((ROOT/i['destination']/p).is_file() for i in manifest['skills'] for p in i['original_files'])
old=Path('/home/bxn/projects/auto-research');checks['legacy_skill_sources_unchanged']=all(hashlib.sha256((Path(i['source'])/p).read_bytes()).hexdigest()==sha for i in manifest['skills'] for p,sha in i['original_files'].items())
catalog=get('/api/v1/skills');checks['all_skills_visible']=set(i['name'] for i in manifest['skills'])<={s['id'] for s in catalog}
checks['formal_acceptance_not_misrepresented']=entry['formal_acceptance']=='pending_new_window' and not entry['seedream_live_verified'] and not entry['data_live_verified']
with store.connect() as db,sqlite3.connect(out/'before-p5.sqlite3') as backup:
 tables=[r[0] for r in backup.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
 checks['all_prior_rows_unchanged']=all(list(backup.execute('SELECT * FROM "'+t+'" ORDER BY rowid'))==[tuple(r) for r in db.execute('SELECT * FROM "'+t+'" ORDER BY rowid')] for t in tables)
 checks['no_new_model_turns']=db.execute('SELECT count(*) FROM turns').fetchone()[0]==12
 checks['no_formal_study_started']=db.execute('SELECT count(*) FROM formal_studies').fetchone()[0]==0
checks['no_active_turns']=not store.active()
checks['no_new_training']=len(list((data/'research').glob('*/runs/*/loop/jobs/*/started.json')))==34
with urllib.request.urlopen('http://127.0.0.1:8002/ready',timeout=5) as r:ready=json.load(r)
before=json.loads((data/'acceptance/p0-20261030/ready-before.json').read_text())
checks['legacy_service_unchanged']=ready['status']=='ready' and (ready['pid'],ready['instance'])==(before['pid'],before['instance']) and not ready['active_experiments'] and not ready['background_jobs']
async def native():
 runtime=OpenCode(data,cfg['opencode_port']);health=await runtime.health();directory=str(data/'projects/runtime')
 skills=await runtime.call('GET','/skill',directory);agents=await runtime.call('GET','/agent',directory);doc=await runtime.call('GET','/doc')
 checks['native_runtime_healthy']=health['healthy']
 checks['native_skills_discovered']=set(i['name'] for i in manifest['skills'])<={s['name'] for s in skills}
 checks['native_formal_agent_registered']='pathoreason-formal' in {a['name'] for a in agents}
 checks['native_permission_api_available']='/permission/{requestID}/reply' in doc['paths']
 (out/'native-contract-observation.json').write_text(json.dumps({'version':health.get('version'),'skill_names':[s['name'] for s in skills],'agent_names':[a['name'] for a in agents],'permission_endpoints':['/permission','/permission/{requestID}/reply'],'inference_calls':0},indent=2)+'\n')
asyncio.run(native())
report={'checks':checks,'all_passed':all(checks.values()),'model_calls':0,'image_calls':0,'patient_data_fetches':0,'training_jobs':0,'skill_count':len(manifest['skills']),'migrated_original_files':sum(len(i['original_files']) for i in manifest['skills']),'formal_end_to_end_acceptance':'pending_new_window'}
(out/'entry-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['all_passed']
