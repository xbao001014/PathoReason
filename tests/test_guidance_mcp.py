"""MCP argument errors must support correction without exposing grants."""
import io
import json

import pytest
import pathoreason.guidance_mcp as bridge


def checkpoint(**changes):
    return {'grant': 'PRIVATE_GRANT_VALUE', 'expected_revision': 2,
            'outcome': 'completed', 'summary': 'Read-only verification',
            'answer_only': True, **changes}


def run_bridge(monkeypatch, tmp_path, requests, responder=None):
    token = tmp_path / 'runtime/control/guidance-token'
    token.parent.mkdir(parents=True)
    token.write_text('PRIVATE_BRIDGE_TOKEN'); token.chmod(0o600)
    monkeypatch.setattr(bridge, 'settings', lambda: {'data_root': str(tmp_path), 'api_port': 1})
    calls = []
    def urlopen(req, **kwargs):
        calls.append(req)
        assert responder is not None, 'Invalid arguments must not reach the business API'
        return io.BytesIO(json.dumps(responder).encode())
    monkeypatch.setattr(bridge.urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(bridge.sys, 'stdin', io.StringIO('\n'.join(json.dumps(r) for r in requests)))
    output = io.StringIO(); monkeypatch.setattr(bridge.sys, 'stdout', output)
    bridge.main()
    text = output.getvalue()
    assert 'PRIVATE_GRANT_VALUE' not in text and 'PRIVATE_BRIDGE_TOKEN' not in text
    return [json.loads(line) for line in text.splitlines()], calls


def request(args, ident=1, name='checkpoint'):
    return {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
            'params': {'name': name, 'arguments': args}}


def test_missing_turn_id_reports_field_and_valid_retry_reaches_api_once(monkeypatch, tmp_path):
    result, calls = run_bridge(monkeypatch, tmp_path,
        [request(checkpoint()), request(checkpoint(turn_id='turn_example'), 2)],
        responder={'status': 'recorded', 'outcome': 'completed'})
    first = result[0]['result']
    assert first['isError'] is True and 'error' not in result[0]
    error = json.loads(first['content'][0]['text'])
    assert error['error'] == 'invalid_tool_arguments'
    assert error['issues'] == [{'type': 'missing', 'loc': ['turn_id'], 'msg': 'Field required'}]
    assert result[1]['result']['isError'] is False and len(calls) == 1
    assert json.loads(calls[0].data)['turn_id'] == 'turn_example'


@pytest.mark.parametrize('args,kind,location', [
    (checkpoint(turn_id='turn_example', outcome='PRIVATE_GRANT_VALUE'), 'literal_error', ['outcome']),
    (checkpoint(turn_id='turn_example', outcome='continue', answer_only=False), 'value_error', []),
])
def test_validation_errors_never_echo_input_or_context(monkeypatch, tmp_path, args, kind, location):
    results, calls = run_bridge(monkeypatch, tmp_path, [request(args)])
    body = json.loads(results[0]['result']['content'][0]['text'])
    assert body['issues'][0]['type'] == kind and body['issues'][0]['loc'] == location
    assert all(not {'input', 'ctx', 'url'} & set(e) for e in body['issues'])
    assert not calls


def test_offer_uses_same_field_feedback_without_side_effects(monkeypatch, tmp_path):
    results, calls = run_bridge(monkeypatch, tmp_path, [request({'grant': 'PRIVATE_GRANT_VALUE'}, name='offer')])
    assert results[0]['result']['isError'] is True
    body = json.loads(results[0]['result']['content'][0]['text'])
    assert ['turn_id'] in [e['loc'] for e in body['issues']]
    assert not calls
