"""Sound scanning helpers.

Ports v1's ``scan_sounds`` / ``clean_name`` (alien_soundboard.py:42-60) as a
pure ``scan_categories`` function. The live, cached, bank-aware library lives in
``bank_store.py`` (``BankStore``); this module is just the low-level scanner it
calls plus the shared constants.
"""

from __future__ import annotations

import re
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


def scan_categories(
    root: Path, category_order: list[str] | None = None
) -> dict[str, list[dict[str, str]]]:
    """Scan ``root`` into an ordered ``{category: [{name, path}, ...]}`` tree.

    ``category`` is the immediate parent folder name; files directly under
    ``root`` fall into ``"Other"``. Hidden files and files inside hidden dirs
    are skipped (v2 improvement over v1, which only checked the filename).
    Categories listed in ``category_order`` come first, then the rest sorted.
    """
    root = Path(root)
    if not root.is_dir():
        return {}
    order = category_order if category_order is not None else CATEGORY_ORDER
    categories: dict[str, list[dict[str, str]]] = {}
    for f in sorted(root.rglob("*")):
        if f.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        rel = f.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        cat = rel.parts[-2] if len(rel.parts) > 1 else "Other"
        categories.setdefault(cat, []).append(
            {"name": clean_name(f.stem), "path": str(rel).replace("\\", "/")}
        )
    ordered = {c: categories[c] for c in order if c in categories}
    for c in sorted(categories):
        ordered.setdefault(c, categories[c])
    return ordered
