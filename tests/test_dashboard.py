import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from bitfinex_lending_bot.dashboard_api import app


def test_metrics_and_health_endpoints():
    client = TestClient(app)
    r = client.get('/metrics')
    assert r.status_code == 200
    data = r.json()
    assert 'symbol' in data

    h = client.get('/health')
    assert h.status_code == 200
    health = h.json()
    assert 'time' in health
