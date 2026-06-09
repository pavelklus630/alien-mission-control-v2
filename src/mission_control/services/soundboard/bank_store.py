"""Soundbank store — the live, bank-aware sound library.

A *soundbank* is a named, self-contained set of categorised sounds (one per
scenario, e.g. "Heart of Darkness"). Exactly one bank is *active* at a time;
the active bank is what ``/sounds.json``, ``/api/sounds`` and ``/audio`` serve.

Layout (mirrors the vibe scene store's builtin-vs-custom shadowing):

    <bundle>/soundboard/sounds/                 ← builtin bank (read-only)
    data_dir/soundboard/active_bank.json        ← { "active": "<id>" }
    data_dir/soundboard/banks/<id>/bank.json    ← custom bank manifest
    data_dir/soundboard/banks/<id>/<Cat>/*.ogg  ← custom bank audio

A custom bank whose id equals the builtin's *shadows* it (user edits win).
The builtin bank has no manifest file — it is synthesised by scanning the
shipped sounds dir, so the existing ``/sounds.json`` contract is unchanged when
the builtin bank is active.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ...config import Settings
from .repository import AUDIO_EXTENSIONS, CATEGORY_ORDER, scan_categories

BUILTIN_BANK_ID = "heart_of_darkness"
BUILTIN_BANK_NAME = "HEART OF DARKNESS"

_BANKS_SUBDIR = Path("soundboard") / "banks"
_ACTIVE_FILE = Path("soundboard") / "active_bank.json"


def _slugify(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip()
    return safe.lower().replace(" ", "_") or "bank"


class BankStore:
    """Active-bank-aware sound library. Drop-in for the old ``SoundLibrary``:
    exposes ``categories()`` and ``refresh()`` plus the bank-management API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._builtin_root = settings.resolved_sounds_dir
        self._banks_dir = settings.data_dir / _BANKS_SUBDIR
        self._active_file = settings.data_dir / _ACTIVE_FILE
        self._banks_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: dict[str, list[dict[str, str]]] | None = None
        self._active: str = self._load_active()

    # ── active bank ──────────────────────────────────────────────────────────

    def _load_active(self) -> str:
        try:
            data = json.loads(self._active_file.read_text(encoding="utf-8"))
            active = str(data.get("active", BUILTIN_BANK_ID))
        except (OSError, ValueError):
            active = BUILTIN_BANK_ID
        return active if self._exists(active) else BUILTIN_BANK_ID

    def _save_active(self) -> None:
        try:
            self._active_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._active_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({"active": self._active}), encoding="utf-8")
            tmp.replace(self._active_file)
        except OSError:
            pass

    def active_id(self) -> str:
        with self._lock:
            return self._active

    def set_active(self, bank_id: str) -> bool:
        """Switch the active bank. Returns False if the id is unknown."""
        if not self._exists(bank_id):
            return False
        with self._lock:
            self._active = bank_id
            self._cache = None
        self._save_active()
        return True

    # ── paths ────────────────────────────────────────────────────────────────

    def _custom_dir(self, bank_id: str) -> Path:
        return self._banks_dir / _slugify(bank_id)

    def root_for(self, bank_id: str) -> Path:
        """Filesystem root that holds a bank's audio files."""
        custom = self._custom_dir(bank_id)
        if custom.is_dir():
            return custom
        if bank_id == BUILTIN_BANK_ID:
            return self._builtin_root
        return custom

    def active_root(self) -> Path:
        return self.root_for(self.active_id())

    def _exists(self, bank_id: str) -> bool:
        return bank_id == BUILTIN_BANK_ID or self._custom_dir(bank_id).is_dir()

    # ── bank listing / manifest ────────────────────────────────────────────────

    def _read_manifest(self, bank_id: str) -> dict[str, Any] | None:
        mf = self._custom_dir(bank_id) / "bank.json"
        try:
            return json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list_banks(self) -> list[dict[str, Any]]:
        """Summaries: builtin first (or its custom shadow), then custom-only banks."""
        active = self.active_id()
        builtin_shadowed = (self._custom_dir(BUILTIN_BANK_ID)).is_dir()
        summaries: list[dict[str, Any]] = [
            {
                "id": BUILTIN_BANK_ID,
                "name": (self._read_manifest(BUILTIN_BANK_ID) or {}).get("name", BUILTIN_BANK_NAME)
                if builtin_shadowed else BUILTIN_BANK_NAME,
                "builtin": not builtin_shadowed,
                "active": active == BUILTIN_BANK_ID,
            }
        ]
        for d in sorted(self._banks_dir.glob("*")):
            if not d.is_dir() or d.name == _slugify(BUILTIN_BANK_ID):
                continue
            mf = self._read_manifest(d.name) or {}
            bid = mf.get("id", d.name)
            summaries.append({
                "id": bid,
                "name": mf.get("name", bid),
                "builtin": False,
                "active": active == bid,
            })
        return summaries

    def get_bank(self, bank_id: str) -> dict[str, Any]:
        """Full manifest for a bank (synthesised for the unshadowed builtin)."""
        mf = self._read_manifest(bank_id)
        if mf is not None:
            return mf
        if bank_id == BUILTIN_BANK_ID:
            tree = scan_categories(self._builtin_root, CATEGORY_ORDER)
            sounds = [
                {"path": s["path"], "name": s["name"], "category": cat}
                for cat, items in tree.items() for s in items
            ]
            return {
                "id": BUILTIN_BANK_ID,
                "name": BUILTIN_BANK_NAME,
                "description": "Shipped sound library.",
                "category_order": list(tree.keys()),
                "sounds": sounds,
                "builtin": True,
            }
        raise KeyError(bank_id)

    # ── category tree (the /sounds.json contract) ───────────────────────────────

    def _categories_for(self, bank_id: str) -> dict[str, list[dict[str, str]]]:
        mf = self._read_manifest(bank_id)
        if mf is None and bank_id == BUILTIN_BANK_ID:
            return scan_categories(self._builtin_root, CATEGORY_ORDER)
        if mf is None:
            return {}
        # Build the tree from the manifest's sound list, honouring category_order.
        order = mf.get("category_order") or CATEGORY_ORDER
        grouped: dict[str, list[dict[str, str]]] = {}
        for s in mf.get("sounds", []):
            cat = s.get("category", "Other")
            grouped.setdefault(cat, []).append(
                {"name": s.get("name", ""), "path": s.get("path", "")}
            )
        ordered = {c: grouped[c] for c in order if c in grouped}
        for c in sorted(grouped):
            ordered.setdefault(c, grouped[c])
        return ordered

    def categories(self) -> dict[str, list[dict[str, str]]]:
        """Ordered ``{category: [{name, path}, ...]}`` for the active bank — cached."""
        with self._lock:
            if self._cache is None:
                self._cache = self._categories_for(self._active)
            return self._cache

    def refresh(self) -> None:
        with self._lock:
            self._cache = None

    # ── write: fork builtin (copy-on-write) + add converted sounds ───────────────

    def _write_manifest(self, bank_id: str, manifest: dict[str, Any]) -> None:
        d = self._custom_dir(bank_id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "bank.json.tmp"
        tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(d / "bank.json")

    def ensure_writable(self, bank_id: str) -> str:
        """Return an editable custom bank id, forking the builtin if needed.

        Editing the builtin is copy-on-write: its audio files are copied into a
        custom bank that shadows it, so activating the shadow keeps every sound.
        """
        if self._custom_dir(bank_id).is_dir():
            return bank_id
        if bank_id == BUILTIN_BANK_ID:
            import shutil

            d = self._custom_dir(bank_id)
            d.mkdir(parents=True, exist_ok=True)
            if self._builtin_root.is_dir():
                for f in self._builtin_root.rglob("*"):
                    rel = f.relative_to(self._builtin_root)
                    if (
                        f.is_file()
                        and f.suffix.lower() in AUDIO_EXTENSIONS
                        and not any(p.startswith(".") for p in rel.parts)
                    ):
                        dest = d / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, dest)
            manifest = self.get_bank(BUILTIN_BANK_ID)
            manifest["builtin"] = False
            self._write_manifest(bank_id, manifest)
            self.refresh()
            return bank_id
        raise KeyError(bank_id)

    def _unique_slug(self, cat_dir: Path, name: str) -> str:
        base = _slugify(name)
        slug = base
        n = 2
        while (cat_dir / f"{slug}.ogg").exists():
            slug = f"{base}_{n}"
            n += 1
        return slug

    def add_sound(
        self,
        bank_id: str,
        category: str,
        name: str,
        ogg_bytes: bytes,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """Write a converted .ogg into a (custom) bank and register it. Returns its rel path."""
        bank_id = self.ensure_writable(bank_id)
        d = self._custom_dir(bank_id)
        cat_dir = d / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        slug = self._unique_slug(cat_dir, name)
        rel = f"{category}/{slug}.ogg"
        (d / rel).write_bytes(ogg_bytes)

        manifest = self._read_manifest(bank_id) or {
            "id": bank_id, "name": bank_id, "description": "",
            "category_order": list(CATEGORY_ORDER), "sounds": [],
        }
        entry: dict[str, Any] = {"path": rel, "name": name, "category": category}
        if meta:
            entry.update(meta)
        manifest.setdefault("sounds", []).append(entry)
        order = manifest.setdefault("category_order", list(CATEGORY_ORDER))
        if category not in order:
            order.append(category)
        self._write_manifest(bank_id, manifest)
        self.refresh()
        return rel

    # ── edit: sound metadata / removal / bank meta ──────────────────────────────

    _EDITABLE_SOUND_KEYS = {"name", "category", "volume", "loop", "kind", "fade_in", "fade_out"}

    def update_sound(self, bank_id: str, path: str, changes: dict[str, Any]) -> None:
        """Patch a sound's metadata in a (custom) bank. Category change only
        re-tags it — the file is not moved, since grouping follows the manifest."""
        bank_id = self.ensure_writable(bank_id)
        manifest = self._read_manifest(bank_id) or {}
        for s in manifest.get("sounds", []):
            if s.get("path") == path:
                for k, v in changes.items():
                    if k in self._EDITABLE_SOUND_KEYS:
                        s[k] = v
                cat = s.get("category")
                order = manifest.setdefault("category_order", list(CATEGORY_ORDER))
                if cat and cat not in order:
                    order.append(cat)
                self._write_manifest(bank_id, manifest)
                self.refresh()
                return
        raise KeyError(path)

    def remove_sound(self, bank_id: str, path: str) -> None:
        bank_id = self.ensure_writable(bank_id)
        manifest = self._read_manifest(bank_id) or {}
        sounds = manifest.get("sounds", [])
        kept = [s for s in sounds if s.get("path") != path]
        if len(kept) == len(sounds):
            raise KeyError(path)
        manifest["sounds"] = kept
        self._write_manifest(bank_id, manifest)
        try:
            (self._custom_dir(bank_id) / path).unlink()
        except OSError:
            pass
        self.refresh()

    def update_bank(self, bank_id: str, changes: dict[str, Any]) -> None:
        """Patch bank-level metadata (name / description / category_order)."""
        bank_id = self.ensure_writable(bank_id)
        manifest = self._read_manifest(bank_id) or {}
        for k in ("name", "description", "category_order"):
            if k in changes:
                manifest[k] = changes[k]
        self._write_manifest(bank_id, manifest)
        self.refresh()

    def bank_file(self, bank_id: str, path: str) -> Path:
        """Resolve a file inside a bank for read-only preview (no fork)."""
        from ...core.uploads import safe_join

        return safe_join(self.root_for(bank_id), path)

    def write_sound_bytes(
        self, bank_id: str, path: str, ogg_bytes: bytes, meta: dict[str, Any] | None = None
    ) -> None:
        """Overwrite an existing sound's audio (e.g. re-normalised) + patch its meta."""
        from ...core.uploads import safe_join

        bank_id = self.ensure_writable(bank_id)
        dest = safe_join(self._custom_dir(bank_id), path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(ogg_bytes)
        if meta:
            try:
                self.update_sound(bank_id, path, meta)
            except KeyError:
                pass
        self.refresh()

    def import_bank(self, manifest: dict[str, Any], files: dict[str, bytes]) -> str:
        """Create a new custom bank from an imported manifest + its audio files."""
        from ...core.uploads import safe_join

        name = str(manifest.get("name") or "Imported Bank")
        bank_id = self.create_bank(name, str(manifest.get("description", "")))
        d = self._custom_dir(bank_id)
        for rel, data in files.items():
            dest = safe_join(d, rel)  # zip-slip protection
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        m = dict(manifest)
        m["id"] = bank_id
        m["name"] = name
        m.pop("builtin", None)
        self._write_manifest(bank_id, m)
        self.refresh()
        return bank_id

    # ── create / delete (foundation for the editor) ─────────────────────────────

    def create_bank(self, name: str, description: str = "") -> str:
        """Create an empty custom bank, returning its id."""
        base = _slugify(name)
        bank_id = base
        n = 2
        while self._custom_dir(bank_id).is_dir() or bank_id == BUILTIN_BANK_ID:
            bank_id = f"{base}_{n}"
            n += 1
        d = self._custom_dir(bank_id)
        d.mkdir(parents=True, exist_ok=True)
        manifest = {
            "id": bank_id,
            "name": name,
            "description": description,
            "category_order": list(CATEGORY_ORDER),
            "sounds": [],
        }
        (d / "bank.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return bank_id

    def delete_bank(self, bank_id: str) -> None:
        """Delete a custom bank. The builtin cannot be deleted (only shadowed)."""
        if bank_id == BUILTIN_BANK_ID and not self._custom_dir(BUILTIN_BANK_ID).is_dir():
            raise ValueError("cannot delete the builtin bank")
        d = self._custom_dir(bank_id)
        if not d.is_dir():
            raise KeyError(bank_id)
        import shutil
        shutil.rmtree(d)
        if self.active_id() == bank_id:
            self.set_active(BUILTIN_BANK_ID)
        self.refresh()
