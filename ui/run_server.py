"""
Standalone trade monitor server.
Serves the FastAPI backend (REST + SSE) on :8000.

Usage:
    python ui/run_server.py
"""
import uvicorn
from ui.server.app import create_app

HOST       = "127.0.0.1"
PORT       = 8000
TRADE_LOG  = "logs/trades.db"

if __name__ == "__main__":
    app = create_app(db_path=TRADE_LOG)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
