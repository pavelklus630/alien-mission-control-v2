"""Structured logging: rotating file under ~/Library/Logs/MissionControl plus
stderr. Replaces v1's silenced ``log_message = lambda *_: None`` access logs.

The Tkinter launcher can attach its own handler (e.g. feeding an in-UI deque)
by calling ``logging.getLogger("mission_control")`` after ``configure()``.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from . import paths

_CONFIGURED = False
_FMT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def configure(level: int = logging.INFO, *, to_file: bool = True) -> logging.Logger:
    """Idempotently configure the ``mission_control`` logger tree."""
    global _CONFIGURED
    root = logging.getLogger("mission_control")
    if _CONFIGURED:
        return root

    root.setLevel(level)
    root.propagate = False

    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter(_FMT))
    root.addHandler(stream)

    if to_file:
        try:
            log_dir = paths.logs_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            fileh = RotatingFileHandler(
                log_dir / "mission_control.log",
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            fileh.setFormatter(logging.Formatter(_FMT))
            root.addHandler(fileh)
        except OSError:
            # Never let logging setup crash startup; stderr handler still works.
            root.warning("Could not open log file; continuing with stderr only.")

    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"mission_control.{name}")
