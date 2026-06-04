"""Map FastAPI app factory + standalone dev runner."""

from __future__ import annotations

from fastapi import FastAPI

from ...config import Settings, get_settings
from ...core.app_factory import create_service_app
from .routes import build_router
from .state import MapState


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    cache_dir = settings.resolved_map_cache_dir
    app = create_service_app("Map")
    state = MapState()
    app.include_router(build_router(settings, state, cache_dir))
    app.state.settings = settings
    app.state.map = state
    return app


def main() -> None:
    import uvicorn
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port_map)


if __name__ == "__main__":
    main()
