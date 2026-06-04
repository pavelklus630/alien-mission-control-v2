"""Tests for the Erebos Map service."""

import pytest
from fastapi.testclient import TestClient

from mission_control.config import Settings
from mission_control.services.map.app import create_app


@pytest.fixture
def map_client(tmp_path) -> TestClient:
    cache = tmp_path / "map_cache"
    # Minimal cache tree matching v1 layout.
    (cache / "assets").mkdir(parents=True)
    (cache / "fonts").mkdir(parents=True)
    (cache / "maps" / "erebos" / "bundle").mkdir(parents=True)
    (cache / "assets" / "engine.js").write_bytes(b"console.log('engine')" * 50)
    (cache / "fonts" / "VT323.woff2").write_bytes(b"woff2data" * 100)
    (cache / "maps" / "erebos" / "bundle" / "map-bundle.bin").write_bytes(bytes(range(256)) * 100)
    (cache / "ludicrpg.png").write_bytes(b"\x89PNG" + b"\x00" * 100)
    s = Settings(data_dir=tmp_path)
    return TestClient(create_app(s))


def test_control_and_display_pages_render(map_client):
    for path in ("/", "/control", "/display"):
        r = map_client.get(path)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert r.headers["cache-control"] == "no-store"


def test_initial_state(map_client):
    r = map_client.get("/api/state")
    assert r.status_code == 200
    assert r.json() == {"title_hidden": False, "menu_hidden": False}


def test_toggle_title(map_client):
    r = map_client.post("/api/toggle")
    assert r.json()["title_hidden"] is True
    r2 = map_client.post("/api/toggle")
    assert r2.json()["title_hidden"] is False


def test_toggle_menu(map_client):
    r = map_client.post("/api/toggle-menu")
    assert r.json()["menu_hidden"] is True


def test_erebos_descriptor(map_client):
    r = map_client.get("/api/maps/erebos")
    d = r.json()
    assert d["id"] == "erebos"
    assert "bundle" in d


def test_serve_cache_asset_full(map_client):
    r = map_client.get("/assets/engine.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert r.headers["accept-ranges"] == "bytes"


def test_serve_cache_binary_range(map_client):
    bundle = bytes(range(256)) * 100
    r = map_client.get("/maps/erebos/bundle/map-bundle.bin", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.content == bundle[:100]
    assert f"bytes 0-99/{len(bundle)}" in r.headers["content-range"]


def test_serve_cache_special_file(map_client):
    r = map_client.get("/ludicrpg.png")
    assert r.status_code == 200


def test_serve_cache_traversal_blocked(map_client):
    r = map_client.get("/assets/../../etc/passwd")
    assert r.status_code in (403, 404)


def test_serve_non_static_path_404(map_client):
    assert map_client.get("/something/random").status_code == 404
