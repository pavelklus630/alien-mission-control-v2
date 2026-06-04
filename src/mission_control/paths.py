"""Filesystem path resolution that works both in dev and in a frozen .app bundle.

In a PyInstaller bundle, bundled resources live under ``sys._MEIPASS``; in dev
they live next to the source modules. User-writable data (uploads, persisted
state, logs) always lives in the macOS standard locations, never inside the
read-only .app bundle.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_NAME = "MissionControl"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir(module_file: str) -> Path:
    """Directory holding a module's bundled resources (templates/static).

    Resolves relative to the module file so it is correct both in editable
    installs and in a frozen bundle (where the source tree is reproduced under
    ``sys._MEIPASS``).
    """
    return Path(module_file).resolve().parent


def user_data_dir() -> Path:
    """Writable per-user data dir (uploads, persisted state)."""
    return Path.home() / "Library" / "Application Support" / _APP_NAME


def logs_dir() -> Path:
    """Writable per-user logs dir."""
    return Path.home() / "Library" / "Logs" / _APP_NAME
