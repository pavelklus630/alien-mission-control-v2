"""FastAPI application factory shared by all four services.

Each service calls :func:`create_service_app` and mounts its own router. This
is the code-level unification the Phase 1 analysis recommended: shared CORS,
caching, and middleware — while each service still runs on its own port and has
its own lifetime (Option A).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .middleware import NoCacheMiddleware

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_service_app(name: str, *, lifespan: Lifespan | None = None) -> FastAPI:
    app = FastAPI(
        title=f"Mission Control · {name}",
        version="2.0.0a0",
        lifespan=lifespan,
        # No interactive docs surface on a LAN-exposed GM tool by default.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(NoCacheMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app
