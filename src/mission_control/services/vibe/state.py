"""Vibe scene state with SSE fan-out and optional persistence.

Ports v1's ``_state``, ``_state_lock``, ``_sse_qs``, ``_sse_lock``, and
``_broadcast()`` (alien_vibe.py:15-24). Persistence is implemented via a small
JSON file under the data dir (confirmed with user: persist last scene).
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from .models import SceneState


class VibeState:
    def __init__(self, persist_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._scene = 0
        self._persist_path = persist_path
        self._subscribers: list[asyncio.Queue] = []
        self._sub_lock = threading.Lock()
        if persist_path:
            self._load()

    # ── scene access ────────────────────────────────────────────────────────────

    def get(self) -> dict:
        with self._lock:
            return {"scene": self._scene}

    def set_scene(self, sid: int) -> bool:
        state = SceneState()
        if not state.is_valid_scene(sid):
            return False
        with self._lock:
            self._scene = sid
        if self._persist_path:
            self._save()
        self._broadcast()
        return True

    # ── SSE subscribers (async queues, one per connected client) ────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=20)
        with self._sub_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._sub_lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def _broadcast(self) -> None:
        payload = json.dumps(self.get()).encode()
        msg = b"data: " + payload + b"\n\n"
        with self._sub_lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    pass

    # ── persistence ─────────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"scene": self._scene}))
            tmp.replace(self._persist_path)
        except OSError:
            pass

    def _load(self) -> None:
        try:
            data = json.loads(self._persist_path.read_text())
            sid = int(data.get("scene", 0))
            if SceneState().is_valid_scene(sid):
                self._scene = sid
        except (OSError, ValueError, KeyError):
            pass
