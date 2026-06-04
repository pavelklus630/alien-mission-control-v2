"""Tests for the Vibe Generator service."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mission_control.config import Settings
from mission_control.services.vibe.app import create_app
from mission_control.services.vibe.models import SCENE_NAMES


@pytest.fixture
def vibe_client(tmp_path) -> TestClient:
    s = Settings(data_dir=tmp_path)
    return TestClient(create_app(s))


def test_control_and_display_pages_render(vibe_client):
    for path in ("/", "/control", "/control.html", "/display", "/display.html"):
        r = vibe_client.get(path)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert r.headers["cache-control"] == "no-store"


def test_initial_scene_is_zero(vibe_client):
    r = vibe_client.get("/api/scene")
    assert r.status_code == 200
    assert r.json() == {"scene": 0}


def test_set_scene_valid(vibe_client):
    r = vibe_client.post("/api/scene", json={"scene": 5})
    assert r.status_code == 200
    assert r.json()["scene"] == 5
    assert vibe_client.get("/api/scene").json()["scene"] == 5


def test_set_scene_invalid(vibe_client):
    r = vibe_client.post("/api/scene", json={"scene": 999})
    assert r.status_code == 400


def test_api_scenes_returns_all(vibe_client):
    scenes = vibe_client.get("/api/scenes").json()
    assert len(scenes) == len(SCENE_NAMES)
    assert scenes[0] == {"id": 0, "name": "CRIMSON VORTEX"}
    assert scenes[11] == {"id": 11, "name": "BLOOD ORBIT"}


def test_scene_persists_across_restart(tmp_path):
    s = Settings(data_dir=tmp_path)
    app1 = create_app(s)
    with TestClient(app1) as c:
        c.post("/api/scene", json={"scene": 7})

    # New app instance — should reload the persisted scene.
    app2 = create_app(s)
    with TestClient(app2) as c:
        assert c.get("/api/scene").json()["scene"] == 7


def test_sse_state_subscribe_broadcast_unsubscribe(tmp_path):
    """Unit test for the SSE fan-out mechanism inside VibeState directly.
    Tests the subscribe/broadcast/unsubscribe logic without opening an HTTP
    connection (which would block waiting for the stream to close).
    """
    import asyncio
    from mission_control.services.vibe.state import VibeState

    state = VibeState()

    async def _run():
        q = state.subscribe()
        state.set_scene(3)  # triggers _broadcast
        msg = await asyncio.wait_for(q.get(), timeout=1.0)
        assert b"data: " in msg
        assert b'"scene": 3' in msg or b'"scene":3' in msg
        state.unsubscribe(q)
        assert q not in state._subscribers

    asyncio.run(_run())
