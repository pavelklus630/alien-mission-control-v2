"""Scene store — load, save, list, and delete JSON vibe scenes.

Builtin scenes live in services/vibe/scenes/builtin/ (package data, read-only source).
Custom scenes live in settings.data_dir / vibe / scenes/ (read-write).

A custom scene with the same ID as a builtin *shadows* the builtin — get() and
list_all() will return the custom version. This lets users edit any scene and
save their changes without touching the shipped files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_BUILTIN_DIR = Path(__file__).resolve().parent / "scenes" / "builtin"
_CUSTOM_SUBDIR = Path("vibe") / "scenes"


class SceneNotFound(KeyError):
    """Raised when a requested scene ID does not exist."""


class SceneStore:
    def __init__(self, data_dir: Path) -> None:
        self._custom_dir = data_dir / _CUSTOM_SUBDIR
        self._custom_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers

    def _builtin_path(self, scene_id: str) -> Path | None:
        for p in sorted(_BUILTIN_DIR.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("id") == scene_id:
                return p
        return None

    def _custom_path(self, scene_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in scene_id)
        return self._custom_dir / f"{safe_id}.json"

    # ------------------------------------------------------------------
    # Public API

    def list_all(self) -> list[dict[str, Any]]:
        """Return summary dicts — builtins in their original order, custom shadows
        replace their builtin counterpart in-place, new custom-only scenes appended."""
        # Index all custom scenes first.
        custom_by_id: dict[str, dict] = {}
        for p in sorted(self._custom_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            sid = data.get("id", p.stem)
            custom_by_id[sid] = {
                "id":      sid,
                "name":    data.get("name", sid),
                "class":   data.get("class", ""),
                "sym":     data.get("sym", ""),
                "builtin": False,
            }

        summaries: list[dict[str, Any]] = []
        builtin_ids: set[str] = set()

        # Builtins in their 00_-11_ file order; substitute custom shadow when present.
        for p in sorted(_BUILTIN_DIR.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            sid = data.get("id", p.stem)
            builtin_ids.add(sid)
            if sid in custom_by_id:
                summaries.append(custom_by_id[sid])
            else:
                summaries.append({
                    "id":      sid,
                    "name":    data.get("name", sid),
                    "class":   data.get("class", ""),
                    "sym":     data.get("sym", ""),
                    "builtin": True,
                })

        # Append custom scenes that don't shadow any builtin.
        for sid, info in custom_by_id.items():
            if sid not in builtin_ids:
                summaries.append(info)

        return summaries

    def get(self, scene_id: str) -> dict[str, Any]:
        """Return full scene dict. Custom copy takes precedence over builtin."""
        # Custom first — lets edited builtins take precedence.
        cp = self._custom_path(scene_id)
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))
        bp = self._builtin_path(scene_id)
        if bp is not None:
            return json.loads(bp.read_text(encoding="utf-8"))
        raise SceneNotFound(scene_id)

    def save(self, scene: dict[str, Any]) -> None:
        """Persist a scene to the custom directory.

        Builtins are never modified — saving a scene with a builtin ID creates a
        custom copy that shadows the builtin (user's edits win).
        """
        scene_id = scene.get("id", "")
        if not scene_id:
            raise ValueError("Scene must have an 'id' field.")
        path = self._custom_path(scene_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(scene, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def delete(self, scene_id: str) -> None:
        """Delete the custom copy of a scene. Raises SceneNotFound if no custom copy."""
        cp = self._custom_path(scene_id)
        if not cp.exists():
            raise SceneNotFound(scene_id)
        cp.unlink()
