"""Cross-cutting HTTP behavior shared by every service.

- CORS ``*`` so the GM can drive ``/control`` from a phone on the LAN (v1 parity).
- ``Cache-Control: no-store`` on every response: these are local, single-user
  services and OBS Browser Sources must always fetch fresh markup/state.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        return response
