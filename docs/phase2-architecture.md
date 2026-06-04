# Mission Control v2 — Architecture & Migration Plan (Phase 2 design)

> **Status: PROPOSAL — no production code written yet.** Presented for consultation per the phase gate.
> Decisions locked with the user: **Option A** (four separate in-process services, each binding its own port) + stack **FastAPI + Jinja2 + pydantic**. Audio stays **Opus/OGG @ 96 kbps**, made **configurable** with an optional higher tier.

---

## 1. Guiding principles

- **Clean separation:** launcher ↔ services ↔ front-end. No service imports another; everything shared goes through a `core/` package.
- **Templates, not string literals:** all HTML moves to Jinja2 templates with separated `static/` (CSS/JS/fonts).
- **Typed config + structured logging:** pydantic-settings replaces scattered magic numbers; `logging` replaces silenced access logs.
- **Mature libs over hand-rolled:** FastAPI/Starlette (routing, Range via `FileResponse`, uploads, SSE via `StreamingResponse`, `TestClient`), Jinja2 (templating), pydantic v2 + pydantic-settings (models/config/validation), pytest (tests + pre-launch gate), uvicorn (ASGI server).
- **Design for extensibility now, build later:** services expose content as **structured, editable data** behind repositories + `/api/...` endpoints; front-end is organized so `/editor` UIs and uploads slot in without restructuring.

---

## 2. Package layout (src layout)

```
V_2.0/
├── pyproject.toml                 # deps, ruff, pytest, build config
├── mission_control.spec           # PyInstaller (updated for fastapi/uvicorn/jinja2)
├── build.sh                       # test-then-build gate
├── src/
│   └── mission_control/
│       ├── __init__.py
│       ├── __main__.py            # `python -m mission_control` → launcher
│       ├── config.py              # pydantic-settings: ports, paths, audio, feature flags
│       ├── logging_conf.py        # rotating file log + in-UI deque handler
│       ├── paths.py               # bundled (PyInstaller _MEIPASS) vs writable user data dirs
│       ├── launcher/
│       │   ├── app.py             # Tkinter launcher (adapted from v1, Canvas UI kept)
│       │   └── supervisor.py      # start/stop the 4 uvicorn servers in daemon threads
│       ├── core/                  # shared service infrastructure
│       │   ├── app_factory.py     # build_app(name, routers, templates, static) → FastAPI
│       │   ├── middleware.py      # CORS(*), OBS no-cache headers, access logging
│       │   ├── ranges.py          # HTTP Range helper (audio + map binaries)
│       │   ├── uploads.py         # validation: content-type/size/ext/codec, safe storage
│       │   ├── templating.py      # shared Jinja2 environment
│       │   └── server.py          # uvicorn Server wrapper: run-in-thread + graceful stop
│       ├── shared_static/
│       │   └── fonts/ShareTechMono.woff2   # de-duplicated single copy
│       └── services/
│           ├── soundboard/        # :8765
│           │   ├── app.py  routes.py  models.py  repository.py
│           │   ├── templates/{control.html, output.html}
│           │   └── static/{css,js}
│           ├── terminal/          # :8770  (cursor-poll)
│           ├── vibe/              # :8090  (SSE)
│           └── map/               # :8085  (Range-served bundles + uploads)
├── tests/
│   ├── conftest.py                # fixtures, TestClient, tmp data dirs
│   ├── test_config.py  test_ranges.py  test_uploads.py
│   └── test_soundboard.py  test_terminal.py  test_vibe.py  test_map.py
├── data/                          # USER-WRITABLE content (gitignored)
│   ├── sounds/   maps/   vibe/    # uploaded/edited assets + persisted state + json metadata
└── docs/
    ├── phase1-analysis.md
    └── phase2-architecture.md     # this file
```

---

## 3. How the four ports are served (the Option-A mechanism)

Each service exposes `create_app() -> FastAPI`. The launcher's **supervisor** builds one uvicorn server per service and runs each in its own daemon thread:

```python
# core/server.py (sketch)
class ThreadedUvicorn:
    def __init__(self, app, host, port):
        cfg = uvicorn.Config(app, host=host, port=port, log_config=None, lifespan="on")
        self.server = uvicorn.Server(cfg)
        self.server.install_signal_handlers = False   # required: not on main thread
        self._thread = None
    def start(self):
        self._thread = threading.Thread(target=self.server.run, daemon=True)
        self._thread.start()
    def stop(self):
        self.server.should_exit = True                # graceful; uvicorn drains then exits
        self._thread.join(timeout=5)
```

This preserves every v1 property: **four distinct ports**, `host="0.0.0.0"` (LAN-reachable), and **independent lifetimes** — the launcher can start/stop each service individually from its Canvas UI, exactly like today. Key implementation notes carried as risks: `install_signal_handlers=False` (we're off the main thread), and `should_exit` for clean shutdown (fixes v1's quit-race + Vibe non-daemon-thread hang).

---

## 4. OBS Browser Source + external monitor

- `/output` (Soundboard) and `/display` (Terminal/Vibe/Map) render Jinja templates with **no-cache headers** and preserved transparent backgrounds, added centrally in `core/middleware.py`.
- CORS `Access-Control-Allow-Origin: *` kept (LAN control from a phone).
- **Vibe SSE** re-implemented with Starlette `StreamingResponse(media_type="text/event-stream")` + an `asyncio.Queue` per client and a keepalive ping — same contract as v1's `/api/events`, so existing OBS sources keep working.
- Three independent display windows on the external monitor is unchanged — they're just four URLs on four ports.

---

## 5. Audio + Range streaming

- `core/ranges.py` — one reusable helper returning correct `206`, `Accept-Ranges: bytes`, `Content-Range`, and chunked streaming. FastAPI's `FileResponse` already honors Range for static files; the helper wraps the cases needing custom logic (and **fixes v1's Map service reading whole binaries into RAM** — `alien_map.py:516-536`).
- Audio stays **Opus/OGG**. `config.py` holds `audio.bitrate_kbps = 96` with optional per-category override (e.g. `music = 128`). Encoding remains an **offline ffmpeg asset step** (−16 LUFS normalization preserved); the config records the target so the future upload pipeline re-encodes consistently.

---

## 6. Config & logging (kills the magic numbers)

```python
# config.py (pydantic-settings sketch)
class AudioSettings(BaseModel):
    bitrate_kbps: int = 96
    music_bitrate_kbps: int | None = 128
    target_lufs: float = -16.0

class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port_soundboard: int = 8765
    port_terminal: int   = 8770
    port_vibe: int       = 8090
    port_map: int        = 8085
    data_dir: Path = default_user_data_dir()      # ~/Library/Application Support/MissionControl
    audio: AudioSettings = AudioSettings()
    enable_uploads: bool = False                    # extensibility flags, off by default
    enable_editors: bool = False
    model_config = SettingsConfigDict(env_prefix="MC_", env_file=".env")
```

`logging_conf.py` → rotating file under `~/Library/Logs/MissionControl/` **plus** a handler feeding the launcher's in-UI deque. Replaces the four `log_message = lambda *_: None` silencers.

---

## 7. Structured, editable content — the extensibility seam

Each service exposes content as typed pydantic models behind a repository, with read APIs now and write/upload APIs **designed but flag-gated** (`enable_uploads`, `enable_editors`):

| Service | Model (sketch) | Store | Read API (now) | Write/upload API (designed, gated) |
|---|---|---|---|---|
| Soundboard | `Sound{id,name,category,file,duration,loop,gain}` | `data/sounds/library.json` + audio dir | `GET /api/sounds` | `POST /api/sounds` (upload+re-encode), `PUT /api/sounds/{id}` |
| Map | `MapAsset{id,name,bundle,layers}` | `data/maps/` | `GET /api/maps`, `GET /api/maps/{id}` | `POST /api/maps` (image upload → Range-served) |
| Vibe | `Scene{id,name,params}` | `data/vibe/scenes.json` | `GET /api/scenes` | `PUT /api/scenes/{id}` (vibe editor) |
| Terminal | `Message{id,ts,text,kind}` | in-memory (+ optional `data/terminal/`) | `GET /api/log` | n/a (authoring is live input) |

Front-end is organized so a per-service `/editor` route can be added later, consuming these `/api/...` endpoints. **No editor is built in Phase 2 — only the seams.** Uploads go through `core/uploads.py` (content-type allowlist, size cap, extension/codec check, path-traversal-safe storage under `data/`).

---

## 8. Migration plan (build order, after approval)

1. **Scaffold:** `pyproject.toml` (deps below), package skeleton, `config.py`, `logging_conf.py`, `paths.py`, `core/{app_factory,middleware,ranges,uploads,templating,server}.py`, `tests/conftest.py`. Wire a minimal **pre-launch test gate** stub (deepened in Phase 3).
2. **Soundboard** (cleanest, already external HTML): port routes → FastAPI, HTML → Jinja templates, audio → `core/ranges`, add `Sound` repository + `GET /api/sounds`. Tests.
3. **Terminal:** extract `DISPLAY_HTML`/`INPUT_HTML` → templates, port cursor-poll `/poll?since=N`, `Message` model. Tests.
4. **Vibe:** extract HTML → templates, port SSE → `StreamingResponse`, `Scene` model. Tests.
5. **Map:** extract HTML → templates, port state routes, **Range-serve bundles**, `MapAsset` model + upload stub. Tests.
6. **Launcher + supervisor:** adapt Tkinter launcher to drive `ThreadedUvicorn` start/stop; keep Canvas UI; fix quit-race; safer self-update (**backup before `rm -rf` replace**); route in-UI log through the logging handler.
7. **Packaging:** update `mission_control.spec` (hidden imports for fastapi/starlette/uvicorn/pydantic/jinja2; bundle `templates/`, `static/`, fonts), `build.sh` runs tests then PyInstaller.
8. **Cleanup:** de-duplicate the Share Tech Mono woff2 into `shared_static/fonts/`.

Each service step is independently shippable and testable, mirroring how v1's services are already independent.

---

## 9. Dependencies (proposed)

| Package | Role | Notes |
|---|---|---|
| `fastapi` | routing, DI, OpenAPI | Starlette under the hood (SSE, Range, uploads) |
| `uvicorn[standard]` | ASGI server | one server per port, run in thread |
| `jinja2` | HTML templates | replaces baked-in strings |
| `pydantic` (v2) | content models, validation | |
| `pydantic-settings` | typed config from env/.env | |
| `python-multipart` | file uploads | required by FastAPI for form/upload |
| `pytest`, `httpx` | tests + `TestClient` | pre-launch gate |
| `ruff` (dev) | lint/format | |
| ffmpeg (external tool) | audio encode/normalize | asset pipeline, not bundled as a lib |

Tkinter stays stdlib (launcher). This is a deliberate, modest dependency set — all mature, all PyInstaller-friendly.

---

## 10. Risks & mitigations

- **PyInstaller hidden imports** for FastAPI/uvicorn/pydantic v2 — well-trodden; add to `hiddenimports` + collect data files. Build.sh validates a smoke launch.
- **uvicorn-in-thread shutdown** — handled via `install_signal_handlers=False` + `should_exit`; test start/stop cycles.
- **Bundle size grows** (~tens of MB for the deps) — acceptable for a desktop .app; no user-visible cost.
- **Async vs v1's sync mental model** — most handlers are simple; SSE benefits from async. Keep handlers thin.

---

## 11. Open questions → working assumptions (please confirm/correct)

| # | Question | Working assumption |
|---|---|---|
| 1 | Ports fixed? | **Yes** — 8765/8770/8090/8085 unchanged (hard req). |
| 2 | Dev hot-reload wanted? | Nice-to-have via uvicorn `--reload` in a dev script; not in the packaged app. |
| 3 | How are audio/map assets distributed to new machines? | Shipped in the bundle; user uploads land in writable `data/`; tests use tiny fixtures, not real assets. |
| 4 | Platform targets? | **macOS arm64 only** (as v1), but code stays portable. ← *confirm* |
| 5 | Vibe scene: persist or reset on restart? | **Persist** last scene to `data/vibe/` (cheap, nice). ← *confirm* |
| 6 | Map: Erebos-only or multi-map? | Design map service for **multiple maps** (aligns with upload goal); ship Erebos. ← *confirm* |
| 7 | Log file under `~/Library/Logs/MissionControl/`? | **Yes.** |

---

## 12. What I'd do next (on approval)

Begin the migration plan at step 1 (scaffold + core), then build the Soundboard service end-to-end (step 2) as the reference implementation, **stop, and show it to you** before porting the other three — so we validate the pattern (FastAPI app factory, Jinja templates, Range audio, content repository, tests) on one service before repeating it.
