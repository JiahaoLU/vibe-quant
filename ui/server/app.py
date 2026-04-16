from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import sessions, sse


def create_app(db_path: str = "logs/trades.db") -> FastAPI:
    app = FastAPI(title="vibe-quant trade monitor")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.db_path = db_path
    app.include_router(sessions.router, prefix="/api")
    app.include_router(sse.router, prefix="/api")
    return app


# Module-level instance for `uvicorn ui.server.app:app --reload`
app = create_app()
