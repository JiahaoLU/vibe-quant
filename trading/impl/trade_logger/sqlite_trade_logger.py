import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ...base.live.trade_logger import TradeLogger
from ...events import FillEvent, OrderEvent, StrategyBundleEvent

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    started_at     TEXT NOT NULL,
    ended_at       TEXT,
    mode           TEXT NOT NULL,
    strategy_names TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    timestamp    TEXT    NOT NULL,
    strategy_id  TEXT    NOT NULL,
    symbol       TEXT    NOT NULL,
    weight       REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    order_id        TEXT    NOT NULL UNIQUE,
    timestamp       TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    quantity        INTEGER NOT NULL,
    reference_price REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    order_id     TEXT    NOT NULL,
    timestamp    TEXT    NOT NULL,
    symbol       TEXT    NOT NULL,
    direction    TEXT    NOT NULL,
    quantity     INTEGER NOT NULL,
    fill_price   REAL    NOT NULL,
    commission   REAL    NOT NULL
);
"""


class SqliteTradeLogger(TradeLogger):
    """Appends all trade events to a single SQLite database file."""

    def __init__(self, db_path: str = "logs/trades.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_DDL)
        self._conn.commit()

    def open_session(self, session_id: str, mode: str, strategy_names: list[str]) -> None:
        self._conn.execute(
            "INSERT INTO sessions (session_id, started_at, mode, strategy_names) VALUES (?, ?, ?, ?)",
            (session_id, datetime.now(timezone.utc).isoformat(), mode, json.dumps(strategy_names)),
        )
        self._conn.commit()

    def log_signal(self, session_id: str, event: StrategyBundleEvent) -> None:
        rows = [
            (session_id, event.timestamp.isoformat(), strategy_id, symbol, weight)
            for strategy_id, symbols in event.per_strategy.items()
            for symbol, weight in symbols.items()
        ]
        self._conn.executemany(
            "INSERT INTO signals (session_id, timestamp, strategy_id, symbol, weight) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def log_order(self, session_id: str, event: OrderEvent) -> None:
        if event.direction == "HOLD":
            return
        self._conn.execute(
            "INSERT INTO orders (session_id, order_id, timestamp, symbol, direction, quantity, reference_price)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, event.order_id, event.timestamp.isoformat(),
             event.symbol, event.direction, event.quantity, event.reference_price),
        )
        self._conn.commit()

    def log_fill(self, session_id: str, event: FillEvent) -> None:
        if event.direction == "HOLD":
            return
        self._conn.execute(
            "INSERT INTO fills (session_id, order_id, timestamp, symbol, direction, quantity, fill_price, commission)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, event.order_id, event.timestamp.isoformat(),
             event.symbol, event.direction, event.quantity, event.fill_price, event.commission),
        )
        self._conn.commit()

    def close_session(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE session_id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
        self._conn.commit()
