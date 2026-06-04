"""Upload validation + path-safe storage.

These are the seam for the planned upload features (user audio, user maps).
They are real and tested now; the upload *routes* stay gated behind
``settings.enable_uploads`` until the editors land.
"""

from __future__ import annotations

from pathlib import Path


class UploadError(ValueError):
    """Raised when an upload fails validation (mapped to HTTP 400 by routes)."""


def safe_join(base: Path, untrusted_relpath: str) -> Path:
    """Join ``untrusted_relpath`` onto ``base``, rejecting path traversal.

    Mirrors the explicit guard v1 used on the Soundboard/Map services
    (resolve + relative_to) rather than v1 Terminal's ``.name`` trick.
    """
    base = base.resolve()
    candidate = (base / untrusted_relpath).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise UploadError(f"Path escapes base directory: {untrusted_relpath!r}") from exc
    return candidate


def validate_upload(
    *,
    filename: str,
    size: int,
    content_type: str | None,
    allowed_extensions: set[str],
    allowed_content_types: set[str] | None = None,
    max_bytes: int,
) -> None:
    """Validate a single uploaded file. Raises :class:`UploadError` on failure."""
    if not filename or filename in {".", ".."}:
        raise UploadError("Missing or invalid filename.")

    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        raise UploadError(f"Extension {ext!r} not allowed (expected one of {sorted(allowed_extensions)}).")

    if size <= 0:
        raise UploadError("Empty upload.")
    if size > max_bytes:
        raise UploadError(f"File too large: {size} bytes > limit {max_bytes}.")

    if allowed_content_types is not None and content_type is not None:
        if content_type.split(";")[0].strip().lower() not in allowed_content_types:
            raise UploadError(f"Content-Type {content_type!r} not allowed.")
