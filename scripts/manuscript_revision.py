"""Route an authorized manuscript rewrite without approving the revised version."""
import json
from pathlib import Path
import sys
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.manuscript import RevisionRoute
from pathoreason.settings import settings

def main():
    cfg=settings()
    try:
        body=RevisionRoute.model_validate(json.load(sys.stdin)).model_dump(mode='json')
        token=Path(cfg['data_root'])/'runtime/control/guidance-token'
        if token.is_symlink() or token.stat().st_mode & 0o077:raise ValueError('bridge_token_unavailable')
        request=urllib.request.Request(f"http://127.0.0.1:{cfg['api_port']}/internal/manuscript-revision-route",
            data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token.read_text().strip()})
        with urllib.request.urlopen(request,timeout=30) as response:result=json.load(response)
        summary={k:result[k] for k in ('revision','gate','status','required_roles','next_work','author_content_approved','delivery_approved')}
        routed=next((h for h in reversed(result['history']) if h['event']=='revision_routed'),None)
        summary['preserved_manuscripts']=[m for p in (routed or {}).get('invalidated',[]) for m in p['materials'] if m['role']=='manuscript']
        summary['next']='Continue the authorized revision in this turn using the returned workflow revision. Preserve original files; submit the new version for scientific review, never approve it.'
        print(json.dumps(summary,ensure_ascii=False));return 0
    except urllib.error.HTTPError as exc:
        print(json.dumps({'error':json.load(exc).get('detail','manuscript_revision_route_failed')},ensure_ascii=False));return 1
    except (OSError,ValueError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
