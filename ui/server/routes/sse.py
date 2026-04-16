import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..db import get_new_fills, get_new_snapshots

router = APIRouter()

_SSE_INTERVAL = 2.0  # seconds between DB polls


@router.get("/sse")
async def sse_stream(
    session_id: str,
    request: Request,
    max_polls: Optional[int] = None,
):
    """Stream SSE events for a trading session.

    Args:
        session_id: The session to stream events for.
        request: The HTTP request (used for disconnect detection in production).
        max_polls: If set, stop after this many DB poll cycles (used in tests).
    """
    db_path = request.app.state.db_path

    async def event_generator():
        last_snapshot_id = 0
        last_fill_id = 0
        polls = 0

        # Send an initial keep-alive comment so the client receives a chunk
        # immediately on connection (before the first poll interval elapses).
        yield ": keep-alive\n\n"

        while True:
            if max_polls is not None and polls >= max_polls:
                break

            if await request.is_disconnected():
                break

            new_snapshots = await get_new_snapshots(
                db_path, session_id, last_snapshot_id
            )
            if new_snapshots:
                last_snapshot_id = new_snapshots[-1]["id"]
                yield f"data: {json.dumps({'type': 'snapshots', 'data': new_snapshots})}\n\n"

            new_fills = await get_new_fills(
                db_path, session_id, last_fill_id
            )
            if new_fills:
                last_fill_id = new_fills[-1]["id"]
                yield f"data: {json.dumps({'type': 'fills', 'data': new_fills})}\n\n"

            polls += 1

            if max_polls is None:
                await asyncio.sleep(_SSE_INTERVAL)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
