"""Shared pytest fixtures.

Tests never bind a real port and never touch the user's real sound library —
a temporary sounds tree with small synthetic files is built per session.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mission_control.config import Settings
from mission_control.services.soundboard.app import create_app

# Deterministic byte payloads for Range tests (content need not be valid OGG;
# the Range machinery is byte-oriented).
_FILES: dict[str, bytes] = {
    "Weapons/Weap__PulseRifle1.ogg": bytes(range(256)) * 20,   # 5120 bytes
    "Weapons/Weap__Shotgun1.ogg": b"shotgun-" * 100,           # 800 bytes
    "Doors/Door 1.ogg": b"door" * 50,                          # 200 bytes
    "Music Cues/#Main_Theme.ogg": b"theme" * 64,               # 320 bytes
    ".hidden/ignore.ogg": b"nope",                             # hidden dir -> skipped
    "Weapons/readme.txt": b"not audio",                        # non-audio -> skipped
}


@pytest.fixture(scope="session")
def sounds_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("sounds")
    for rel, data in _FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


@pytest.fixture
def settings(sounds_root: Path, tmp_path: Path) -> Settings:
    return Settings(sounds_dir=sounds_root, data_dir=tmp_path)


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def pulse_rifle_bytes() -> bytes:
    return _FILES["Weapons/Weap__PulseRifle1.ogg"]
