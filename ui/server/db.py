import asyncio
import json
import sqlite3


async def _query(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
    def _run():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    return await asyncio.to_thread(_run)


async def get_sessions(db_path: str) -> list[dict]:
    rows = await _query(
        db_path,
        "SELECT * FROM sessions ORDER BY started_at DESC",
    )
    for row in rows:
        row["strategy_names"] = json.loads(row["strategy_names"])
    return rows


async def get_live_session(db_path: str) -> dict | None:
    rows = await _query(
        db_path,
        "SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
    )
    if not rows:
        return None
    rows[0]["strategy_names"] = json.loads(rows[0]["strategy_names"])
    return rows[0]


async def get_snapshots(db_path: str, session_id: str) -> list[dict]:
    rows = await _query(
        db_path,
        "SELECT * FROM pnl_snapshots WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    )
    for row in rows:
        row["strategy_pnl"] = json.loads(row["strategy_pnl"])
        row["strategy_equity"] = json.loads(row["strategy_equity"])
    return rows


async def get_fills(db_path: str, session_id: str) -> list[dict]:
    return await _query(
        db_path,
        "SELECT * FROM fills WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    )


async def get_orders(db_path: str, session_id: str) -> list[dict]:
    return await _query(
        db_path,
        "SELECT * FROM orders WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    )


async def get_signals(db_path: str, session_id: str) -> list[dict]:
    return await _query(
        db_path,
        "SELECT * FROM signals WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    )


async def get_new_snapshots(
    db_path: str, session_id: str, after_id: int
) -> list[dict]:
    rows = await _query(
        db_path,
        "SELECT * FROM pnl_snapshots WHERE session_id = ? AND id > ? ORDER BY id",
        (session_id, after_id),
    )
    for row in rows:
        row["strategy_pnl"] = json.loads(row["strategy_pnl"])
        row["strategy_equity"] = json.loads(row["strategy_equity"])
    return rows


async def get_new_fills(
    db_path: str, session_id: str, after_id: int
) -> list[dict]:
    return await _query(
        db_path,
        "SELECT * FROM fills WHERE session_id = ? AND id > ? ORDER BY id",
        (session_id, after_id),
    )
