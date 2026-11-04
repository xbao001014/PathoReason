import pytest
from pydantic import ValidationError
from pathoreason.goals import GoalCheckpoint, GoalEvidence
from pathoreason.manuscript import ReviewRequest


def test_checkpoint_can_reference_every_review_material():
    ids = [f'art_fixture_{i}' for i in range(24)]
    review = ReviewRequest(gate='draft', expected_revision=1, summary='Draft',
        materials=[dict(role=f'role_{i}', label=f'Material {i}', artifact_id=aid)
                   for i, aid in enumerate(ids)])
    evidence = GoalEvidence(artifact_ids=ids)
    assert {m.artifact_id for m in review.materials} == set(evidence.artifact_ids)
    assert GoalCheckpoint.model_json_schema()['$defs']['GoalEvidence']['properties']['artifact_ids']['maxItems'] == 24
    with pytest.raises(ValidationError):
        GoalEvidence(artifact_ids=ids + ['art_over_limit'])
