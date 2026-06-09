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


def vendor_dir() -> Path:
    """Directory holding vendored binaries (ffmpeg/ffprobe).

    Frozen: bundled under ``sys._MEIPASS/ffmpeg``. Dev: ``<repo>/vendor/ffmpeg``
    (this file is ``<repo>/src/mission_control/paths.py``).
    """
    if is_frozen():
        return Path(sys._MEIPASS) / "ffmpeg"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2] / "vendor" / "ffmpeg"


def _tool_path(name: str) -> str | None:
    """Resolve a CLI tool: vendored/bundled copy first, then system PATH.

    A Finder-launched .app has a minimal PATH (no Homebrew), so the bundled
    copy is what makes the converter work in the shipped app; the PATH fallback
    is what makes it work in dev without vendoring.
    """
    cand = vendor_dir() / name
    if cand.exists():
        return str(cand)
    import shutil

    return shutil.which(name)


def ffmpeg_path() -> str | None:
    return _tool_path("ffmpeg")


def ffprobe_path() -> str | None:
    return _tool_path("ffprobe")


def user_data_dir() -> Path:
    """Writable per-user data dir (uploads, persisted state)."""
    return Path.home() / "Library" / "Application Support" / _APP_NAME


def logs_dir() -> Path:
    """Writable per-user logs dir."""
    return Path.home() / "Library" / "Logs" / _APP_NAME
