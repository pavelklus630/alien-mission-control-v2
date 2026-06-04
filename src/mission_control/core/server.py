"""Run a uvicorn server on its own thread so the Tkinter launcher (main thread)
can supervise all four services and start/stop each independently.

This is the Option-A port mechanism: one ``ThreadedUvicorn`` per service, each
binding its own port. ``install_signal_handlers=False`` is required off the main
thread; ``should_exit`` gives a clean shutdown (fixes v1's quit-race and the
Vibe SSE shutdown hang).
"""

from __future__ import annotations

import threading

import uvicorn
from fastapi import FastAPI


class ThreadedUvicorn:
    def __init__(self, app: FastAPI, host: str, port: int):
        self._config = uvicorn.Config(app, host=host, port=port, log_config=None, lifespan="on")
        self.server = uvicorn.Server(self._config)
        self.server.install_signal_handlers = False
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._config.port

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.server.run, daemon=True, name=f"uvicorn:{self.port}")
        self._thread.start()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self.server.started)

    def stop(self, timeout: float = 5.0) -> None:
        self.server.should_exit = True
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
