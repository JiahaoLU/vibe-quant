# tests/ui/test_db.py
import asyncio
import json
import pytest
from trading.impl.trade_logger.sqlite_trade_logger import SqliteTradeLogger


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "trades.db")
    logger = SqliteTradeLogger(db_path=path)
    logger.open_session("sess-1", "paper", ["StratA", "StratB"])
    logger.log_snapshot("sess-1", {
        "timestamp": __import__("datetime").datetime(2024, 1, 2, 10, 0, 0),
        "equity": 10_500.0,
        "strategy_pnl": {"StratA": 300.0, "StratB": 200.0},
        "strategy_equity": {"StratA": 5_300.0, "StratB": 5_200.0},
    })
    logger.close_session("sess-1")
    logger.open_session("sess-2", "paper", ["StratA"])
    return path


def run(coro):
    return asyncio.run(coro)


def test_get_sessions_returns_all(db_path):
    from ui.server.db import get_sessions
    sessions = run(get_sessions(db_path))
    assert len(sessions) == 2
    # most recent first
    assert sessions[0]["session_id"] == "sess-2"


def test_get_sessions_parses_strategy_names(db_path):
    from ui.server.db import get_sessions
    sessions = run(get_sessions(db_path))
    closed = next(s for s in sessions if s["session_id"] == "sess-1")
    assert closed["strategy_names"] == ["StratA", "StratB"]


def test_get_live_session_returns_open(db_path):
    from ui.server.db import get_live_session
    live = run(get_live_session(db_path))
    assert live is not None
    assert live["session_id"] == "sess-2"
    assert live["ended_at"] is None


def test_get_live_session_returns_none_when_all_closed(db_path):
    from ui.server.db import get_live_session, get_sessions
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE sessions SET ended_at = '2024-01-02T11:00:00' WHERE session_id = 'sess-2'")
    conn.commit()
    conn.close()
    assert run(get_live_session(db_path)) is None


def test_get_snapshots_parses_json_fields(db_path):
    from ui.server.db import get_snapshots
    snaps = run(get_snapshots(db_path, "sess-1"))
    assert len(snaps) == 1
    assert snaps[0]["total_equity"] == 10_500.0
    assert isinstance(snaps[0]["strategy_pnl"], dict)
    assert snaps[0]["strategy_pnl"]["StratA"] == 300.0
    assert isinstance(snaps[0]["strategy_equity"], dict)


def test_get_new_snapshots_filters_by_id(db_path):
    from ui.server.db import get_snapshots, get_new_snapshots
    snaps = run(get_snapshots(db_path, "sess-1"))
    first_id = snaps[0]["id"]
    result = run(get_new_snapshots(db_path, "sess-1", after_id=first_id))
    assert result == []
    result = run(get_new_snapshots(db_path, "sess-1", after_id=0))
    assert len(result) == 1
