import socket
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pathoreason.server import listeners


@pytest.mark.parametrize('hosts', [['0.0.0.0'], ['192.168.1.204'], ['8.8.8.8'], [], ['127.0.0.1', '127.0.0.1']])
def test_reject_unintended_networks(hosts):
    with pytest.raises(ValueError):
        listeners({'api_hosts': hosts, 'api_port': 0})


def test_default_binds_only_loopback():
    sockets = listeners({'api_port': 0})
    try:
        assert [s.getsockname()[0] for s in sockets] == ['127.0.0.1']
    finally:
        for s in sockets: s.close()


def test_partial_bind_failure_releases_first_socket():
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.2', 0))
        port = occupied.getsockname()[1]
        with pytest.raises(OSError):
            listeners({'api_hosts': ['127.0.0.1', '127.0.0.2'], 'api_port': port})
        with socket.socket() as retry:
            retry.bind(('127.0.0.1', port))


def test_host_allowlist_and_cross_origin_protection(monkeypatch):
    from pathoreason.api import app
    monkeypatch.setattr(app.state, 'service', SimpleNamespace(config={'allowed_hosts': ['100.84.214.106']}), raising=False)
    client = TestClient(app, base_url='http://100.84.214.106:8520')
    assert client.get('/health').status_code == 200
    assert client.get('/health', headers={'host':'evil.invalid'}).status_code == 403
    assert client.post('/missing', headers={'origin':'http://evil.invalid'}).status_code == 403
    assert client.post('/missing', headers={'origin':'http://100.84.214.106:8520'}).status_code == 404
    monkeypatch.setattr(app.state, 'service', SimpleNamespace(config={}))
    assert client.get('/health').status_code == 403
