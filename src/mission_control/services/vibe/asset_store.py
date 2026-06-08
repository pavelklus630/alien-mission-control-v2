"""Asset store — upload, list, serve, and delete image assets for the vibe editor."""

from __future__ import annotations

from pathlib import Path

from ...core.uploads import UploadError, safe_join, validate_upload

_ASSET_SUBDIR = Path("vibe") / "assets"

_ALLOWED_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_ALLOWED_CONTENT_TYPES: set[str] = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


class AssetStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / _ASSET_SUBDIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_assets(self) -> list[dict]:
        return [
            {"filename": p.name, "size": p.stat().st_size}
            for p in sorted(self._dir.iterdir())
            if p.is_file() and p.suffix.lower() in _ALLOWED_EXTENSIONS
        ]

    def save(self, filename: str, data: bytes, content_type: str | None = None) -> Path:
        validate_upload(
            filename=filename,
            size=len(data),
            content_type=content_type,
            allowed_extensions=_ALLOWED_EXTENSIONS,
            allowed_content_types=_ALLOWED_CONTENT_TYPES,
            max_bytes=_MAX_BYTES,
        )
        dest = safe_join(self._dir, filename)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return dest

    def path_for(self, filename: str) -> Path:
        p = safe_join(self._dir, filename)
        if not p.exists():
            raise FileNotFoundError(filename)
        return p

    def delete(self, filename: str) -> None:
        p = safe_join(self._dir, filename)
        if not p.exists():
            raise FileNotFoundError(filename)
        p.unlink()
