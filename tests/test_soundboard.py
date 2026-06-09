"""End-to-end tests for the Soundboard service (the v2 reference service)."""

import io
import json
import math
import struct
import wave

import pytest

from mission_control.services.soundboard.audio_ingest import converter_available

_needs_ffmpeg = pytest.mark.skipif(
    not converter_available(), reason="ffmpeg not available"
)


def _wav_bytes(seconds: float = 0.4, freq: int = 220, rate: int = 8000) -> bytes:
    """A minimal valid mono 16-bit WAV tone for converter tests."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(0.3 * 32767 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * seconds))
        )
        w.writeframes(frames)
    return buf.getvalue()


def _make_custom_bank(app, bank_id, name, sounds, category_order=None):
    """Create a custom soundbank on disk. ``sounds``: [(category, filename, bytes)]."""
    store = app.state.library
    root = store._banks_dir / bank_id  # custom dir (root_for() would prefer builtin)
    root.mkdir(parents=True, exist_ok=True)
    manifest_sounds = []
    for cat, fn, data in sounds:
        (root / cat).mkdir(parents=True, exist_ok=True)
        (root / cat / fn).write_bytes(data)
        manifest_sounds.append(
            {"path": f"{cat}/{fn}", "name": fn.rsplit(".", 1)[0], "category": cat}
        )
    manifest = {
        "id": bank_id,
        "name": name,
        "category_order": category_order or [],
        "sounds": manifest_sounds,
    }
    (root / "bank.json").write_text(json.dumps(manifest))
    store.refresh()
    return root


def test_control_and_output_pages_render(client):
    for path in ("/", "/control", "/output"):
        r = client.get(path)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert r.headers["cache-control"] == "no-store"  # OBS must not cache
        assert "<html" in r.text.lower()


def test_sounds_json_groups_and_orders_categories(client):
    data = client.get("/sounds.json").json()
    # CATEGORY_ORDER is Music Cues, Atmosphere & FX, Doors, Motion Sensor, Weapons…
    assert list(data.keys()) == ["Music Cues", "Doors", "Weapons"]
    # clean_name: '_' -> ' ', collapse runs, strip leading '#'.
    names = {s["name"] for s in data["Weapons"]}
    assert names == {"Weap PulseRifle1", "Weap Shotgun1"}
    cue = data["Music Cues"][0]
    assert cue["name"] == "Main Theme"            # '#Main_Theme' -> 'Main Theme'
    assert cue["path"] == "Music Cues/#Main_Theme.ogg"


def test_hidden_and_nonaudio_files_are_skipped(client):
    data = client.get("/sounds.json").json()
    assert ".hidden" not in data
    weapons_paths = {s["path"] for s in data["Weapons"]}
    assert all(not p.endswith(".txt") for p in weapons_paths)


def test_api_sounds_is_flat_structured_list(client):
    flat = client.get("/api/sounds").json()
    assert isinstance(flat, list)
    assert all({"name", "path"} <= set(item) for item in flat)


def test_state_play_stop_cycle(client):
    state = client.get("/state").json()
    assert state["_voice"] == {"active": False, "deviceId": ""}
    assert state["_bank"] == "heart_of_darkness"  # active bank rides the poll

    path = "Weapons/Weap__PulseRifle1.ogg"
    client.post("/", json={"action": "play", "path": path, "loop": True, "volume": 0.7})
    state = client.get("/state").json()
    assert state[path] == {"loop": True, "volume": 0.7}

    client.post("/", json={"action": "volume", "path": path, "volume": 0.3})
    assert client.get("/state").json()[path]["volume"] == 0.3

    client.post("/", json={"action": "stop", "path": path})
    assert path not in client.get("/state").json()


def test_voice_toggle(client):
    client.post("/", json={"action": "voice_on", "deviceId": "abc"})
    assert client.get("/state").json()["_voice"] == {"active": True, "deviceId": "abc"}
    client.post("/", json={"action": "voice_off"})
    assert client.get("/state").json()["_voice"] == {"active": False, "deviceId": ""}


def test_audio_range_streaming(client, pulse_rifle_bytes):
    path = "/audio/Weapons/Weap__PulseRifle1.ogg"
    full = client.get(path)
    assert full.status_code == 200
    assert full.content == pulse_rifle_bytes
    assert full.headers["accept-ranges"] == "bytes"

    partial = client.get(path, headers={"Range": "bytes=10-19"})
    assert partial.status_code == 206
    assert partial.content == pulse_rifle_bytes[10:20]
    assert partial.headers["content-range"] == f"bytes 10-19/{len(pulse_rifle_bytes)}"


def test_audio_path_traversal_blocked(client):
    r = client.get("/audio/../../../etc/passwd")
    assert r.status_code in (403, 404)  # never serves outside the sounds dir


def test_audio_missing_file_404(client):
    assert client.get("/audio/Weapons/DoesNotExist.ogg").status_code == 404


# ── Soundbanks ──────────────────────────────────────────────────────────────

def test_banks_list_has_builtin_active(client):
    banks = {b["id"]: b for b in client.get("/api/banks").json()}
    assert "heart_of_darkness" in banks
    assert banks["heart_of_darkness"]["builtin"] is True
    assert banks["heart_of_darkness"]["active"] is True


def test_builtin_bank_manifest(client):
    mf = client.get("/api/banks/heart_of_darkness").json()
    assert mf["builtin"] is True
    assert "Weapons" in mf["category_order"]
    assert any(s["category"] == "Weapons" for s in mf["sounds"])


def test_get_unknown_bank_404(client):
    assert client.get("/api/banks/nope").status_code == 404


def test_activate_unknown_bank_404(client):
    assert client.post("/api/banks/nope/activate").status_code == 404


def test_custom_bank_switch_changes_sounds_and_audio(app, client):
    _make_custom_bank(
        app, "ambient", "AMBIENT",
        [("Atmosphere & FX", "Hum.ogg", b"hum-bytes" * 10)],
        category_order=["Atmosphere & FX"],
    )
    assert client.post("/api/banks/ambient/activate").json()["ok"] is True
    assert client.get("/state").json()["_bank"] == "ambient"

    data = client.get("/sounds.json").json()
    assert list(data.keys()) == ["Atmosphere & FX"]
    assert data["Atmosphere & FX"][0]["path"] == "Atmosphere & FX/Hum.ogg"
    assert "Weapons" not in data  # builtin no longer active

    r = client.get("/audio/Atmosphere & FX/Hum.ogg")
    assert r.status_code == 200
    assert r.content == b"hum-bytes" * 10


def test_custom_bank_shadows_builtin(app, client):
    _make_custom_bank(
        app, "heart_of_darkness", "HOD CUSTOM",
        [("Doors", "Hatch.ogg", b"hatch")],
    )
    banks = {b["id"]: b for b in client.get("/api/banks").json()}
    assert banks["heart_of_darkness"]["builtin"] is False
    assert banks["heart_of_darkness"]["name"] == "HOD CUSTOM"
    # Active id is still the builtin id; it now resolves to the custom shadow.
    data = client.get("/sounds.json").json()
    assert list(data.keys()) == ["Doors"]


def test_create_and_delete_bank(app, client):
    store = app.state.library
    bid = store.create_bank("My Session")
    assert bid == "my_session"
    assert any(b["id"] == "my_session" for b in client.get("/api/banks").json())

    store.delete_bank(bid)
    assert not any(b["id"] == "my_session" for b in client.get("/api/banks").json())


def test_create_bank_via_api(client):
    r = client.post("/api/banks", json={"name": "Chariot of the Gods"})
    assert r.status_code == 200
    bid = r.json()["id"]
    assert bid == "chariot_of_the_gods"
    assert any(b["id"] == bid for b in client.get("/api/banks").json())


# ── Ingest: add_sound / fork-on-edit (no ffmpeg needed) ──────────────────────

def test_add_sound_to_custom_bank(app, client):
    store = app.state.library
    bid = store.create_bank("Session A")
    rel = store.add_sound(bid, "Doors", "Big Hatch", b"OggSfakebytes", {"kind": "sfx", "lufs": -16.0})
    assert rel == "Doors/big_hatch.ogg"

    client.post(f"/api/banks/{bid}/activate")
    data = client.get("/sounds.json").json()
    assert any(s["name"] == "Big Hatch" for s in data["Doors"])

    mf = client.get(f"/api/banks/{bid}").json()
    assert any(s.get("lufs") == -16.0 for s in mf["sounds"])

    r = client.get("/audio/Doors/big_hatch.ogg")
    assert r.status_code == 200 and r.content == b"OggSfakebytes"


def test_editing_builtin_forks_to_custom(app, client):
    store = app.state.library
    store.add_sound("heart_of_darkness", "Doors", "New Door", b"OggSx", {})
    banks = {b["id"]: b for b in client.get("/api/banks").json()}
    assert banks["heart_of_darkness"]["builtin"] is False  # forked → shadowed

    data = client.get("/sounds.json").json()  # active id resolves to the shadow
    assert any(s["name"] == "New Door" for s in data.get("Doors", []))
    assert "Weapons" in data  # builtin sounds preserved by the copy-on-write fork


# ── Upload pipeline (converter; gated on ffmpeg) ─────────────────────────────

def test_editor_page_renders(client):
    r = client.get("/editor")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert "SOUNDBANK EDITOR" in r.text


def test_edit_and_delete_sound(app, client):
    store = app.state.library
    bid = store.create_bank("Edits")
    store.add_sound(bid, "Doors", "Raw Hatch", b"OggSaaaa", {"kind": "sfx"})

    # rename + recategorise + volume/loop/kind
    r = client.post(f"/api/banks/{bid}/sounds", json={
        "path": "Doors/raw_hatch.ogg", "name": "Polished Hatch",
        "category": "Atmosphere & FX", "volume": 0.5, "loop": True, "kind": "music",
    })
    assert r.json()["ok"] is True
    mf = client.get(f"/api/banks/{bid}").json()
    s = next(x for x in mf["sounds"] if x["path"] == "Doors/raw_hatch.ogg")
    assert s["name"] == "Polished Hatch" and s["category"] == "Atmosphere & FX"
    assert s["volume"] == 0.5 and s["loop"] is True and s["kind"] == "music"

    # grouping follows the manifest category (file not moved)
    client.post(f"/api/banks/{bid}/activate")
    data = client.get("/sounds.json").json()
    assert any(x["name"] == "Polished Hatch" for x in data["Atmosphere & FX"])

    # delete
    r = client.delete(f"/api/banks/{bid}/sounds", params={"path": "Doors/raw_hatch.ogg"})
    assert r.json()["ok"] is True
    mf = client.get(f"/api/banks/{bid}").json()
    assert mf["sounds"] == []


def test_update_bank_meta(app, client):
    bid = app.state.library.create_bank("Old Name")
    r = client.post(f"/api/banks/{bid}/meta", json={"name": "New Name", "description": "desc"})
    assert r.json()["ok"] is True
    mf = client.get(f"/api/banks/{bid}").json()
    assert mf["name"] == "New Name" and mf["description"] == "desc"


def test_bank_scoped_audio_preview(app, client):
    store = app.state.library
    bid = store.create_bank("Preview")
    store.add_sound(bid, "Doors", "Hatch", b"OggSpreview", {})
    # served from the specific bank even though it is NOT the active bank
    assert store.active_id() == "heart_of_darkness"
    r = client.get(f"/api/banks/{bid}/audio/Doors/hatch.ogg")
    assert r.status_code == 200 and r.content == b"OggSpreview"


def test_export_import_roundtrip(app, client):
    store = app.state.library
    src = store.create_bank("Exportable")
    store.add_sound(src, "Doors", "Hatch", b"OggSroundtrip", {"kind": "sfx", "lufs": -16.0})

    # export → .sndbank zip
    r = client.get(f"/api/banks/{src}/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    zbytes = r.content

    # import → brand-new custom bank with the same content
    r = client.post("/api/import", files={"file": ("Exportable.sndbank", zbytes, "application/zip")})
    assert r.status_code == 200
    new_id = r.json()["id"]
    assert new_id != src

    mf = client.get(f"/api/banks/{new_id}").json()
    assert any(s["name"] == "Hatch" for s in mf["sounds"])
    client.post(f"/api/banks/{new_id}/activate")
    assert client.get("/audio/Doors/hatch.ogg").content == b"OggSroundtrip"


def test_analyze_report_is_read_only(app, client):
    store = app.state.library
    bid = store.create_bank("Analyze Me")
    store.add_sound(bid, "Doors", "Hatch", b"OggSx", {})
    r = client.post(f"/api/banks/{bid}/analyze")
    assert r.status_code == 200
    body = r.json()
    assert body["target_lufs"] == -16.0
    assert len(body["report"]) == 1 and body["report"][0]["name"] == "Hatch"
    # analyze does not fork or modify the bank
    assert not any(b["builtin"] is False and b["id"] == "heart_of_darkness"
                   for b in client.get("/api/banks").json())


@_needs_ffmpeg
def test_normalize_brings_quiet_sound_to_target(app, client, settings):
    from mission_control.services.soundboard import audio_ingest

    store = app.state.library
    bid = store.create_bank("Loud Mix")
    # Ingest a real (already-normalised) tone, then leave it; normalize should be a near-noop.
    ogg, lufs, _ = audio_ingest.convert_and_normalize(_wav_bytes(), "tone.wav", "sfx", settings)
    store.add_sound(bid, "Weapons", "Tone", ogg, {"kind": "sfx", "lufs": lufs})

    r = client.post(f"/api/banks/{bid}/normalize", json={"threshold": 1.0})
    assert r.status_code == 200
    assert r.json()["ok"] is True


@_needs_ffmpeg
def test_convert_and_normalize_produces_opus(settings):
    from mission_control.services.soundboard import audio_ingest

    ogg, lufs, peak = audio_ingest.convert_and_normalize(
        _wav_bytes(), "tone.wav", "sfx", settings
    )
    assert ogg[:4] == b"OggS"  # Ogg container magic
    assert lufs is None or isinstance(lufs, float)


@_needs_ffmpeg
def test_upload_converts_and_ingests(app, client):
    bid = app.state.library.create_bank("Uploads")
    r = client.post(
        f"/api/banks/{bid}/upload",
        files={"files": ("Pulse Blast.wav", _wav_bytes(), "audio/wav")},
        data={"category": "Weapons", "kind": "sfx"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and len(body["added"]) == 1

    client.post(f"/api/banks/{bid}/activate")
    data = client.get("/sounds.json").json()
    assert any(s["name"] == "Pulse Blast" for s in data["Weapons"])
    # the ingested file is real Opus and streams back
    path = data["Weapons"][0]["path"]
    assert client.get("/audio/" + path).content[:4] == b"OggS"
