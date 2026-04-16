# Trade Monitor UI — Design Spec
_Date: 2026-04-16_

## Overview

A local web UI for visualising `logs/trades.db` (written by `SqliteTradeLogger`). Supports both live session monitoring (auto-refreshing via SSE) and reviewing completed past sessions.

Stack: FastAPI (Python) backend + Vite/React/TypeScript frontend + Plotly.js charts.

---

## Folder structure

```
ui/
  server/
    __init__.py
    app.py          # FastAPI app factory; accepts db_path
    db.py           # All SQLite query functions (via asyncio.to_thread)
    routes/
      sessions.py   # REST endpoints for session list + per-session data
      sse.py        # SSE endpoint for live updates
  frontend/
    index.html
    package.json    # vite, react, typescript, plotly.js, @types/*
    tsconfig.json
    vite.config.ts  # proxy /api → localhost:8000
    src/
      main.tsx
      App.tsx
      types.ts          # mirrors DB schema (Session, Fill, Order, Signal, Snapshot)
      components/
        Header.tsx        # session picker, live badge, equity/P&L/fills stats, SSE indicator
        TradeSummary.tsx  # stat cards + per-symbol table
        EquityChart.tsx   # Plotly line — total_equity + per-strategy lines
        FillsChart.tsx    # Plotly scatter — fill_price vs time, buy/sell per symbol
        SignalHeatmap.tsx # Plotly heatmap — symbols × time, weight as colour
        CommissionsChart.tsx # Plotly grouped bar — commission + slippage per symbol
      hooks/
        useSessionData.ts # fetches all data for a given session_id
        useLiveSSE.ts     # subscribes to /api/sse, merges new snapshots/fills into state
```

---

## Backend

### FastAPI app (`ui/server/app.py`)

- Created by `create_app(db_path: str) -> FastAPI`
- Module-level `app = create_app("logs/trades.db")` instance for `uvicorn` dev reloading
- CORS enabled for `localhost:5173` (Vite dev server)
- Mounts `routes/sessions` and `routes/sse`

### DB queries (`ui/server/db.py`)

All functions use `asyncio.to_thread(sqlite3_call)` so the blocking `sqlite3` driver never stalls the trading event loop.

| Function | Query |
|---|---|
| `get_sessions()` | `SELECT * FROM sessions ORDER BY started_at DESC` |
| `get_live_session()` | Most recent session where `ended_at IS NULL` |
| `get_snapshots(session_id)` | `pnl_snapshots` for session, ordered by timestamp; `strategy_pnl` and `strategy_equity` JSON strings parsed to dicts before return |
| `get_fills(session_id)` | `fills` for session |
| `get_orders(session_id)` | `orders` for session |
| `get_signals(session_id)` | `signals` for session |
| `get_new_snapshots(session_id, after_id)` | Snapshots with `id > after_id` (used by SSE) |
| `get_new_fills(session_id, after_id)` | Fills with `id > after_id` (used by SSE) |

### REST endpoints (`routes/sessions.py`)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/sessions` | List of all sessions |
| GET | `/api/sessions/live` | Current live session or 404 |
| GET | `/api/sessions/{id}/snapshots` | All pnl_snapshots for session |
| GET | `/api/sessions/{id}/fills` | All fills |
| GET | `/api/sessions/{id}/orders` | All orders |
| GET | `/api/sessions/{id}/signals` | All signals |

### SSE endpoint (`routes/sse.py`)

`GET /api/sse?session_id={id}`

- Streams `text/event-stream`
- Polls DB every 2 s for new rows (snapshot `id > last_seen_id`, fill `id > last_seen_id`)
- Pushes JSON events: `{"type": "snapshots"|"fills", "data": [...]}`
- Exits cleanly when the client disconnects

### Integration into `run_live.py`

```python
import uvicorn
from ui.server.app import create_app

async def main():
    ui_app = create_app(db_path="logs/trades.db")
    ui_config = uvicorn.Config(ui_app, host="127.0.0.1", port=8000, log_level="warning")
    ui_server = uvicorn.Server(ui_config)

    runner = LiveRunner(...)
    await asyncio.gather(
        runner.run(),
        ui_server.serve(),
    )
```

Both share the same asyncio event loop. DB reads are offloaded via `asyncio.to_thread`, so uvicorn request handling never blocks the trading dispatch path.

---

## Frontend

### Layout (top → bottom)

1. **Header** — app name, session picker dropdown, LIVE badge (red, pulsing) when a live session exists, equity / P&L / fill-count stats, SSE connection indicator
2. **Trade summary** — stat cards: total fills, buy count, sell count, total qty, total commission, avg slippage · per-symbol breakdown table below
3. **Row (50/50)** — Equity curve (left) · Fills scatter (right)
4. **Row (50/50)** — Signal heatmap (left) · Commissions & slippage bar (right)

### Charts

| Component | Plotly trace type | Data source |
|---|---|---|
| EquityChart | `scatter` mode `lines` | `pnl_snapshots.total_equity` + `strategy_equity` JSON |
| FillsChart | `scatter` mode `markers` | `fills.fill_price`, symbol=marker colour, direction=marker symbol |
| SignalHeatmap | `heatmap` | `signals` pivoted: x=timestamp, y=symbol, z=weight; colorscale RdYlGn |
| CommissionsChart | `bar` (grouped) | `fills` aggregated: commission sum + mean slippage per symbol |

### Live refresh (`useLiveSSE.ts`)

- Opens `EventSource` to `/api/sse?session_id={id}` when a live session is selected
- On `snapshots` event: appends new rows to equity state
- On `fills` event: appends new fills, re-derives summary stats
- Closes and reopens if the selected session changes
- Shows "SSE connected / reconnecting / disconnected" in the header

### Session switching

- Dropdown in header lists all sessions (live session pinned at top with badge)
- Selecting a different session: cancels SSE (if active), fetches full data for selected session via REST, re-renders all charts
- Past sessions: all data fetched once on selection, no SSE

---

## Dev workflow

```bash
# Terminal 1 — backend (or just run run_live.py to get both)
# app.py exposes a module-level `app` instance pointing at logs/trades.db
uvicorn ui.server.app:app --reload --port 8000

# Terminal 2 — frontend
cd ui/frontend && npm install && npm run dev
# → http://localhost:5173
```

Vite proxies `/api/*` to `http://localhost:8000` so there are no CORS issues in dev.

---

## Dependencies added

| Package | Where | Purpose |
|---|---|---|
| `fastapi>=0.110` | `requirements.txt` | API server |
| `uvicorn>=0.29` | `requirements.txt` | ASGI server |
| `plotly` (npm) | `ui/frontend/package.json` | Charts |
| `react`, `react-dom` | npm | UI framework |
| `typescript`, `@types/react` | npm | Type safety |
| `vite` | npm | Dev server + bundler |

---

## What is out of scope

- Authentication / access control (local tool only)
- WebSocket bidirectional control (pause strategy, cancel order)
- Mobile layout
- Dark/light theme toggle (dark only)
