"""Terminal message log — in-memory list with cursor-based poll.

Ports v1's ``messages`` list + ``messages_lock`` (alien_terminal.py:24-25).
Messages are in-memory only (no persistence — Terminal is always live input).
"""

from __future__ import annotations

import threading
import time
from typing import Any

_PURGE_MESSAGE = {"text": "LOG PURGED. SYSTEM REINITIALISED.", "type": "system", "ts": 0.0}


class MessageLog:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._messages: list[dict[str, Any]] = []

    def send(self, text: str, msg_type: str = "user") -> None:
        with self._lock:
            self._messages.append({"text": text, "type": msg_type, "ts": time.time()})

    def purge(self) -> None:
        with self._lock:
            self._messages.clear()
            self._messages.append({**_PURGE_MESSAGE, "ts": time.time()})

    def poll(self, since: int) -> tuple[list[dict[str, Any]], int]:
        """Return ``(messages[since:], total)`` — v1's cursor-poll contract."""
        with self._lock:
            return self._messages[since:], len(self._messages)
