"""HTTP Range streaming, reused by Soundboard audio and (later) Map binaries.

v1 implemented Range only in the Soundboard and read whole map files into RAM
(``alien_map.py:516-536``). This single helper gives correct ``206`` / partial
responses and chunked streaming to any service that serves files.
"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

# Ensure .ogg resolves to audio/ogg regardless of the host's mime registry.
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/mp4", ".m4a")

_CHUNK = 64 * 1024
_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")


def range_response(
    path: Path,
    request: Request,
    *,
    content_type: str | None = None,
    chunk_size: int = _CHUNK,
) -> Response:
    """Return a full (200) or partial (206) streaming response for ``path``.

    Honors a single ``bytes=start-end`` Range header (what browsers send for
    audio seek/replay). Returns 404 if missing, 416 for an unsatisfiable range.
    """
    if not path.is_file():
        return Response(status_code=404)

    size = path.stat().st_size
    ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    start, end, status = 0, size - 1, 200
    raw = request.headers.get("range")
    if raw and (m := _RANGE_RE.match(raw.strip())):
        start = int(m.group(1))
        end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        status = 206

    if start > end or start >= size:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    length = end - start + 1

    def iterfile():
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(length)}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    return StreamingResponse(iterfile(), status_code=status, media_type=ctype, headers=headers)
