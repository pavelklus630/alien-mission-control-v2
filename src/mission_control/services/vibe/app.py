"""Vibe Generator FastAPI app factory + standalone dev runner."""

from __future__ import annotations

from fastapi import FastAPI

from ...config import Settings, get_settings
from ...core.app_factory import create_service_app
from .routes import build_router
from .state import VibeState


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    persist_path = settings.data_dir / "vibe" / "scene.json"
    app = create_service_app("Vibe")
    state = VibeState(persist_path=persist_path)
    app.include_router(build_router(settings, state))
    app.state.settings = settings
    app.state.vibe = state
    return app


def main() -> None:
    import uvicorn
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port_vibe)


if __name__ == "__main__":
    main()
