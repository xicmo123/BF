import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from bitfinex_lending_bot.dashboard_api import app


def test_rollout_set_and_stop():
    client = TestClient(app)
    # initial state
    r = client.get('/rollout/state')
    assert r.status_code == 200
    s = r.json()

    # set to 1%
    r2 = client.post('/rollout/set', json={'percent': 1})
    assert r2.status_code in (200, 403, 400)

    # emergency stop
    r3 = client.post('/rollout/stop', json={'reason': 'test stop'})
    assert r3.status_code == 200
    r4 = client.get('/rollout/state')
    assert r4.status_code == 200
    assert r4.json()['state']['allocation_percent'] == '0.0'
