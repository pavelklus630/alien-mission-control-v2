"""Typed content + command models for the Soundboard.

Exposing sounds as structured data (rather than v1's ad-hoc dicts) is the seam
that a future sound editor and audio uploads will build on.
"""

from __future__ import annotations

from pydantic import BaseModel


class Sound(BaseModel):
    """A single playable sound, addressed by its posix path under the sounds dir."""

    name: str
    path: str


class PlayEntry(BaseModel):
    """Per-sound playback state shared with the OBS output page."""

    loop: bool = False
    volume: float = 1.0
