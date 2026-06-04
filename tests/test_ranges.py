"""Unit tests for core.ranges via a minimal app serving one temp file."""

from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from mission_control.core.ranges import range_response

PAYLOAD = bytes(range(256)) * 8  # 2048 bytes


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    f = tmp_path / "clip.ogg"
    f.write_bytes(PAYLOAD)
    app = FastAPI()

    @app.get("/file")
    async def serve(request: Request):
        return range_response(f, request)

    @app.get("/missing")
    async def missing(request: Request):
        return range_response(tmp_path / "nope.ogg", request)

    return TestClient(app)


def test_full_response_is_200_with_accept_ranges(client):
    r = client.get("/file")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == str(len(PAYLOAD))
    assert r.headers["content-type"] == "audio/ogg"
    assert r.content == PAYLOAD


def test_partial_response_is_206_with_content_range(client):
    r = client.get("/file", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-99/{len(PAYLOAD)}"
    assert r.headers["content-length"] == "100"
    assert r.content == PAYLOAD[:100]


def test_open_ended_range_runs_to_eof(client):
    start = len(PAYLOAD) - 10
    r = client.get("/file", headers={"Range": f"bytes={start}-"})
    assert r.status_code == 206
    assert r.content == PAYLOAD[start:]
    assert r.headers["content-range"] == f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}"


def test_unsatisfiable_range_is_416(client):
    r = client.get("/file", headers={"Range": f"bytes={len(PAYLOAD) + 5}-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(PAYLOAD)}"


def test_missing_file_is_404(client):
    assert client.get("/missing").status_code == 404
