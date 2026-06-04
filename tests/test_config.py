from pathlib import Path

from mission_control.config import Settings


def test_default_ports_match_v1():
    s = Settings()
    assert (s.port_soundboard, s.port_terminal, s.port_vibe, s.port_map) == (8765, 8770, 8090, 8085)


def test_audio_defaults_are_configurable():
    s = Settings()
    assert s.audio.bitrate_kbps == 96
    assert s.audio.target_lufs == -16.0


def test_env_override(monkeypatch):
    monkeypatch.setenv("MC_PORT_SOUNDBOARD", "9999")
    monkeypatch.setenv("MC_AUDIO__BITRATE_KBPS", "128")
    s = Settings()
    assert s.port_soundboard == 9999
    assert s.audio.bitrate_kbps == 128


def test_resolved_sounds_dir_defaults_under_data_dir(tmp_path):
    s = Settings(data_dir=tmp_path, sounds_dir=None)
    assert s.resolved_sounds_dir == tmp_path / "sounds"


def test_resolved_sounds_dir_explicit(tmp_path):
    explicit = tmp_path / "library"
    s = Settings(data_dir=tmp_path, sounds_dir=explicit)
    assert s.resolved_sounds_dir == explicit
