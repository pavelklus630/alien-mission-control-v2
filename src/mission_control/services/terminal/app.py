"""Terminal FastAPI app factory + standalone dev runner."""

from __future__ import annotations

from fastapi import FastAPI

from ...config import Settings, get_settings
from ...core.app_factory import create_service_app
from ...paths import resource_dir
from .routes import build_router
from .state import MessageLog


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    sounds_dir = settings.resolved_terminal_sounds_dir
    app = create_service_app("Terminal")
    log = MessageLog()
    app.include_router(build_router(settings, log, sounds_dir))
    app.state.settings = settings
    app.state.log = log
    return app


def main() -> None:
    import uvicorn
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port_terminal)


if __name__ == "__main__":
    main()
