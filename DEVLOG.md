# Mission Control v2 — Development Log

Running record of every meaningful decision and change. Append-only; newest entries at the bottom of each phase. Kept up to date continuously so there is always an accurate record of what has been done and why.

- **Repo:** alien-mission-control-v2 (GitHub: pavelklus630/alien-mission-control-v2)
- **Local path:** `/Users/pavelklus/ALIEN_PROJEKCE_ASSETS/CODE/DEV/V_2.0`
- **v1 source of truth:** `/Users/pavelklus/alien-mission-control` (v1.7.1) and dev dirs `…/CODE/DEV/V_1.6`, `…/CODE/DEV/V_1.7`

## Hard requirements carried over from v1 (must not regress)
- Four distinct LAN-reachable ports: **Soundboard 8765, Terminal 8770, Vibe 8090, Map 8085**.
- **OBS Browser Source** compatibility for the `/output` and `/display` pages.
- Efficient audio: **Opus in .ogg (~96 kbps VBR, −16 LUFS)** + **HTTP Range streaming**.

## Extensibility goals (design for, even if not built yet)
- Upload user maps (Erebos Map) and user audio (Soundboard).
- Future editors (sound editor first; possibly map/vibe editors) → services expose content as **structured, editable data**, front-end organized to host editor UIs later.

## Operating rules
- Phase-gated: analysis → development → testing, stop and summarize after each.
- Prefer mature external libraries over custom code (FastAPI/Flask, Jinja2, pydantic, pytest…).
- Use the most token-efficient model that does the job; flag when a step warrants a stronger model.
- Subagents live in `.claude/agents/` (gitignored, local only).

---

## Phase 0 — Repo setup

### 2026-06-04
- **Decision:** v2 working directory placed under the existing dev convention at `…/CODE/DEV/V_2.0` (matches V_1.6 / V_1.7), per user choice. GitHub repo named `alien-mission-control-v2`.
- **Decision:** Did **not** use `gh repo create --source=.` inside the v1 clone — that clone's `origin` already points at the v1 repo and would collide. v2 gets its own fresh git repo instead.
- **Decision:** Subagent set approved as proposed with per-agent models: `legacy-analyst` (sonnet, read-only), `architect` (opus), `service-dev` (sonnet), `frontend-dev` (sonnet), `test-engineer` (sonnet). Opus reserved for architecture design only.
- **Created:** `V_2.0/` git repo, `.gitignore` (gitignores `.claude/agents/`), `DEVLOG.md` (this file), `README.md`, and five agent definitions under `.claude/agents/`.
- **Verified:** `git check-ignore` confirms `.claude/agents/*` is NOT tracked; only `.gitignore`, `DEVLOG.md`, `README.md` are committed.
- **Commit:** `0720f0c` "Phase 0: initialize Mission Control v2 repo".
- **GitHub:** created public repo `pavelklus630/alien-mission-control-v2` via `gh repo create … --public --source=. --remote=origin --push`; `main` tracks `origin/main`. URL: https://github.com/pavelklus630/alien-mission-control-v2
- **Phase 0 complete.** Stopped for consultation before Phase 1 (analysis).

---

## Phase 1 — Systemic analysis of v1

### 2026-06-04
- **Ran** read-only legacy analysis (legacy-analyst charter, on Sonnet via a general-purpose subagent since the named agent isn't registered to the v1-rooted session). No v1 files modified.
- **Preserved** the full report to `docs/phase1-analysis.md`.
- **Decision (user):** Opus audio bitrate stays at **96 kbps** (transparent for ambient/SFX/music over speakers/OBS) but must become a **config value, not a hardcoded constant**, with an optional higher tier (e.g. 128 kbps) for music-heavy cues. Logged as a Phase 2 design requirement.
- **Key findings:** v1 is clean, **zero third-party runtime deps** (pure stdlib `http.server.ThreadingHTTPServer`, daemon-thread per service). Biggest debt = ~200 KB HTML/CSS/JS baked into Python string literals in Terminal/Vibe/Map (Soundboard already uses external `.html`). No tests in canonical clone (dev V_1.6/V_1.7 have a pytest suite + test-then-build `build.sh`). Range streaming only on Soundboard audio; Map reads whole binary into RAM. Path-traversal guards present on Soundboard/Map (explicit `resolve().relative_to`), Terminal uses `.name` trick. All ports bind `0.0.0.0`, no auth (intentional LAN sharing). Inconsistent live-update (poll vs SSE). Config = magic numbers; no structured logging.
- **Architecture recommendation (analyst):** **Option A** — keep four separate in-process services, add shared `config.py` + `server_utils.py` + restore tests. Option B (unified) still needs 4 socket binds for OBS; only B3 (full asyncio rewrite) truly unifies and costs the most. Tension to resolve in Phase 2: analyst's zero-dep stdlib leaning vs. the user's stated want for mature libs (FastAPI/Jinja2/pydantic/pytest) that make uploads + future editors cleaner. **This is the central Phase 2 decision — flagged for the architect (Opus) and user consultation.**
- **7 open questions** recorded for the user at the end of `docs/phase1-analysis.md`.
- **Phase 1 complete.** Stopped for consultation before Phase 2 (design).

---

## Phase 2 — Greenfield v2 design (proposal)

### 2026-06-04
- **Decision (user):** Runtime architecture = **Option A** (four separate in-process services, each binding its own port). Stack = **FastAPI + Jinja2 + pydantic** (+ uvicorn, pydantic-settings, python-multipart, pytest/httpx, ruff).
- **Process note:** architecture designed **inline in the main Opus thread** rather than spawning the `architect` subagent — this thread is already Opus 4.8 (the approved strong model) and holds the full Phase 1 context, so a separate Opus agent would only re-derive it at extra cost.
- **Created** `docs/phase2-architecture.md`: package layout (src layout, `core/` shared infra, four `services/`), the ThreadedUvicorn-per-port mechanism (`install_signal_handlers=False` + `should_exit` graceful stop, fixes v1 quit-race), OBS/SSE handling, reusable `core/ranges.py` (audio + map binaries), pydantic-settings config + rotating file logging, structured editable content models per service (flag-gated upload/editor APIs as the extensibility seam), an 8-step migration plan, dependency table, risks, and 7 open-question assumptions.
- **Plan:** on approval, build step 1 (scaffold + core) then the **Soundboard service end-to-end as the reference implementation**, stop and review before porting Terminal/Vibe/Map.
- **Open questions confirmed (user):** #4 platform = **macOS arm64 only**; #5 Vibe scene = **persist** last scene to `data/vibe/scenes.json`; #6 map = **Erebos-only for now** (keep upload seam clean, defer multi-map UI). Architecture doc assumptions table updated to match.
- **Open questions confirmed (user):** #4 platform = **macOS arm64 only**; #5 Vibe scene = **persist**; #6 map = **Erebos-only for now**.

---

## Phase 2 — Implementation: scaffold + core + Soundboard reference

### 2026-06-04 — build step 1 & 2 (user gave go-ahead; "change the model and let's build")
- **Note on model:** I cannot change the active session model from my side (`/model` is user-only); flagged that the user can run `/model sonnet` anytime for the routine build work.
- **Scaffolded** `src/` layout package `mission_control` + `pyproject.toml` (setuptools, deps: fastapi, uvicorn[standard], jinja2, pydantic, pydantic-settings, python-multipart; dev: pytest, httpx, ruff). Created venv at `.venv` (gitignored), `pip install -e ".[dev]"`.
- **Core modules:**
  - `config.py` — pydantic-settings `Settings` (four ports as defaults, `MC_` env prefix, nested `MC_AUDIO__BITRATE_KBPS`, `resolved_sounds_dir`, `enable_uploads`/`enable_editors` flags). Kills v1 magic numbers.
  - `logging_conf.py` — rotating file log (`~/Library/Logs/MissionControl/`) + stderr. `paths.py` — frozen/dev + macOS dir resolution.
  - `core/ranges.py` — reusable HTTP Range helper (206/`Content-Range`/`Accept-Ranges`/416/404), registers `audio/ogg`. Fixes v1's Soundboard-only Range + Map-whole-file-in-RAM debt.
  - `core/uploads.py` — `safe_join` (traversal-proof) + `validate_upload` (ext/size/content-type). The upload seam; routes stay gated.
  - `core/app_factory.py` (CORS `*` + `NoCacheMiddleware`), `core/middleware.py`, `core/templating.py` (Jinja2Templates), `core/server.py` (`ThreadedUvicorn`: `install_signal_handlers=False` + `should_exit`).
- **Soundboard service** (port 8765) — full v1 contract preserved: `GET / /control /output /state /sounds.json /audio/<path>` + `POST /` actions (play/stop/stop_all/volume/voice_on/voice_off), plus new `GET /api/sounds` (flat structured list = editor/upload seam). HTML moved from external files to Jinja `templates/` (verified no Jinja-token collisions). `repository.SoundLibrary` ports v1 `scan_sounds`/`clean_name` but **caches** the scan (fixes debt 3.13) and **skips hidden dirs/files** (improvement over v1, which leaked hidden dirs as bogus categories). `state.PlaybackState` ports the shared play/voice state behind a lock.
- **Tests (29, all green):** `test_config` (defaults/env/resolved dir), `test_ranges` (full/partial/open-ended/416/404), `test_uploads` (traversal + validation matrix), `test_soundboard` (pages render w/ no-store, sounds.json grouping+order, hidden/non-audio skip, api/sounds, play/stop/volume/voice cycle, real Range streaming, traversal 403/404, missing 404). conftest builds a tmp sounds tree — no real assets, no real port.
- **Two test bugs found & fixed during the run:** (1) wrong `clean_name` expectation (`Weap__X` → `Weap X`, not `X`); (2) wrong category-order expectation (CATEGORY_ORDER has Doors before Weapons). Both were test errors, not code errors — except the hidden-dir case, which exposed a real v1 latent bug now improved in v2.
- **Live smoke test** vs the **real v1 sound library** (100 .ogg, port 8765): `/sounds.json` returned all 6 categories in correct order; `/control` served (72157 B, `cache-control: no-store`); **real Opus Range** `bytes=0-99` → `206 content-range: bytes 0-99/128845`, partial byte-exact vs file head; traversal → 404 (no leak). Server started/stopped cleanly via the standalone runner.
- **Pattern validated.** User reviewed Soundboard reference and gave go-ahead ("review and proceed").

### 2026-06-04 — build Terminal / Vibe / Map services

- **Terminal service** (port 8770): `MessageLog` (cursor-poll, in-memory), models (`Message`, `MessageType`, `PollResponse`), routes (`GET /` `/input` `/display` `/poll?since=N` `/sounds/<name>` `/api/log`, `POST /send`). HTML served as `FileResponse` (not Jinja) because the v1 markup contains CSS `{#selector}` patterns that are valid Jinja2 comment delimiters — collision avoided by rendering-bypass. Sound files served by `.name` component (no traversal; `.ogg`-only guard). 8/8 tests pass.
- **Vibe service** (port 8090): `VibeState` with thread-safe asyncio.Queue SSE fan-out + persist-to-JSON on scene change (user-confirmed: restore on restart). Persistence uses atomic write (`.tmp` → rename). Routes: `GET /` `/control` `/control.html` `/display` `/display.html` `/api/scene` `/api/events` `/api/scenes`, `POST /api/scene`. HTML served via `FileResponse` (Jinja collision: CSS `{{}}`/`{%` patterns in baked Vibe markup). SSE unit test tests `VibeState.subscribe/broadcast/unsubscribe` directly (TestClient SSE streaming blocks; direct async test is correct approach). 7/7 pass.
- **Map service** (port 8085): `MapState` (title/menu toggle), routes preserve v1 contract (`GET /` `/control` `/display` `/api/state` `/api/maps/erebos`, `POST /api/toggle` `/api/toggle-menu`, `GET /assets/*` `/fonts/*` `/maps/*` `/ludicrpg.png`). All cache files served via `core/ranges.py` — **fixes v1's whole-file-in-RAM debt** for `map-bundle.bin`. Traversal guard via `safe_join`. `/api/maps/erebos` structured descriptor = editor/multi-map seam. 10/10 tests pass.
- **Full suite: 54/54 pass** (config 5, map 10, ranges 5, soundboard 9, terminal 8, uploads 10, vibe 7). No real ports, no real assets in tests.
- **Stopped for consultation.** Phase 2 implementation (all four services) complete. Pending: launcher/supervisor, PyInstaller spec update, pre-launch test gate (Phase 3).

### 2026-06-04 — launcher, __main__ gate, build tooling (user: "review and proceed")

- **Config**: added `resolved_terminal_sounds_dir` and `resolved_map_cache_dir` properties following the same frozen-path pattern as `resolved_sounds_dir` — in a frozen .app they resolve to `_MEIPASS/terminal/sounds` and `_MEIPASS/map/cache`; in dev to `data_dir/terminal_sounds` and `data_dir/map_cache`. Tests updated to use explicit dir fixtures.
- **`core/server.py`**: added `on_crash` callback to `ThreadedUvicorn.start()` — fires if uvicorn thread exits without `should_exit` being set (unexpected crash), fed from the launcher's `_on_crash` handler.
- **`launcher/supervisor.py`**: `ServiceDescriptor` dataclass + `make_services()` factory that defers service imports to call time (avoids Tkinter-level import side effects). Four descriptors with correct ports, URL labels, icons, and factories for all services.
- **`launcher/app.py`**: full Tkinter Canvas launcher, identical look to v1. Key v2 improvements: drives `ThreadedUvicorn.start/stop` instead of `make_server()/serve_forever`; quit signals `should_exit` on all uvicorn instances (fixes v1's 500ms quit-race); auto-update backs up the old `.app` before replacing it (`cp -a` + `rm -rf`). LAN_IP, ports, and URLs all come from Settings.
- **`__main__.py`**: pre-launch test gate — runs `pytest -m "not slow" -q --tb=short` as a subprocess before starting the launcher. Aborts with a clear message if tests fail. Bypassed automatically when frozen (pytest not bundled); bypassable manually via `MC_SKIP_TESTS=1` for rapid dev iteration.
- **`build.sh`**: test-then-build script (creates venv if needed → `pytest -m "not slow"` → `PyInstaller`). Same pattern as v1 dev build.sh.
- **`mission_control.spec`**: v2 PyInstaller spec — `src/` layout entry point, `collect_data_files("mission_control")` for templates/static, full hidden imports for FastAPI/Starlette/uvicorn/pydantic-v2/jinja2/anyio. Bundle ID `com.pavelklus.alien.missioncontrol.v2`, version `2.0.0a0`, `arm64`.
- **`.gitignore`**: un-ignored `mission_control.spec` (was blanket-ignored by `*.spec`).
- **Verified**: 54/54 tests pass; supervisor resolves all four factories at correct ports; `MC_SKIP_TESTS=1` gate bypass works; pre-launch pytest run exits 0.
- **Phase 2 + Phase 3 (gate) complete.** Stopped for consultation before PyInstaller build smoke-test and any further work.

### 2026-06-04 — visual check of Tkinter launcher

- **Issue found:** pyenv Python 3.11.8 lacks `_tkinter` (built without Tcl/Tk — standard pyenv gotcha on macOS). All four Homebrew Python 3.11/3.13 builds from `/opt/homebrew` also lack it. **`/usr/local/bin/python3.13` (Python.org framework build) has working Tkinter.** Venv rebuilt with that interpreter; 54/54 tests still pass on 3.13.
- **Visual check result — PASSED.** All requirements met:
  - Header: "MISSION CONTROL" title, live clock (ticking), LAN IP (192.168.1.49).
  - Four service cards: SOUNDBOARD (:8765), MU/TH/UR TERMINAL (:8770), VIBE GENERATOR (:8090), EREBOS STATION (:8085) — all with correct icons, tags, port labels, link labels, log area.
  - All four START buttons visible before launch.
  - Footer: LAUNCH ALL / STOP ALL / QUIT — all present and styled correctly.
  - After LAUNCH ALL: all four cards turned green (border + glow + dot), status = "● ONLINE · port XXXX responding", buttons changed to red STOP, log shows "Listening on :XXXX". HTTP 200 confirmed on all four ports via curl.
  - Look is identical to v1.
- **Note for setup docs:** To run the launcher, use `/usr/local/bin/python3.13` (Python.org framework build) or any Python with a working `_tkinter`. pyenv builds on macOS require `brew install tcl-tk` + pyenv reinstall to get Tk support. PyInstaller `.app` bundles its own Tk so this is a dev-only concern.

### 2026-06-04 — icon fixes (user report: no icon in corner or dock)
- **Root cause 1 (canvas corner icon):** `assets/` directory did not exist in V_2.0 — the path resolved correctly (4 parent levels from `app.py` = repo root) but the file wasn't there. Fixed by copying assets from v1: `cp -r alien-mission-control/assets V_2.0/assets`.
- **Root cause 2 (dock icon):** Running as bare `python -m` shows the Python interpreter's dock icon. Fixed by calling `NSApplication.sharedApplication().setApplicationIconImage_()` via AppKit (PyObjC) in `_load_icon()`, with silent fallback if AppKit is unavailable. Also added `iconphoto()` call for the window titlebar icon.
- **Dock icon:** now rounded — switched from `alien_avatar.png` (flat PNG, no mask) to `AlienMissionControl.icns` (carries the rounded icon mask) via `NSApplication.setApplicationIconImage_()`. Canvas corner icon unchanged (`alien_avatar.png`).
- **Menu bar label:** "Mission Control" — set by patching `CFBundleName`/`CFBundleDisplayName` into `NSBundle.mainBundle().infoDictionary()` before Tkinter renders.
- **Dock hover tooltip:** still reads "Python" in dev mode — known macOS limitation. The WindowServer registers the tooltip from `Python.app`'s bundle at process launch, before any runtime AppKit calls. This cannot be overridden without a stub `.app` wrapper. **Not a concern for production:** the PyInstaller `.app` bundle has its own `Info.plist` so the dock will show "Mission Control" correctly for real users.
- **54/54 tests still pass.**
