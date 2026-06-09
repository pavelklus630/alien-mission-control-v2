"""Soundboard FastAPI app factory + standalone dev runner.

    python -m mission_control.services.soundboard.app    # run just this service
"""

from __future__ import annotations

from fastapi import FastAPI

from ...config import Settings, get_settings
from ...core.app_factory import create_service_app
from .bank_store import BankStore
from .routes import build_router
from .state import PlaybackState


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = create_service_app("Soundboard")
    library = BankStore(settings)
    state = PlaybackState()
    app.include_router(build_router(settings, library, state))
    # Expose for tests / launcher introspection.
    app.state.settings = settings
    app.state.library = library
    app.state.playback = state
    return app


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port_soundboard)


if __name__ == "__main__":
    main()
