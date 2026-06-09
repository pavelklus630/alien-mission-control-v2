# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`alien-mission-control-v2` — a clean-architecture rewrite of the ALIEN RPG GM toolkit
("Mission Control"), a macOS app that runs **four independent LAN-reachable web services**
for running tabletop sessions. Each service is a FastAPI app on its own fixed port, fronted
by a Tkinter launcher. The GM drives `/control` pages; OBS / external monitors show
`/output` / `/display` pages.

| Service | Port | Package | Notable routes |
|---|---|---|---|
| Soundboard | 8765 | `services/soundboard` | `/control` `/output` `/editor` |
| MU/TH/UR Terminal | 8770 | `services/terminal` | `/input` `/display` `/poll` `/send` |
| Vibe Generator | 8090 | `services/vibe` | `/control` `/display` `/editor` |
| Erebos Map | 8085 | `services/map` | `/control` `/display` |

> The README's "Status: nothing runnable yet / Phase 0" line is stale — the app is shipped
> (pyproject is at 2.3.0). Trust the code and `DEVLOG.md`, not that line.

## Commands

All commands assume the project venv at `.venv` (created by `build.sh` on first run, or
`python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`).

```bash
# Run the full app (Tkinter launcher + all four services)
python -m mission_control                 # runs the pre-launch test gate first
MC_SKIP_TESTS=1 python -m mission_control  # bypass the gate during rapid iteration

# Run a single service standalone (no launcher, no gate) — fastest dev loop for one service
python -m mission_control.services.soundboard.app   # .terminal.app / .vibe.app / .map.app

# Tests
.venv/bin/python -m pytest                 # all tests (-q is default via pyproject)
.venv/bin/python -m pytest -m "not slow"   # the fast pre-launch gate subset
.venv/bin/python -m pytest tests/test_vibe.py::test_name   # a single test

# Lint / format
.venv/bin/ruff check .
.venv/bin/ruff format .

# Build the signed .app bundle (tests -> vendor ffmpeg -> PyInstaller -> codesign)
./build.sh
```

There is **no `requirements.txt`** — dependencies live in `pyproject.toml` (`[project]`
runtime, `[project.optional-dependencies].dev` for pytest/httpx/ruff). `src/` is on the
pytest pythonpath, so imports are `mission_control.*` without installing.

## Architecture

**Per-service factory pattern.** Every service exposes `create_app(settings) -> FastAPI`
in its `app.py`. It calls `core.app_factory.create_service_app(name)` (shared CORS,
`NoCacheMiddleware`, docs disabled) then mounts its own router(s) and attaches per-service
objects to `app.state`. This is "Option A": services share *code* but each runs on its own
port with its own lifetime — they are never combined into one app.

**Launcher + supervision.** `python -m mission_control` → `launcher/app.py` (Tkinter, main
thread). `launcher/supervisor.py` holds the `ServiceDescriptor` table (name, port, URLs,
lazy factory) — the single place service wiring lives. Each running service is a
`core/server.py::ThreadedUvicorn` (one uvicorn server per thread, `install_signal_handlers
=False` because it's off the main thread). The launcher can start/stop/restart each service
independently and is notified on crash via an `on_crash` callback.

**State + real-time.** Each service keeps thread-safe in-memory state (its `state.py`).
Two real-time patterns are used: **SSE fan-out** (Vibe — `subscribe()`/`_broadcast()` over
`asyncio.Queue`) and **cursor poll** (Terminal — `GET /poll?since=N`). Persisted state is
written atomically (`tmp.write` then `replace`) and reloaded on startup; persistence failures
are swallowed so a read-only FS never crashes a service.

**Config.** `config.py` (pydantic-settings). All values overridable via `MC_`-prefixed env
vars or `.env`; nested with `__` (e.g. `MC_AUDIO__BITRATE_KBPS=128`). Use the
`get_settings()` lru-cached singleton in app code; tests construct `Settings(...)` directly
and call `get_settings.cache_clear()`. Feature flags `enable_uploads` / `enable_editors`
default **off**.

**Dev vs frozen paths.** `paths.py` is the single source of truth for filesystem location.
In a PyInstaller bundle, bundled resources resolve under `sys._MEIPASS`; in dev they resolve
next to the source. The `resolved_*_dir` properties on `Settings` encode this fork — never
hardcode an asset path, go through them. User-writable data always lives at
`~/Library/Application Support/MissionControl` (logs at `~/Library/Logs/MissionControl`),
never inside the read-only `.app`.

**Pre-launch test gate.** `__main__.py` runs the fast pytest subset before starting the
launcher and aborts (services never start) on failure. In a frozen build pytest isn't
bundled, so the gate is bypassed — `build.sh` runs the full suite as a separate pre-PyInstaller
step instead. So tests gate *both* dev startup and release builds.

**ffmpeg/ffprobe.** The audio converter shells out to vendored binaries
(`vendor/ffmpeg` in dev, bundled under `sys._MEIPASS/ffmpeg` when frozen), falling back to
system PATH. A Finder-launched `.app` has a minimal PATH, so `build.sh` ad-hoc codesigns the
bundled binaries under the hardened runtime. Audio targets: Opus/OGG, −16 LUFS.

**Templating quirk.** Most services render Jinja2 templates, but **Terminal serves raw HTML
via `FileResponse`** — its v1 markup contains CSS `{#…}` patterns that collide with Jinja's
comment delimiter, and the pages need no server-side variables.

## Tests

`pytest` + FastAPI `TestClient`. `tests/conftest.py` builds a temporary synthetic sounds
tree (small byte payloads, not real OGG — the Range machinery is byte-oriented) so tests
**never bind a real port and never touch the user's real sound library**. The `slow` marker
is deselected from the fast gate. Add tests under `tests/`; the `client`/`settings`/`app`
fixtures wire a soundboard app against the temp tree.

## Conventions specific to this project

- **v1 is frozen.** The sibling repo `alien-mission-control` (v1.7.1) must never be modified —
  all work happens here in V_2.0.
- **Git flow** is documented in [`docs/GITFLOW.md`](docs/GITFLOW.md): trunk-based on `main`,
  branch only for risky/experimental work (`feat/` `fix/` `chore/` `experiment/`), and
  **every release must be tagged** `vX.Y.Z` and pushed with `--follow-tags`.
- **Release steps:** `pytest` → bump the version → update `DEVLOG.md` → commit → annotated
  tag → `./build.sh` → `gh release create` with the zipped `.app`.
- **Version drift to watch:** the canonical version is in `pyproject.toml` (2.3.0), but
  `__init__.py::__version__` and the hardcoded `version="2.0.0a0"` in
  `core/app_factory.py` are stale. Bump all version sources together on release.
