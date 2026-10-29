"""
GenStudio FastAPI application entry point.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import secrets
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel, create_engine

from app.config import get_settings
from app.engine.process import engine_process
from app.gpu.monitor import start_monitor
from app.jobs import events as evt
from app.jobs.models import Asset, InstalledModel, Job, Lora, Preset
from app.jobs.queue import set_db_engine, start_scheduler

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("genstudio")

# ── FastAPI app ────────────────────────────────────────────────────────────
app = FastAPI(title="GenStudio", version="0.1.0")

cfg = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{cfg.port}",
        f"http://127.0.0.1:{cfg.port}",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── LAN access control ─────────────────────────────────────────────────────

_PROTECTED_PREFIXES = ("/api", "/media", "/uploads", "/ws")


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _extract_token(scope) -> str:
    for k, v in scope.get("headers", []):
        if k == b"authorization":
            val = v.decode("latin-1")
            if val.lower().startswith("bearer "):
                return val[7:].strip()
    qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    return (qs.get("token") or [""])[0]


class LanAuthMiddleware:
    """Pure ASGI middleware (covers HTTP and WebSocket) gating non-loopback clients."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        client = scope.get("client")
        if client and _is_loopback(client[0]):
            return await self.app(scope, receive, send)

        settings = get_settings()
        status, detail = None, ""
        if not settings.lan_access:
            status, detail = 403, "LAN access is disabled"
        elif scope["path"].startswith(_PROTECTED_PREFIXES):
            expected = settings.lan_token
            given = _extract_token(scope)
            if not expected or not secrets.compare_digest(given.encode(), expected.encode()):
                status, detail = 401, "Invalid or missing LAN token"

        if status is None:
            return await self.app(scope, receive, send)

        if scope["type"] == "websocket":
            await receive()
            return await send({"type": "websocket.close", "code": 1008})
        response = JSONResponse({"detail": detail}, status_code=status)
        await response(scope, receive, send)


app.add_middleware(LanAuthMiddleware)

# ── Routers ────────────────────────────────────────────────────────────────
from app.api.routes_system import router as sys_router
from app.api.routes_pipelines import router as pip_router
from app.api.routes_uploads import router as up_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_assets import router as assets_router
from app.api.routes_models import router as models_router
from app.api.routes_loras import router as loras_router
from app.api.routes_settings import router as settings_router

for r in (sys_router, pip_router, up_router, jobs_router,
          assets_router, models_router, loras_router, settings_router):
    app.include_router(r)

# ── WebSocket event stream ─────────────────────────────────────────────────

@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    q = evt.subscribe()

    async def sender() -> None:
        while True:
            await websocket.send_text(await q.get())

    async def receiver() -> None:
        while True:
            await websocket.receive_text()

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        evt.unsubscribe(q)

# ── Media static files ─────────────────────────────────────────────────────

outputs_dir = cfg.outputs_dir
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(outputs_dir)), name="media")

# Serve uploads
uploads_dir = cfg.data_dir / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# ── Startup/shutdown ───────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    # Database
    db_path = cfg.data_dir / "genstudio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SQLModel.metadata.create_all(engine)
    set_db_engine(engine)

    # Pipeline registry
    from app.pipelines.registry import pipeline_registry
    pipeline_registry.load_all()
    pipeline_registry.validate_models()

    # Start engine
    asyncio.create_task(engine_process.start(), name="engine-start")

    # Validate pipelines once engine is up
    asyncio.create_task(_validate_pipelines_when_ready(), name="validate-pipelines")

    # Job scheduler
    await start_scheduler()

    # GPU monitor
    await start_monitor()

    logger.info("GenStudio started at http://%s:%s", cfg.host, cfg.port)


async def _validate_pipelines_when_ready() -> None:
    from app.engine.client import comfy_client
    from app.pipelines.registry import pipeline_registry
    import time

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if engine_process.status == "ready":
            try:
                info = await comfy_client.object_info()
                await pipeline_registry.validate_against_engine(info)
                logger.info("Pipelines validated against engine")
            except Exception as e:
                logger.warning("Pipeline validation failed: %s", e)
            return
        await asyncio.sleep(2)


@app.on_event("shutdown")
async def shutdown():
    from app.jobs.queue import stop_scheduler
    from app.gpu.monitor import stop_monitor
    await stop_scheduler()
    await stop_monitor()
    await engine_process.stop()


# ── Frontend SPA ───────────────────────────────────────────────────────────

_RESERVED_PREFIXES = ("api", "media", "uploads", "ws", "docs", "redoc", "openapi.json", "assets")


def register_spa(application: FastAPI, dist: Path) -> None:
    """Serve the built frontend with index.html fallback for client-side routes."""
    dist = dist.resolve()
    if (dist / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        first = full_path.split("/", 1)[0]
        if first in _RESERVED_PREFIXES:
            raise HTTPException(404, "Not found")
        if full_path:
            candidate = (dist / full_path).resolve()
            if candidate.is_relative_to(dist) and candidate.is_file():
                return FileResponse(candidate)
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(404, "Frontend not built")
        return FileResponse(index)


frontend_dist = cfg.frontend_dist
if frontend_dist.exists():
    register_spa(app, frontend_dist)
else:
    from fastapi.responses import HTMLResponse
    @app.get("/")
    async def frontend_placeholder():
        return HTMLResponse("""
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>GenStudio</title>
<style>body{font-family:system-ui,sans-serif;background:#0f0f0f;color:#e0e0e0;
display:flex;flex-direction:column;align-items:center;justify-content:center;
min-height:100vh;margin:0;}
h1{font-size:2.5rem;margin-bottom:.5rem;background:linear-gradient(135deg,#7c3aed,#2563eb);
-webkit-background-clip:text;-webkit-text-fill-color:transparent}
p{color:#888;margin:.25rem 0}
a{color:#7c3aed;text-decoration:none}
</style>
</head>
<body>
<h1>✨ GenStudio</h1>
<p>Backend is running. Frontend not built yet.</p>
<p>Run <code>cd frontend && npm ci && npm run build</code></p>
<p>API: <a href="/docs">/docs</a></p>
</body></html>
""")
