import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from bitfinex_lending_bot.dashboard_api import app


def test_auto_enable_disable_run():
    client = TestClient(app)
    r = client.post('/rollout/auto/enable', json={'interval':1, 'cycles':1})
    assert r.status_code == 200
    r2 = client.post('/rollout/auto/run')
    assert r2.status_code == 200
    r3 = client.post('/rollout/auto/disable')
    assert r3.status_code == 200
 