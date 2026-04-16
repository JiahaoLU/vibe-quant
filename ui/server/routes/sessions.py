from fastapi import APIRouter, HTTPException, Request
from ..db import (
    get_fills,
    get_live_session,
    get_orders,
    get_sessions,
    get_signals,
    get_snapshots,
)

router = APIRouter()


@router.get("/sessions")
async def list_sessions(request: Request):
    return await get_sessions(request.app.state.db_path)


@router.get("/sessions/live")
async def live_session(request: Request):
    session = await get_live_session(request.app.state.db_path)
    if session is None:
        raise HTTPException(status_code=404, detail="No live session")
    return session


@router.get("/sessions/{session_id}/snapshots")
async def session_snapshots(session_id: str, request: Request):
    return await get_snapshots(request.app.state.db_path, session_id)


@router.get("/sessions/{session_id}/fills")
async def session_fills(session_id: str, request: Request):
    return await get_fills(request.app.state.db_path, session_id)


@router.get("/sessions/{session_id}/orders")
async def session_orders(session_id: str, request: Request):
    return await get_orders(request.app.state.db_path, session_id)


@router.get("/sessions/{session_id}/signals")
async def session_signals(session_id: str, request: Request):
    return await get_signals(request.app.state.db_path, session_id)
