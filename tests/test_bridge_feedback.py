import io,json,urllib.error
import pytest
from pathoreason.bridge_feedback import http_failure,validation_failure
from pathoreason.training_contracts import TrainingToolInput
from pydantic import ValidationError


def error(body):return urllib.error.HTTPError('http://local/bridge',422,'invalid',{},io.BytesIO(json.dumps(body).encode()))


def test_publish_area_error_explains_actual_next_step():
    result=http_failure(error({'detail':'publish_result_area_required'}))
    assert result['error']=='publish_result_area_required' and 'outputs/' in result['next']
    assert result['http_status']==422


def test_error_details_do_not_echo_body_or_tokens():
    result=http_failure(error({'detail':[{'loc':['body','turn_id'],'type':'missing','msg':'bad PRIVATE_GRANT','input':{'grant':'PRIVATE_GRANT'}}]}))
    assert result['issues']==[{'loc':['body','turn_id'],'type':'missing'}]
    assert 'PRIVATE' not in json.dumps(result)
    assert http_failure(error({'detail':'request contained PRIVATE_GRANT value'}))['error']=='bridge_request_failed'
    with pytest.raises(ValidationError) as invalid:TrainingToolInput(turn_id='turn_fixture',grant={'secret':'PRIVATE_GRANT'},operation='list')
    assert 'PRIVATE_GRANT' not in json.dumps(validation_failure(invalid.value))
