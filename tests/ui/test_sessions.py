# tests/ui/test_sessions.py
import json
import pytest
from fastapi.testclient import TestClient
from trading.impl.trade_logger.sqlite_trade_logger import SqliteTradeLogger


@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "trades.db")
    logger = SqliteTradeLogger(db_path=db)
    logger.open_session("sess-1", "paper", ["StratA"])
    logger.log_snapshot("sess-1", {
        "timestamp": __import__("datetime").datetime(2024, 1, 2, 10, 0),
        "equity": 10_200.0,
        "strategy_pnl": {"StratA": 200.0},
        "strategy_equity": {"StratA": 10_200.0},
    })
    logger.close_session("sess-1")
    logger.open_session("sess-live", "paper", ["StratA"])

    from ui.server.app import create_app
    app = create_app(db_path=db)
    return TestClient(app)


def test_list_sessions(client):
    r = client.get("/api/sessions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["session_id"] == "sess-live"  # most recent first


def test_live_session(client):
    r = client.get("/api/sessions/live")
    assert r.status_code == 200
    assert r.json()["session_id"] == "sess-live"


def test_live_session_404_when_none(tmp_path):
    db = str(tmp_path / "empty.db")
    SqliteTradeLogger(db_path=db)  # creates schema, no sessions
    from ui.server.app import create_app
    c = TestClient(create_app(db_path=db))
    assert c.get("/api/sessions/live").status_code == 404


def test_snapshots_endpoint(client):
    r = client.get("/api/sessions/sess-1/snapshots")
    assert r.status_code == 200
    snaps = r.json()
    assert len(snaps) == 1
    assert snaps[0]["total_equity"] == 10_200.0
    assert isinstance(snaps[0]["strategy_pnl"], dict)


def test_fills_endpoint_empty(client):
    r = client.get("/api/sessions/sess-1/fills")
    assert r.status_code == 200
    assert r.json() == []


def test_signals_endpoint_empty(client):
    r = client.get("/api/sessions/sess-1/signals")
    assert r.status_code == 200
    assert r.json() == []


def test_orders_endpoint_empty(client):
    r = client.get("/api/sessions/sess-1/orders")
    assert r.status_code == 200
    assert r.json() == []
