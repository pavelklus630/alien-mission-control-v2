"""Typed configuration via pydantic-settings.

Replaces v1's magic numbers (ports, paths) scattered across service files.
Every value is overridable via environment variables (prefix ``MC_``) or a
``.env`` file, e.g. ``MC_PORT_SOUNDBOARD=9000`` or ``MC_AUDIO__BITRATE_KBPS=128``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import paths


class AudioSettings(BaseModel):
    """Audio encode targets. Bitrate is configurable, not hardcoded (v1 debt)."""

    bitrate_kbps: int = 96
    music_bitrate_kbps: int | None = 128
    target_lufs: float = -16.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MC_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Network — four distinct ports preserved from v1 (hard requirement).
    host: str = "0.0.0.0"
    port_soundboard: int = 8765
    port_terminal: int = 8770
    port_vibe: int = 8090
    port_map: int = 8085

    # Storage — writable user data (uploads, persisted state).
    data_dir: Path = Field(default_factory=paths.user_data_dir)

    # Soundboard: where the audio library lives. Defaults under data_dir; can be
    # pointed at the v1 library or a test fixture via MC_SOUNDS_DIR.
    sounds_dir: Path | None = None

    audio: AudioSettings = AudioSettings()

    # Extensibility flags — designed in, off by default (uploads & editors).
    enable_uploads: bool = False
    enable_editors: bool = False

    @property
    def resolved_sounds_dir(self) -> Path:
        return self.sounds_dir if self.sounds_dir is not None else self.data_dir / "sounds"


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton (cache cleared in tests via cache_clear)."""
    return Settings()
