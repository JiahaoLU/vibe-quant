import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trading.events import FillEvent, OrderEvent, SignalEvent, StrategyBundleEvent


def _make_logger(tmp_path):
    from trading.impl.trade_logger.sqlite_trade_logger import SqliteTradeLogger
    return SqliteTradeLogger(db_path=str(tmp_path / "trades.db"))


def _strategy_bundle(ts=None):
    ts = ts or datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc)
    return StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=0.8)},
        per_strategy={"strat_a": {"AAPL": 0.8}, "strat_b": {"AAPL": 0.2}},
    )


def _order(order_id="oid-1"):
    return OrderEvent(
        symbol="AAPL", timestamp=datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc),
        order_type="MARKET", direction="BUY", quantity=10,
        reference_price=150.0, order_id=order_id,
    )


def _fill(order_id="oid-1"):
    return FillEvent(
        symbol="AAPL", timestamp=datetime(2026, 4, 15, 14, 31, tzinfo=timezone.utc),
        direction="BUY", quantity=10, fill_price=150.5, commission=0.0,
        order_id=order_id,
    )


def test_open_session_creates_sessions_row(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", ["strat_a", "strat_b"])

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    row = conn.execute("SELECT session_id, mode, strategy_names, ended_at FROM sessions").fetchone()
    conn.close()

    assert row[0] == "sess-1"
    assert row[1] == "paper"
    assert json.loads(row[2]) == ["strat_a", "strat_b"]
    assert row[3] is None   # ended_at not set yet


def test_close_session_sets_ended_at(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.close_session("sess-1")

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    ended_at = conn.execute("SELECT ended_at FROM sessions WHERE session_id = 'sess-1'").fetchone()[0]
    conn.close()

    assert ended_at is not None


def test_log_signal_inserts_one_row_per_strategy_symbol(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.log_signal("sess-1", _strategy_bundle())

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    rows = conn.execute("SELECT strategy_id, symbol, weight FROM signals ORDER BY strategy_id").fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0] == ("strat_a", "AAPL", pytest.approx(0.8))
    assert rows[1] == ("strat_b", "AAPL", pytest.approx(0.2))


def test_log_order_inserts_orders_row(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.log_order("sess-1", _order("oid-1"))

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    row = conn.execute("SELECT order_id, symbol, direction, quantity, reference_price FROM orders").fetchone()
    conn.close()

    assert row == ("oid-1", "AAPL", "BUY", 10, pytest.approx(150.0))


def test_log_order_skips_hold(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    hold = OrderEvent(
        symbol="", timestamp=datetime(2026, 4, 15, tzinfo=timezone.utc),
        order_type="MARKET", direction="HOLD", quantity=0,
    )
    logger.log_order("sess-1", hold)

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()

    assert count == 0


def test_log_fill_inserts_fills_row(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.log_order("sess-1", _order("oid-1"))
    logger.log_fill("sess-1", _fill("oid-1"))

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    row = conn.execute("SELECT order_id, symbol, direction, quantity, fill_price, commission FROM fills").fetchone()
    conn.close()

    assert row == ("oid-1", "AAPL", "BUY", 10, pytest.approx(150.5), pytest.approx(0.0))


def test_log_fill_skips_hold(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    hold_fill = FillEvent(
        symbol="", timestamp=datetime(2026, 4, 15, tzinfo=timezone.utc),
        direction="HOLD", quantity=0, fill_price=0.0, commission=0.0,
    )
    logger.log_fill("sess-1", hold_fill)

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    count = conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
    conn.close()

    assert count == 0


def test_db_file_created_in_nested_directory(tmp_path):
    from trading.impl.trade_logger.sqlite_trade_logger import SqliteTradeLogger
    db_path = str(tmp_path / "nested" / "dir" / "trades.db")
    logger = SqliteTradeLogger(db_path=db_path)
    assert Path(db_path).exists()


def test_multiple_sessions_append_to_same_db(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.open_session("sess-2", "live", [])

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()

    assert count == 2
