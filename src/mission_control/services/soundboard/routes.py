"""Soundboard HTTP routes — preserves the exact v1 contract so existing
control/output pages and OBS sources keep working:

    GET  /  /control      → control.html (GM remote)
    GET  /output          → output.html (OBS Browser Source)
    GET  /state           → playback + voice snapshot (polled at 1 Hz)
    GET  /sounds.json     → ordered category tree
    GET  /audio/<relpath> → Range-streamed audio
    POST /                → {action, ...} mutates shared state
    GET  /api/sounds      → structured Sound list (v2 editor/upload seam)
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from ...config import Settings
from ...core.ranges import range_response
from ...core.templating import service_templates
from ...core.uploads import UploadError, safe_join
from .repository import SoundLibrary
from .state import PlaybackState

_templates = service_templates(__file__)


def build_router(settings: Settings, library: SoundLibrary, state: PlaybackState) -> APIRouter:
    router = APIRouter()
    sounds_dir = settings.resolved_sounds_dir

    @router.get("/", response_class=HTMLResponse)
    @router.get("/control", response_class=HTMLResponse)
    async def control(request: Request) -> Response:
        return _templates.TemplateResponse(request, "control.html", _page_ctx(settings))

    @router.get("/output", response_class=HTMLResponse)
    async def output(request: Request) -> Response:
        return _templates.TemplateResponse(request, "output.html", _page_ctx(settings))

    @router.get("/state")
    async def get_state() -> JSONResponse:
        return JSONResponse(state.snapshot())

    @router.get("/sounds.json")
    async def sounds_json() -> JSONResponse:
        return JSONResponse(library.categories())

    @router.get("/api/sounds")
    async def api_sounds() -> JSONResponse:
        """Flat structured list — the seam future editor/upload UIs consume."""
        flat = [s for items in library.categories().values() for s in items]
        return JSONResponse(flat)

    @router.get("/audio/{file_path:path}")
    async def audio(file_path: str, request: Request) -> Response:
        try:
            target = safe_join(sounds_dir, file_path)
        except UploadError:
            return Response(status_code=403)
        return range_response(target, request)

    @router.post("/")
    async def command(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)
        if isinstance(body, dict):
            state.apply(body)
        return JSONResponse({"ok": True})

    return router


def _page_ctx(settings: Settings) -> dict[str, object]:
    # Available to templates now; unused by the ported v1 markup, consumed later
    # by editor/upload UI.
    return {
        "enable_uploads": settings.enable_uploads,
        "enable_editors": settings.enable_editors,
    }
