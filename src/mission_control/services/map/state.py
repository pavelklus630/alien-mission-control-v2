"""Map GM state — title/menu visibility toggles. Thread-safe, in-memory."""

from __future__ import annotations

import threading


class MapState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._title_hidden = False
        self._menu_hidden = False

    def snapshot(self) -> dict:
        with self._lock:
            return {"title_hidden": self._title_hidden, "menu_hidden": self._menu_hidden}

    def toggle(self, key: str) -> dict:
        with self._lock:
            if key == "title_hidden":
                self._title_hidden = not self._title_hidden
            elif key == "menu_hidden":
                self._menu_hidden = not self._menu_hidden
            return {"title_hidden": self._title_hidden, "menu_hidden": self._menu_hidden}
