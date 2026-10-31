"""Read-only acceptance assertions; no model invocation, dispatch or schema reset."""
import hashlib,json,re,sqlite3,urllib.request
from pathlib import Path
from pathoreason.service import Service
ROOT=Path('/home/bxn/projects/PathoReason');DATA=Path('/data/bxn/PathoReason');OUT=DATA/'acceptance/p2-20261030'
s=Service();ids=json.loads((OUT/'live-identity.json').read_text());pid=ids['project_id'];cid=ids['conversation_id']
b=s.business.inspect(pid).model_dump(mode='json');root=DATA/'research'/pid;state=json.loads((root/'task.json').read_text());checks={}
checks['conversation_tools_mutated_real_business']=all(json.loads((OUT/f'live-v2-step-{i}.json').read_text())['turn']['status']=='completed' for i in range(1,5))
checks['one_business_dispatch']=len([a for a in b['actions'] if a['operation']=='execute'])==1 and len(list((root/'runs').iterdir()))==1
checks['workflow_completed_full_matrix']=b['status']=='completed' and b['completed_units']==8 and b['failed_units']==0
checks['no_scientific_promotion']=not b['independent_confirmation_verified'] and not b['submission_ready'] and b['scientific_status']=='not_assessed'
revs=state['revisions'];plans=[json.loads((root/'plans'/f"{r['after']}.json").read_text()) for r in revs]
checks['feedback_is_versioned']=len(revs)==2 and revs[1]['before']==revs[0]['after'] and revs[0]['learning_rate']==.0004 and revs[1]['learning_rate']==.0006 and bool(revs[1]['feedback'])
checks['frozen_protocol_unchanged']=plans[0]['contract']['protocol']==plans[1]['contract']['protocol'] and plans[0]['contract']['budget']==plans[1]['contract']['budget']
checks['baseline_unchanged']=plans[0]['candidates'][0]==plans[1]['candidates'][0]
checks['eight_physical_submissions']=len(list((root/'runs'/b['run_id']/'loop/jobs').glob('*/started.json')))==8
checks['no_gpu_no_planner_calls']=state['result']['budget']['gpu_seconds']==0 and state['result']['budget']['model_calls']==0
artifacts=s.store.artifacts(pid);checks['four_verified_project_run_artifacts']=len(artifacts)==4
for a in artifacts:
 checks['four_verified_project_run_artifacts'] &= a['project_id']==pid and a['run_ref']['resource_id']==b['run_id'] and a['evidence_role']=='synthetic' and hashlib.sha256(s.artifact_bytes(a)).hexdigest()==a['sha256']
 req=urllib.request.Request(f"http://127.0.0.1:8520/api/v1/research-projects/{pid}/artifacts/{a['id']}/content?download=true")
 with urllib.request.urlopen(req) as r:
  checks['four_verified_project_run_artifacts'] &= hashlib.sha256(r.read()).hexdigest()==a['sha256'] and 'attachment' in r.headers['Content-Disposition']
last=json.loads((OUT/'live-v2-step-4.json').read_text());links=re.findall(r'artifact:([A-Za-z0-9_.:-]+)',last['text']);checks['all_model_citations_resolve']=len(links)>=3 and set(links)<=set(b['artifact_ids'])
checks['domain_events_have_turn_and_action']=all(e['scope']=='domain' and e['turn_id'] and e['action_id'] for e in b['events'])
checks['runtime_events_separate']=all(e['scope']=='runtime' for e in s.store.events(cid,0))
checks['public_text_hides_grants']=all(s.business.grant(t['id']) not in t['text'] for t in s.store.turns(cid))
recovery=json.loads((OUT/'recovery-acceptance-fixed.json').read_text());checks['fault_recovery_and_idempotency']=all(recovery['checks'].values())
with s.store.connect() as db:turns=db.execute('SELECT count(*) FROM turns').fetchone()[0]
checks['global_model_budget_preserved']=turns<=12 and s.config['p1_test_limits']['max_turns']==12
report={'checks':checks,'all_passed':all(checks.values()),'business':b,'model_turns_total':turns,'p2_model_turns':len(s.store.turns(cid)),
 'limitations':['仅独立 CPU 合成 MIL 范围；旧真实项目只读','累计 worker 墙钟时间，不是进程 CPU 时间','P3 本机 Codex 与 P4 全面 Schema 调整未开始']}
(OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'checks':checks,'all_passed':report['all_passed'],'model_turns_total':turns},ensure_ascii=False,indent=2));assert report['all_passed']
