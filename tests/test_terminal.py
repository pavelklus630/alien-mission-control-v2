"""Tests for the MU/TH/UR Terminal service."""

import pytest
from fastapi.testclient import TestClient

from mission_control.config import Settings
from mission_control.services.terminal.app import create_app


@pytest.fixture
def terminal_client(tmp_path) -> TestClient:
    sounds = tmp_path / "terminal_sounds"
    sounds.mkdir()
    (sounds / "beep.ogg").write_bytes(b"beep" * 100)
    s = Settings(data_dir=tmp_path, terminal_sounds_dir=sounds)
    return TestClient(create_app(s))


def test_input_and_display_pages_render(terminal_client):
    for path in ("/", "/input", "/display"):
        r = terminal_client.get(path)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert r.headers["cache-control"] == "no-store"
        assert "<html" in r.text.lower()


def test_poll_empty_log(terminal_client):
    r = terminal_client.get("/poll?since=0")
    assert r.status_code == 200
    data = r.json()
    assert data["messages"] == []
    assert data["total"] == 0


def test_send_and_poll_cycle(terminal_client):
    terminal_client.post("/send", json={"text": "Alert: xenomorph detected", "type": "system"})
    terminal_client.post("/send", json={"text": "Acknowledged", "type": "user"})

    r = terminal_client.get("/poll?since=0")
    msgs = r.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["text"] == "Alert: xenomorph detected"
    assert msgs[0]["type"] == "system"

    # cursor — since=1 returns only the second message
    r2 = terminal_client.get("/poll?since=1")
    assert len(r2.json()["messages"]) == 1
    assert r2.json()["total"] == 2


def test_purge_clears_log(terminal_client):
    terminal_client.post("/send", json={"text": "message one"})
    terminal_client.post("/send", json={"_purge": True})
    msgs = terminal_client.get("/poll?since=0").json()["messages"]
    assert len(msgs) == 1
    assert "PURGED" in msgs[0]["text"]


def test_api_log_returns_structured_list(terminal_client):
    terminal_client.post("/send", json={"text": "hello"})
    data = terminal_client.get("/api/log").json()
    assert "messages" in data and "total" in data
    assert all("text" in m and "type" in m and "ts" in m for m in data["messages"])


def test_sound_file_served(terminal_client):
    r = terminal_client.get("/sounds/beep.ogg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/ogg"


def test_sound_traversal_blocked(terminal_client):
    assert terminal_client.get("/sounds/../../../etc/passwd").status_code in (403, 404)


def test_sound_non_ogg_blocked(terminal_client):
    assert terminal_client.get("/sounds/somefile.exe").status_code == 403
