"""Additive read-only training progress contract snapshot; preserve older releases."""
import json
from pathlib import Path
from pathoreason.api import app
from pathoreason.training_progress import TrainingProgressView,TrainingTelemetryView
root=Path(__file__).resolve().parents[1]/'contracts'
(root/'p5-training-progress').mkdir(exist_ok=True)
for model in (TrainingProgressView,TrainingTelemetryView):
    (root/'p5-training-progress'/f'{model.__name__}.schema.json').write_text(json.dumps(model.model_json_schema(),indent=2)+'\n')
(root/'api-p5-training-progress.openapi.json').write_text(json.dumps(app.openapi(),indent=2)+'\n')
