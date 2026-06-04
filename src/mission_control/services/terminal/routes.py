"""Terminal HTTP routes — preserves the exact v1 contract:

    GET  /  /input          → input (GM control) page
    GET  /display           → display (OBS) page
    GET  /poll?since=N      → cursor-based message poll
    GET  /sounds/<filename> → serve terminal sound (OGG, by name only, safe)
    POST /send              → {text, type} | {_purge: true}
    GET  /api/log           → structured message list (v2 seam)

Note: Terminal HTML is served as plain FileResponse, not Jinja templates.
The v1 markup contains CSS ``{#selector}`` patterns that collide with Jinja2's
comment delimiter. Since the pages need no server-side variable injection, raw
file serving is simpler and correct.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from ...config import Settings

_TEMPLATES = Path(__file__).resolve().parent / "templates"


def build_router(settings: Settings, log, sounds_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    @router.get("/input", response_class=HTMLResponse)
    async def input_page() -> Response:
        return FileResponse(_TEMPLATES / "input.html", media_type="text/html")

    @router.get("/display", response_class=HTMLResponse)
    async def display() -> Response:
        return FileResponse(_TEMPLATES / "display.html", media_type="text/html")

    @router.get("/poll")
    async def poll(since: int = 0) -> JSONResponse:
        msgs, total = log.poll(since)
        return JSONResponse({"messages": msgs, "total": total})

    @router.get("/api/log")
    async def api_log() -> JSONResponse:
        msgs, total = log.poll(0)
        return JSONResponse({"messages": msgs, "total": total})

    @router.get("/sounds/{filename}")
    async def sound(filename: str) -> Response:
        # Use only the final filename component — mirrors v1's .name trick but
        # more explicit and audit-visible (no path traversal possible).
        safe_name = Path(filename).name
        if not safe_name.lower().endswith(".ogg"):
            return Response(status_code=403)
        filepath = sounds_dir / safe_name
        if not filepath.is_file():
            return Response(status_code=404)
        data = filepath.read_bytes()
        return Response(content=data, media_type="audio/ogg")

    @router.post("/send")
    async def send(request: Request) -> JSONResponse:
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"error": "bad json"}, status_code=400)
        if data.get("_purge"):
            log.purge()
        else:
            log.send(data.get("text", ""), data.get("type", "user"))
        return JSONResponse({"ok": True})

    return router
