"""Vibe scene state with SSE fan-out and optional persistence."""

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
        self._scene_id: str | None = None  # string ID when set via set_scene_by_id
        self._persist_path = persist_path
        self._subscribers: list[asyncio.Queue] = []
        self._sub_lock = threading.Lock()
        if persist_path:
            self._load()

    # ── scene access ────────────────────────────────────────────────────────────

    def get(self) -> dict:
        with self._lock:
            result: dict = {"scene": self._scene}
            if self._scene_id is not None:
                result["scene_id"] = self._scene_id
            return result

    def set_scene(self, sid: int) -> bool:
        state = SceneState()
        if not state.is_valid_scene(sid):
            return False
        with self._lock:
            self._scene = sid
            self._scene_id = None  # clear string ID; display maps by integer
        if self._persist_path:
            self._save()
        self._broadcast()
        return True

    def set_scene_by_id(self, scene_id: str) -> None:
        """Switch to any scene (builtin or custom) by string ID.
        Broadcasts scene_id via SSE so display.html can load the JSON directly."""
        with self._lock:
            self._scene_id = scene_id
            self._scene = -1  # sentinel: -1 means "use scene_id"
        if self._persist_path:
            self._save()
        self._broadcast()

    # ── SSE subscribers ──────────────────────────────────────────────────────────

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
            data: dict = {"scene": self._scene}
            if self._scene_id is not None:
                data["scene_id"] = self._scene_id
            tmp = self._persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(self._persist_path)
        except OSError:
            pass

    def _load(self) -> None:
        try:
            data = json.loads(self._persist_path.read_text())
            sid = int(data.get("scene", 0))
            scene_id = data.get("scene_id")
            if scene_id:
                self._scene_id = str(scene_id)
                self._scene = sid  # may be -1
            elif SceneState().is_valid_scene(sid):
                self._scene = sid
        except (OSError, ValueError, KeyError):
            pass
