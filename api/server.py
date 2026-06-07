"""
FastAPI application — Lyft Support Agent backend.

Serves:
  /api/chat          → customer support chat API
  /api/agents        → internal agent builder API
  /health            → health check
  /                  → customer chat UI  (ui/chat/index.html)
  /builder           → agent builder UI  (ui/builder/index.html)
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routes import health, chat, agents

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Lyft Support Agent",
    description="Multi-agent customer support system with self-serve agent builder",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

app.include_router(health.router, tags=["health"])
app.include_router(chat.router,   prefix="/api", tags=["chat"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])

# ---------------------------------------------------------------------------
# Static UI files
# ---------------------------------------------------------------------------

UI_DIR = Path(__file__).parent.parent / "ui"

# Mount static assets (CSS, JS, images) for each UI
app.mount("/ui/chat",    StaticFiles(directory=UI_DIR / "chat"),    name="chat-static")
app.mount("/ui/builder", StaticFiles(directory=UI_DIR / "builder"), name="builder-static")


@app.get("/", include_in_schema=False)
def chat_ui():
    """Serve the customer-facing chat UI."""
    return FileResponse(UI_DIR / "chat" / "index.html")


@app.get("/builder", include_in_schema=False)
def builder_ui():
    """Serve the internal agent builder UI."""
    return FileResponse(UI_DIR / "builder" / "index.html")


# ---------------------------------------------------------------------------
# Run directly: python api/server.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=True,
        reload_dirs=[str(Path(__file__).parent.parent)],
    )
