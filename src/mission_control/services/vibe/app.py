"""Vibe Generator FastAPI app factory + standalone dev runner."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ...config import Settings, get_settings
from ...core.app_factory import create_service_app
from .asset_store import AssetStore
from .editor_routes import build_editor_router
from .routes import build_router
from .scene_store import SceneStore
from .state import VibeState

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    persist_path = settings.data_dir / "vibe" / "scene.json"
    app = create_service_app("Vibe")
    state = VibeState(persist_path=persist_path)
    app.include_router(build_router(settings, state))

    scene_store = SceneStore(settings.data_dir)
    asset_store = AssetStore(settings.data_dir)
    app.include_router(build_editor_router(settings, scene_store, asset_store))

    # Serve the vendored 3D engine (Three.js + vibe3d.js) for renderer:"3d" scenes.
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    app.state.settings = settings
    app.state.vibe = state
    return app


def main() -> None:
    import uvicorn
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port_vibe)


if __name__ == "__main__":
    main()
