"""Sound library: scans the audio directory into ordered categories.

Ports v1's ``scan_sounds`` / ``clean_name`` (alien_soundboard.py:42-60) but
caches the result instead of re-walking the filesystem on every request
(v1 debt 3.13). ``refresh()`` invalidates the cache — the hook a future upload
endpoint calls after storing a new file.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}

CATEGORY_ORDER = [
    "Music Cues",
    "Atmosphere & FX",
    "Doors",
    "Motion Sensor",
    "Weapons",
    "Xenomorph",
]


def clean_name(stem: str) -> str:
    n = stem.lstrip("#").strip().replace("_", " ")
    n = re.sub(r"-{2,}", " ", n)
    return re.sub(r"\s+", " ", n).strip(" -")


class SoundLibrary:
    def __init__(self, sounds_dir: Path):
        self.sounds_dir = Path(sounds_dir)
        self._lock = threading.Lock()
        self._cache: dict[str, list[dict[str, str]]] | None = None

    def refresh(self) -> None:
        with self._lock:
            self._cache = None

    def categories(self) -> dict[str, list[dict[str, str]]]:
        """Ordered ``{category: [{name, path}, ...]}`` — cached after first scan."""
        with self._lock:
            if self._cache is None:
                self._cache = self._scan()
            return self._cache

    def _scan(self) -> dict[str, list[dict[str, str]]]:
        if not self.sounds_dir.is_dir():
            return {}
        categories: dict[str, list[dict[str, str]]] = {}
        for f in sorted(self.sounds_dir.rglob("*")):
            if f.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            rel = f.relative_to(self.sounds_dir)
            # Skip any hidden file OR file inside a hidden dir (v2 improvement
            # over v1, which only checked the filename — a hidden dir leaked in
            # as a bogus category).
            if any(part.startswith(".") for part in rel.parts):
                continue
            cat = rel.parts[-2] if len(rel.parts) > 1 else "Other"
            categories.setdefault(cat, []).append(
                {"name": clean_name(f.stem), "path": str(rel).replace("\\", "/")}
            )
        ordered = {c: categories[c] for c in CATEGORY_ORDER if c in categories}
        for c in sorted(categories):
            ordered.setdefault(c, categories[c])
        return ordered
