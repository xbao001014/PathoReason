"""Agent-facing JSON tool. Authority is checked by the running application."""
import json
from pathlib import Path
import sys
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.settings import settings
from pathoreason.training_contracts import TrainingToolInput
from pydantic import ValidationError
from pathoreason.bridge_feedback import http_failure,validation_failure


def main():
    cfg=settings()
    try:
        args=TrainingToolInput.model_validate(json.load(sys.stdin)).model_dump(mode='json')
        token=Path(cfg['data_root'])/'runtime/control/guidance-token'
        if token.is_symlink() or token.stat().st_mode & 0o077:raise ValueError('bridge_token_unavailable')
        request=urllib.request.Request(f"http://127.0.0.1:{cfg['api_port']}/internal/training",
            data=json.dumps(args).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token.read_text().strip()})
        with urllib.request.urlopen(request,timeout=3600) as response:result=json.load(response)
        print(json.dumps(result,ensure_ascii=False))
    except urllib.error.HTTPError as exc:
        print(json.dumps(http_failure(exc,'training_failed'),ensure_ascii=False));return 1
    except ValidationError as exc:
        print(json.dumps(validation_failure(exc),ensure_ascii=False));return 1
    except (ValueError,OSError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False));return 1
    return 0

if __name__=='__main__':sys.exit(main())
