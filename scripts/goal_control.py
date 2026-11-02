"""Record the current Agent turn's goal checkpoint through the application."""
import json
from pathlib import Path
import sys
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.goals import GoalCheckpoint
from pathoreason.settings import settings


def main():
    cfg=settings()
    try:
        body=GoalCheckpoint.model_validate(json.load(sys.stdin)).model_dump(mode='json')
        token=Path(cfg['data_root'])/'runtime/control/guidance-token'
        if token.is_symlink() or token.stat().st_mode & 0o077:raise ValueError('bridge_token_unavailable')
        request=urllib.request.Request(f"http://127.0.0.1:{cfg['api_port']}/internal/goal-checkpoint",
            data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token.read_text().strip()})
        with urllib.request.urlopen(request,timeout=30) as response:result=json.load(response)
        print(json.dumps(result,ensure_ascii=False));return 0
    except urllib.error.HTTPError as exc:
        print(json.dumps({'error':json.load(exc).get('detail','goal_checkpoint_failed')},ensure_ascii=False));return 1
    except (OSError,ValueError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
