"""Shared playback state driven by the GM control page and read by the OBS
output page. Ports v1's play_state/voice_state + action handlers
(alien_soundboard.py:29-82) behind a small thread-safe class.
"""

from __future__ import annotations

import threading
from typing import Any


class PlaybackState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._play: dict[str, dict[str, Any]] = {}
        self._voice: dict[str, Any] = {"active": False, "deviceId": ""}

    def apply(self, body: dict[str, Any]) -> None:
        """Apply one control command. Unknown actions are ignored (v1 parity)."""
        action = body.get("action")
        with self._lock:
            if action == "play":
                self._play[body["path"]] = {
                    "loop": body.get("loop", False),
                    "volume": body.get("volume", 1.0),
                }
            elif action == "stop":
                self._play.pop(body.get("path"), None)
            elif action == "stop_all":
                self._play.clear()
            elif action == "volume":
                if body.get("path") in self._play:
                    self._play[body["path"]]["volume"] = body.get("volume", 1.0)
            elif action == "voice_on":
                self._voice["active"] = True
                self._voice["deviceId"] = body.get("deviceId", "")
            elif action == "voice_off":
                self._voice["active"] = False
                self._voice["deviceId"] = ""

    def snapshot(self) -> dict[str, Any]:
        """State payload for ``/state`` — play entries plus the ``_voice`` block."""
        with self._lock:
            data: dict[str, Any] = dict(self._play)
            data["_voice"] = dict(self._voice)
            return data
