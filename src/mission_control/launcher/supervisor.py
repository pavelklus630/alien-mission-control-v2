"""Service descriptor table and supervisor helpers.

Keeps all service-specific wiring in one place so the Tkinter launcher stays
free of import-level side effects from the four service packages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..config import Settings
from ..core.server import ThreadedUvicorn


@dataclass
class ServiceDescriptor:
    name: str
    tag: str
    icon: str
    port: int
    url_labels: list[tuple[str, str]]   # (label, url)
    _server: ThreadedUvicorn | None = field(default=None, repr=False)

    # Factory is resolved lazily to keep imports off the hot path.
    _factory: Callable | None = field(default=None, repr=False)

    @property
    def running(self) -> bool:
        return self._server is not None and self._server.is_running()

    def start(self, settings: Settings, on_crash: Callable[[], None]) -> None:
        if self._server and self._server.is_running():
            return
        app = self._factory(settings)
        self._server = ThreadedUvicorn(app, settings.host, self.port)
        self._server.start(on_crash=on_crash)

    def stop(self) -> None:
        if self._server:
            self._server.stop()
            self._server = None


def make_services(settings: Settings, lan_ip: str) -> list[ServiceDescriptor]:
    """Build the four service descriptors. Factories are imported here so the
    Tkinter launcher can be imported without pulling in the full service tree."""
    from ..services.soundboard.app import create_app as create_soundboard
    from ..services.terminal.app import create_app as create_terminal
    from ..services.vibe.app import create_app as create_vibe
    from ..services.map.app import create_app as create_map

    return [
        ServiceDescriptor(
            name="SOUNDBOARD",
            tag="AMBIENT AUDIO ENGINE",
            icon="wave",
            port=settings.port_soundboard,
            url_labels=[
                ("GM CONTROL", f"http://{lan_ip}:{settings.port_soundboard}/control"),
                ("OBS OUTPUT",  f"http://localhost:{settings.port_soundboard}/output"),
                ("SOUND EDITOR", f"http://{lan_ip}:{settings.port_soundboard}/editor"),
            ],
            _factory=create_soundboard,
        ),
        ServiceDescriptor(
            name="MU/TH/UR TERMINAL",
            tag="WEYLAND-YUTANI 6000",
            icon="term",
            port=settings.port_terminal,
            url_labels=[
                ("GM CONTROL", f"http://{lan_ip}:{settings.port_terminal}/input"),
                ("OBS DISPLAY", f"http://localhost:{settings.port_terminal}/display"),
            ],
            _factory=create_terminal,
        ),
        ServiceDescriptor(
            name="VIBE GENERATOR",
            tag="AMBIENT VISUAL SCENES",
            icon="wave",
            port=settings.port_vibe,
            url_labels=[
                ("GM CONTROL",   f"http://{lan_ip}:{settings.port_vibe}/control"),
                ("OBS DISPLAY",  f"http://localhost:{settings.port_vibe}/display"),
                ("SCENE EDITOR", f"http://{lan_ip}:{settings.port_vibe}/editor"),
            ],
            _factory=create_vibe,
        ),
        ServiceDescriptor(
            name="EREBOS STATION",
            tag="INTERACTIVE MAP",
            icon="map",
            port=settings.port_map,
            url_labels=[
                ("GM CONTROL", f"http://{lan_ip}:{settings.port_map}/control"),
                ("OBS DISPLAY", f"http://localhost:{settings.port_map}/display"),
            ],
            _factory=create_map,
        ),
    ]
