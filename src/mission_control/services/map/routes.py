"""Map HTTP routes — preserves the exact v1 contract:

    GET  /  /control        → control page
    GET  /display           → OBS display page
    GET  /api/state         → GM state (polled at 2 Hz by display page)
    POST /api/toggle        → toggle title_hidden
    POST /api/toggle-menu   → toggle menu_hidden
    GET  /assets/* /fonts/* /maps/* /ludicrpg.png → serve map cache (Range-enabled)
    GET  /api/maps/erebos   → structured map descriptor (v2 seam)

Range streaming is applied to all cache files (fixes v1's whole-file-in-RAM
debt for map-bundle.bin, which can be large).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from ...config import Settings
from ...core.ranges import range_response
from ...core.uploads import safe_join, UploadError
from .state import MapState

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_STATIC_PREFIXES = ("/assets/", "/fonts/", "/maps/")
_SPECIAL_FILES = {"/ludicrpg.png"}


def build_router(settings: Settings, state: MapState, cache_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    @router.get("/control", response_class=HTMLResponse)
    async def control() -> Response:
        return FileResponse(_TEMPLATES / "control.html", media_type="text/html")

    @router.get("/display", response_class=HTMLResponse)
    async def display() -> Response:
        return FileResponse(_TEMPLATES / "display.html", media_type="text/html")

    @router.get("/api/state")
    async def get_state() -> JSONResponse:
        return JSONResponse(state.snapshot())

    @router.get("/api/maps/erebos")
    async def erebos_descriptor() -> JSONResponse:
        """Structured map descriptor — the seam a future multi-map UI consumes."""
        return JSONResponse({
            "id": "erebos",
            "name": "Erebos Station",
            "bundle": "/maps/erebos/bundle/map-bundle.bin",
        })

    @router.post("/api/toggle")
    async def toggle_title() -> JSONResponse:
        return JSONResponse(state.toggle("title_hidden"))

    @router.post("/api/toggle-menu")
    async def toggle_menu() -> JSONResponse:
        return JSONResponse(state.toggle("menu_hidden"))

    @router.get("/{file_path:path}")
    async def serve_cache(file_path: str, request: Request) -> Response:
        full = "/" + file_path.lstrip("/")
        is_static = any(full.startswith(p) for p in _STATIC_PREFIXES) or full in _SPECIAL_FILES
        if not is_static:
            return Response(status_code=404)
        try:
            target = safe_join(cache_dir, file_path)
        except UploadError:
            return Response(status_code=403)
        # Use Range streaming for all cache files (fixes v1's RAM-loading of
        # map-bundle.bin; also correct for the JS/CSS/woff2 assets).
        return range_response(target, request)

    return router
