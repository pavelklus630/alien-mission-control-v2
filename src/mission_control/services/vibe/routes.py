"""Vibe HTTP routes — preserves the exact v1 contract:

    GET  /  /control  /control.html  → control page
    GET  /display  /display.html     → OBS display page
    GET  /api/scene                  → current scene state
    GET  /api/events                 → SSE stream (push on scene change + 20s ping)
    POST /api/scene                  → {scene: N} set scene
    GET  /api/scenes                 → structured scene list (v2 seam)
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse

from ...config import Settings
from .state import VibeState

_TEMPLATES = __import__("pathlib").Path(__file__).resolve().parent / "templates"

_SSE_PING_INTERVAL = 20  # seconds


def build_router(settings: Settings, state: VibeState) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    @router.get("/control", response_class=HTMLResponse)
    @router.get("/control.html", response_class=HTMLResponse)
    async def control() -> Response:
        return FileResponse(_TEMPLATES / "control.html", media_type="text/html")

    @router.get("/display", response_class=HTMLResponse)
    @router.get("/display.html", response_class=HTMLResponse)
    async def display() -> Response:
        return FileResponse(_TEMPLATES / "display.html", media_type="text/html")

    @router.get("/api/scene")
    async def get_scene() -> JSONResponse:
        return JSONResponse(state.get())

    @router.get("/api/scenes")
    async def api_scenes() -> JSONResponse:
        from .models import SCENE_NAMES
        return JSONResponse([{"id": i, "name": n} for i, n in enumerate(SCENE_NAMES)])

    @router.get("/api/events")
    async def sse(request: Request) -> StreamingResponse:
        q = state.subscribe()

        async def generator():
            # Send current state immediately on connect (v1 parity).
            import json as _json
            yield b"data: " + _json.dumps(state.get()).encode() + b"\n\n"
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=_SSE_PING_INTERVAL)
                        yield msg
                    except asyncio.TimeoutError:
                        yield b": ping\n\n"
            finally:
                state.unsubscribe(q)

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    @router.post("/api/scene")
    async def set_scene(request: Request) -> JSONResponse:
        try:
            data = await request.json()
            sid = int(data["scene"])
        except Exception:
            return JSONResponse({"error": "bad request"}, status_code=400)
        if not state.set_scene(sid):
            return JSONResponse({"error": "invalid scene"}, status_code=400)
        return JSONResponse(state.get())

    return router
