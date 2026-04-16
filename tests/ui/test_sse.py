# tests/ui/test_sse.py
import pytest
from fastapi.testclient import TestClient
from trading.impl.trade_logger.sqlite_trade_logger import SqliteTradeLogger


@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "trades.db")
    logger = SqliteTradeLogger(db_path=db)
    logger.open_session("sess-1", "paper", ["StratA"])
    from ui.server.app import create_app
    return TestClient(create_app(db_path=db))


def test_sse_returns_event_stream_content_type(client):
    # Use max_polls=1 so the generator terminates after one DB poll —
    # TestClient is synchronous and cannot detect client disconnect, so an
    # infinite generator would block forever.  max_polls=1 is the test seam.
    with client.stream("GET", "/api/sse?session_id=sess-1&max_polls=1") as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        # Read one chunk and break — enough to confirm the stream opens
        for chunk in r.iter_text():
            break
