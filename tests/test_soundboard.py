"""End-to-end tests for the Soundboard service (the v2 reference service)."""


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
    assert client.get("/state").json() == {"_voice": {"active": False, "deviceId": ""}}

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
