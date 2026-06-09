"""Audio ingest — transcode + loudness-normalise uploads to a uniform format.

Every uploaded sound is converted to **Opus in .ogg** and loudness-normalised
to the project target (−16 LUFS integrated, −1.5 dBTP true peak) so the whole
board plays at a consistent level. Wraps the bundled ``ffmpeg``/``ffprobe``
(see ``paths.ffmpeg_path``); raises :class:`ConverterUnavailable` if neither the
bundled nor a system binary is found.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from ... import paths
from ...config import Settings

# Formats we accept for upload (ffmpeg decodes far more, but keep the surface tight).
INPUT_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".aif", ".aiff"}

_FFMPEG_TIMEOUT = 120  # seconds per file


class ConverterUnavailable(RuntimeError):
    """ffmpeg/ffprobe could not be located (bundled or on PATH)."""


class ConversionError(RuntimeError):
    """ffmpeg failed to convert a file."""


def converter_available() -> bool:
    return paths.ffmpeg_path() is not None


def _require_ffmpeg() -> str:
    ff = paths.ffmpeg_path()
    if ff is None:
        raise ConverterUnavailable(
            "ffmpeg not found. In dev install it (brew install ffmpeg); "
            "the shipped app bundles it."
        )
    return ff


def _bitrate_kbps(kind: str, settings: Settings) -> int:
    if kind == "music" and settings.audio.music_bitrate_kbps:
        return settings.audio.music_bitrate_kbps
    return settings.audio.bitrate_kbps


def convert_and_normalize(
    data: bytes, filename: str, kind: str, settings: Settings
) -> tuple[bytes, float | None, float | None]:
    """Convert ``data`` to normalised Opus/.ogg.

    Returns ``(ogg_bytes, measured_lufs, measured_peak_db)``. The measured
    values describe the *output* file (best-effort; ``None`` if analysis fails).
    """
    ff = _require_ffmpeg()
    target = settings.audio.target_lufs
    bitrate = _bitrate_kbps(kind, settings)
    suffix = Path(filename).suffix.lower() or ".bin"

    with tempfile.TemporaryDirectory(prefix="mc_ingest_") as td:
        src = Path(td) / f"in{suffix}"
        dst = Path(td) / "out.ogg"
        src.write_bytes(data)
        loudnorm = f"loudnorm=I={target}:TP=-1.5:LRA=11"
        cmd = [
            ff, "-y", "-hide_banner", "-nostdin",
            "-i", str(src),
            "-af", loudnorm,
            "-c:a", "libopus", "-b:a", f"{bitrate}k", "-vbr", "on",
            "-vn",  # drop any cover-art video stream
            str(dst),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=_FFMPEG_TIMEOUT)
        if proc.returncode != 0 or not dst.exists():
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
            raise ConversionError(" / ".join(tail) or "ffmpeg failed")
        ogg = dst.read_bytes()

    lufs, peak = analyze_loudness(ogg)
    return ogg, lufs, peak


def analyze_loudness(data: bytes) -> tuple[float | None, float | None]:
    """Measure integrated loudness (LUFS) and true peak (dBTP) of ``data``.

    Best-effort: returns ``(None, None)`` if ffmpeg is unavailable or parsing
    fails. Uses loudnorm's JSON analysis pass.
    """
    ff = paths.ffmpeg_path()
    if ff is None:
        return None, None
    with tempfile.TemporaryDirectory(prefix="mc_analyze_") as td:
        src = Path(td) / "a.ogg"
        src.write_bytes(data)
        cmd = [
            ff, "-hide_banner", "-nostdin", "-i", str(src),
            "-af", "loudnorm=print_format=json", "-f", "null", "-",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=_FFMPEG_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired):
            return None, None
    stderr = proc.stderr.decode("utf-8", "replace")
    # loudnorm prints a JSON object near the end of stderr.
    matches = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.DOTALL)
    if not matches:
        return None, None
    try:
        info = json.loads(matches[-1])
        lufs = float(info.get("input_i"))
        peak = float(info.get("input_tp"))
        return lufs, peak
    except (ValueError, TypeError):
        return None, None
