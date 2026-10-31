"""Read-only P1 deployment/source verification; writes only P1 evidence, never P0."""
import hashlib,json,subprocess,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.settings import ROOT,settings
from pathoreason.service import Service
cfg=settings();data=Path(cfg['data_root']);out=Path(sys.argv[1]) if len(sys.argv)>1 else data/'acceptance/p1-20261030'
baseline=json.loads((data/'acceptance/p1-20261030/baseline.json').read_text());p0=data/'acceptance/p0-20261030'
old=Path(cfg['legacy_root']);checks={}
checks['legacy_worktree_status_unchanged']=subprocess.check_output(['git','-C',str(old),'status','--porcelain'],text=True)==baseline['old_git_status']
base0=json.loads((p0/'baseline.json').read_text());inventory=json.loads((p0/'source-inventory.json').read_text())
checks['legacy_baseline_sources_unchanged']=all(hashlib.sha256((old/p).read_bytes()).hexdigest()==h for p,h in base0['files'].items())
checks['legacy_inventory_sources_unchanged']=all(hashlib.sha256((old/i['path']).read_bytes()).hexdigest()==i['sha256'] for i in inventory)
ready=json.load(urllib.request.urlopen('http://127.0.0.1:8002/ready',timeout=5))
checks['legacy_same_ready_instance']=ready['status']=='ready' and ready['instance']==baseline['old_ready']['instance'] and ready['pid']==baseline['old_ready']['pid']
checks['legacy_no_active_experiments_or_jobs']=not ready['active_experiments'] and not ready['background_jobs']
svc=Service();artifacts=[a for p in svc.store.projects() for a in svc.store.artifacts(p['id']) if a['storage_root']=='legacy_evidence']
checks['five_legacy_artifacts_verified']=len(artifacts)==5 and all(len(svc.artifact_bytes(a))==a['size_bytes'] for a in artifacts)
observed=json.loads((p0/'legacy-experiment-observation.json').read_text())
from pathoreason.legacy import observe_experiment
checks['legacy_frozen_experiment_unchanged']=observe_experiment(Path('/data/bxn/auto-research/experiments'),observed['ref']['resource_id'])==observed
refs=json.loads((ROOT/'docs/references/provenance.json').read_text())['references']
checks['reference_snapshots_unchanged']=all(hashlib.sha256((ROOT/r['snapshot_path']).read_bytes()).hexdigest()==r['sha256'] for r in refs)
base='http://127.0.0.1:'+str(cfg['api_port'])
checks['application_healthy']=json.load(urllib.request.urlopen(base+'/health',timeout=5))['status']=='ok'
status=json.load(urllib.request.urlopen(base+'/api/v1/settings/status',timeout=10))
checks['native_runtime_connected']=status['connected'] and status['version']=='1.18.33'
checks['codex_server_inference_disabled']=status['codex_server_inference_enabled'] is False
with svc.store.connect() as db:turn_count=db.execute('SELECT COUNT(*) FROM turns').fetchone()[0]
report={'checks':checks,'all_passed':all(checks.values()),'runtime_status':status,'application_turn_count':turn_count,'real_inference_acceptance':'see_live_verification' if status['inference_verified'] else 'pending_user_credential','legacy_mutations_requested':0,'training_jobs_started':0}
(out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
if not report['all_passed']:raise SystemExit(1)
