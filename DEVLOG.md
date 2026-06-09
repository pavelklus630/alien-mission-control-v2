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
### 2026-06-04 — first .app build

- **Fixed:** `__main__.py` used `from .launcher.app import run` (relative import). PyInstaller executes `__main__` directly (not as `mission_control.__main__`), so relative imports fail. Changed to `from mission_control.launcher.app import run`.
- **Fixed:** `.gitignore` was not excluding `build/` and `dist/`.
- **Spec updated:** added `V1` path constant and uncommented sounds/map-cache asset lines pointing at v1 library (interim until v2 has its own asset pipeline).
- **Build result:** `dist/Mission Control.app` — 141 MB, 54 tests pass before PyInstaller runs, clean build (no errors/warnings). Info.plist: `CFBundleName = Mission Control`, version `2.0.0a0`, arm64.
- **Verified:** app launches without crash; menu bar reads "Mission Control"; alien avatar in canvas corner; rounded dock icon (.icns).
- **User verified:** LAUNCH ALL tested manually — all 4 services ONLINE, pages load. Dock tooltip reads "Mission Control" in the bundled .app (Info.plist bundle name confirmed in menu bar).
- **Released:** tag `v2.0.0a0` pushed; `MissionControl-v2.0.0a0-arm64.zip` (116 MB, ditto-packed to preserve macOS metadata) uploaded to https://github.com/pavelklus630/alien-mission-control-v2/releases/tag/v2.0.0a0
- **Note for setup docs:** To run the launcher, use `/usr/local/bin/python3.13` (Python.org framework build) or any Python with a working `_tkinter`. pyenv builds on macOS require `brew install tcl-tk` + pyenv reinstall to get Tk support. PyInstaller `.app` bundles its own Tk so this is a dev-only concern.

### 2026-06-04 — icon fixes (user report: no icon in corner or dock)
- **Root cause 1 (canvas corner icon):** `assets/` directory did not exist in V_2.0 — the path resolved correctly (4 parent levels from `app.py` = repo root) but the file wasn't there. Fixed by copying assets from v1: `cp -r alien-mission-control/assets V_2.0/assets`.
- **Root cause 2 (dock icon):** Running as bare `python -m` shows the Python interpreter's dock icon. Fixed by calling `NSApplication.sharedApplication().setApplicationIconImage_()` via AppKit (PyObjC) in `_load_icon()`, with silent fallback if AppKit is unavailable. Also added `iconphoto()` call for the window titlebar icon.
- **Dock icon:** now rounded — switched from `alien_avatar.png` (flat PNG, no mask) to `AlienMissionControl.icns` (carries the rounded icon mask) via `NSApplication.setApplicationIconImage_()`. Canvas corner icon unchanged (`alien_avatar.png`).
- **Menu bar label:** "Mission Control" — set by patching `CFBundleName`/`CFBundleDisplayName` into `NSBundle.mainBundle().infoDictionary()` before Tkinter renders.
- **Dock hover tooltip:** still reads "Python" in dev mode — known macOS limitation. The WindowServer registers the tooltip from `Python.app`'s bundle at process launch, before any runtime AppKit calls. This cannot be overridden without a stub `.app` wrapper. **Not a concern for production:** the PyInstaller `.app` bundle has its own `Info.plist` so the dock will show "Mission Control" correctly for real users.
- **54/54 tests still pass.**

---

### 2026-06-05 — v2.0.1 mic latency fix (previous session)

- **Microphone voice effect:** replaced deprecated `ScriptProcessor(2048)` (~46 ms delay) with inline `AudioWorklet` (~3 ms). Falls back to `ScriptProcessor(512)` on older browsers.
- **AudioContext:** `latencyHint: 'interactive'` + `getUserMedia { latency: 0 }` for lowest pipeline latency.
- **Versioning:** switched from alpha strings (`2.0.0a0`) to standard semver (`MAJOR.MINOR.PATCH`).
- **54/54 tests pass.** GitHub release `v2.0.1` published with `MissionControl-v2.0.1-arm64.zip`.
- **Note:** `CURRENT_VERSION` in `launcher/app.py` was bumped to `"2.0.1"` and a `.zip` asset was attached to the release. The auto-updater code (`_check_update()` / banner / download flow) exists but has **not been end-to-end tested** against a real version transition — verifying the full update path (API check → banner → zip download → `.app` swap → relaunch) is a future task.

---

### 2026-06-07 — v2.0.2 soundboard waveform + AUDIO STATUS

- **Waveform reworked:** replaced continuous-stroke oscilloscope line with pixelated phosphor approach — one small rectangle (2×3 px logical) per column placed at the exact signal position. No vertical spread, no bars. Canvas taller (48 px, opacity 0.85). Idle state shows sparse scattered dots along centre line.
- **Decorative sine wave removed:** `#stwv` canvas (status bar ornament) deleted — CSS rule, HTML element, and `initWave()` call all removed.
- **AUDIO STATUS now reflects real AudioContext state:** amber dot + SUSPENDED on page load (browser autoplay policy); green dot + SYSTEMS NOMINAL once AudioContext is running (after first user gesture); red dot + DISCONNECTED if server unreachable; red dot + NO AUDIO if AudioContext cannot be created. `statechange` listener fires the update immediately on user click without waiting for the next poll cycle.
- **Dead code removed:** `initWave()` (animated decorative sine generator) was left in the file when its call-site (`initWave('stwv', …)`) was deleted; caught in review and removed in follow-up.
- **54/54 tests pass** (frontend-only changes; no Python modified).
- **Release gaps (caught after the fact):** `CURRENT_VERSION` in `launcher/app.py` was NOT bumped to `"2.0.2"` — the launcher header still shows v2.0.1. No `.zip` asset was attached to the v2.0.2 GitHub release — so `_check_update()` returns `None` and no update is offered to v2.0.1 users. Skipping the build was incorrect even for frontend-only changes: without a new `.app` zip, the version string is wrong and the auto-updater cannot deliver the change.
- **Required for every release going forward:** bump `CURRENT_VERSION` in `launcher/app.py`, run `build.sh`, attach the resulting zip to the GitHub release.
- **Auto-updater status:** the full update flow (API check → banner → zip download → `.app` swap → relaunch) has never been end-to-end tested. To be verified in a future version.
- **GitHub release `v2.0.2`** published (tag only, no zip asset — acknowledged deficiency above).

---

### 2026-06-08 — v2.1.0 Vibe Scene Editor + full JSON renderer

**Version bump:** `2.0.2` → `2.1.0` in `pyproject.toml` and `CURRENT_VERSION` in `launcher/app.py`.

**Vibe — Scene Editor (`/editor`):**
- New browser-based scene editor at `/editor` (three-panel SPA: layer list, canvas preview, property panel).
- 12 built-in JSON scenes in `scenes/builtin/` — each a declarative layer stack (solid_bg, gradient_bg, vignette, particle_field, vortex, nebula_wisps, path_flow, geometric, image, sprite, custom).
- Custom scenes saved to `data_dir/vibe/scenes/` — shadow builtins with the same ID (custom copy wins).
- Import/export as `.vibe` ZIP (scene.json + assets/ subfolder).
- Scene editor restyled to match green color scheme (`--g:#33dd55`, `--bg:#020602`, etc.) of all other app panels.
- "TEST ▶" button now calls `POST /api/scene-by-id` for any scene (builtin or custom), not just integer-indexed builtins.

**Vibe — Scene-by-ID API:**
- New `POST /api/scene-by-id` endpoint: switches to any scene (builtin or custom) by string ID.
- `VibeState.set_scene_by_id(scene_id)`: sets `_scene_id`, sets `_scene = -1` sentinel, broadcasts `{scene: -1, scene_id: "xxx"}` via SSE.
- `VibeState.set_scene(int)`: clears `_scene_id = None` (existing int-based API unmodified).
- `VibeState.get()`: includes `scene_id` key only when not None — preserves existing test `{"scene": 0}` exact match.

**Vibe — display.html rewritten:**
- Replaced 994-line hardcoded imperative renderer with JSON renderer (~360 lines).
- All 12 layer types rendered from JSON: solid_bg, gradient_bg, vignette, particle_field, vortex, nebula_wisps, path_flow, geometric, image, sprite, custom.
- SSE listener handles both `{scene: N}` (integer → BUILTIN_IDS mapping) and `{scene_id: "xxx"}` (direct string ID).
- Crossfade transition via black overlay (fade_out → load → fade_in).
- Asset preloading from `/api/editor/assets` on init.

**Vibe — control.html updated:**
- Now loads scenes from `GET /api/editor/scenes` (returns all scenes: builtins + custom shadows) instead of `GET /api/scenes` (builtins only, integer-indexed).
- Custom scenes appear in the grid with a `★` prefix.
- Scene switching uses `POST /api/scene-by-id` with string ID.
- SSE and polling fallback both handle `scene_id` field.
- Keyboard shortcut 1-9 maps to scenes by position in the loaded list (not hardcoded integers).
- Static `SCENES` array replaced with `BUILTIN_META` lookup for display metadata (symbol, description, ship status, system message).

**Launcher:**
- Vibe service card now shows three URL buttons: GM CONTROL, OBS DISPLAY, SCENE EDITOR.

**Tests:** all 54 existing tests pass (no regressions).

---

### 2026-06-08 — v2.1.1 Vibe display & editor fixes

**Version bump:** `2.1.0` → `2.1.1` in `pyproject.toml` and `CURRENT_VERSION` in `launcher/app.py`.

**Vibe — custom layer rendering (display.html):**
- `renderCustom` was a no-op (`default: break` in switch) — all custom layers (ships, radar blips, planet discs, etc.) were invisible on the OBS output.
- Implemented generic `renderCustom(ctx, W, H, layer, p)` dispatcher: dispatches on param signature (`size_factor` → cross-ship silhouette, `rx`/`ry` → ellipse, `radius_factor` → planet disc, `count` → scattered blips, `color` → point glow).
- Added `default: renderCustom(...)` to `renderLayer` switch so all unknown layer types also render.

**Vibe — custom layer rendering (editor.html):**
- Editor `renderCustom` was showing a dashed "preview not available" placeholder; not passing resolved motion params (`p`) to the function.
- Ported identical rendering logic from display.html.
- Updated `renderLayer` to pass `p` to `renderCustom` for both `case 'custom'` and `default`.

**Vibe — editor TEST button fixed:**
- Renamed "TEST ▶" → "OBS ▶" (clearer intent: sends to OBS display).
- Auto-saves the scene before sending if it has unsaved changes (previously sent the scene ID but display loaded the old server-side version, so edits were invisible on OBS).
- `saveCurrentScene()` now returns `true`/`false`; `testOnDisplay` aborts if save fails.
- Full try/catch added — errors now appear in the status bar instead of silently crashing.
- Added "↗" button next to OBS ▶ that opens `/display` in a new tab.

**Vibe — button layout shift fixed:**
- `#status` span had `min-width: 120px` with no upper bound; long messages (e.g. "SENT TO DISPLAY: crimson_vortex") caused the span to grow, compressing the flex spacer and shifting all toolbar buttons.
- Fixed: `width: 200px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;` — buttons are now stable regardless of status text length.

**Tests:** all 54 existing tests pass.

---

### 2026-06-09 — v2.2.0 Vibe scene redesign + renderer fixes

**Version bump:** `2.1.1` → `2.2.0` in `pyproject.toml` and `CURRENT_VERSION` in `launcher/app.py`.

**All 12 builtin scenes redesigned** for table projection (top-down RPG background):
- Reworked around slow parallax motion and radial/centred compositions that read from any seat.
- Each scene given a distinct colour identity and structure — no two share the "warm glow on black" gestalt.
- THE HIVE (acid-green biolum, resin downflows) and THE NEST (blood-red throne + purple canopy, egg cluster) fully differentiated — previously near-identical.
- SOLAR APPROACH rebuilt as a concentric, full-frame churning white-hot star (twin plasma vortices, prominence arcs, white core, no stars/no black).
- BLOOD ORBIT rebuilt as an orbital horizon — cold star-filled black space with the curved dark-red bulk of LV-426 rising across the bottom and a glowing atmospheric limb. Structurally opposite to Solar.
- MOTION TRACKER cleaned to the iconic green scope (range rings, bearing ticks, sweep, contacts); removed the messy circuit traces.

**Renderer enhancements (display.html + editor.html):**
- `custom` planet disc now accepts `color_lit` / `color_mid` / `color_dark` and an optional atmospheric `limb_color` / `limb_width`, so each scene's planet/star reads with its own palette.
- `radar_sweep` reworked: angle driven directly from `t` × `sweep_speed` (no longer dependent on a motion expression resolving), shorter default trail, bold glowing leading edge scaled to canvas size + bright tip blip, brighter fading wedge. Fixes the sweep appearing frozen on a projector.

**Scene-shadow gotcha documented:** `SceneStore.get()` reads the custom data-dir copy before the builtin source. The editor's OBS auto-save had written shadow copies of crimson_vortex / solar_approach / derelict / blood_orbit to `~/Library/Application Support/MissionControl/vibe/scenes/`, which silently overrode builtin edits. Stale shadows cleared. Previewing from the GM Control panel never writes shadows; the editor's OBS ▶ only shadows a scene with unsaved edits.

**Tests:** all 54 pass.

---

### 2026-06-09 — Sound editor Phase 1: soundbank model (WIP, unreleased)

First slice of the planned soundboard editor (mirrors the vibe scene store's builtin-vs-custom shadowing). No converter/editor SPA yet — that's Phases 2–3.

- **`repository.py`** refactored: scanning logic extracted into a pure `scan_categories(root, category_order)` function; `SoundLibrary` class removed.
- **`bank_store.py`** (new): `BankStore` — active-bank-aware library. Builtin bank (`heart_of_darkness`) synthesised by scanning the shipped sounds dir; custom banks live in `data_dir/soundboard/banks/<id>/bank.json`; a custom bank with the builtin's id shadows it. Active pointer persisted to `data_dir/soundboard/active_bank.json`. Exposes `categories()`/`refresh()` (drop-in for the old library) plus `list_banks`/`get_bank`/`set_active`/`active_root`/`create_bank`/`delete_bank`.
- **`app.py`**: wires `BankStore` as `app.state.library`.
- **`routes.py`**: `/audio/<path>` now resolves against the **active bank's root** (not a fixed sounds dir); `/sounds.json` + `/api/sounds` reflect the active bank; `/state` snapshot gains a `_bank` field (poll-based bank-switch signal — soundboard is poll-based, not SSE). New: `GET /api/banks`, `GET /api/banks/{id}`, `POST /api/banks/{id}/activate`.
- **`control.html`**: SOUNDBANK selector in the sidebar; switching activates the bank and reloads the board; the 1 Hz `/state` poll detects external bank switches (via `_bank`) and reloads.
- **Tests:** 61 pass (was 54; +7 bank tests — list/manifest/activate/custom-switch/shadow/create-delete; `test_state` updated for `_bank`). `/sounds.json` contract preserved when the builtin bank is active.

**Next (Phase 2):** vendor + bundle + codesign ffmpeg; `audio_ingest` converter (Opus + −16 LUFS, async jobs); upload endpoint that ingests into a bank.

---

### 2026-06-09 — Sound editor Phase 2: converter + ingest (WIP, unreleased)

The upload/conversion pipeline. Every uploaded sound is transcoded to Opus/.ogg and loudness-normalised to −16 LUFS so a bank plays at a consistent level.

- **`paths.py`**: `ffmpeg_path()`/`ffprobe_path()` resolve a vendored/bundled binary first (`vendor/ffmpeg/` in dev, `_MEIPASS/ffmpeg/` frozen), then fall back to system PATH. A Finder-launched .app has no Homebrew on PATH, so the bundled copy is what makes the shipped converter work.
- **`audio_ingest.py`** (new): `convert_and_normalize(data, filename, kind, settings)` → `(ogg_bytes, lufs, peak)` via `ffmpeg -af loudnorm=I=-16:TP=-1.5:LRA=11 -c:a libopus -b:a {96|128}k`; `analyze_loudness()` parses loudnorm JSON for measured LUFS/peak. `ConverterUnavailable` / `ConversionError`; `converter_available()` for graceful degradation.
- **`bank_store.py`**: `ensure_writable()` forks the builtin copy-on-write (copies its audio + synthesises a manifest) so editing the shipped bank creates a complete custom shadow; `add_sound()` writes the .ogg + appends a manifest entry (name/category/kind/lufs/peak).
- **`routes.py`**: `POST /api/banks` (create), `DELETE /api/banks/{id}`, `POST /api/banks/{id}/upload` (multipart `files`+`category`+`kind` → convert in a threadpool → ingest; returns `{added, errors}`; 503 if no converter). Fixed an UploadFile isinstance pitfall (fastapi vs starlette class identity) by duck-typing non-string form values.
- **Build scaffolding**: `scripts/fetch_ffmpeg.sh` (best-effort vendor of arm64 static ffmpeg/ffprobe, non-fatal), `mission_control.spec` conditionally bundles them to `_MEIPASS/ffmpeg/`, `build.sh` fetches before PyInstaller and **codesigns** the nested binaries after (hardened-runtime requirement). `vendor/` gitignored.
- **Tests:** 66 pass (+5: converter→Opus and upload→ingest gated on ffmpeg present; add_sound; builtin fork-on-edit; create-bank API). Real conversion verified: a test tone ingests at −15.95 LUFS.

**Verification gap:** the bundled+codesigned ffmpeg path can't be confirmed without a real `build.sh` run that actually vendors an arm64 static binary — to validate at the next release. Dev works via Homebrew ffmpeg today.

**Next (Phase 3):** the editor SPA — bank/category/sound CRUD, waveform + preview, per-sound metadata, drag-drop upload with progress, test-on-output; launcher SOUND EDITOR button.

---

### 2026-06-09 — Sound editor Phase 3: editor SPA (WIP, unreleased)

The browser editor at `/editor` (port 8765), mirroring the vibe editor's green three-panel layout, tailored to audio.

- **`templates/editor.html`** (new): top bar (bank selector, NEW / DELETE / ● GO LIVE, status); left category list with counts; centre sound list (per row: preview ▶, name, kind, measured-LUFS chip that flags >3 LUFS off target, delete) plus a drag-drop / file-input upload zone with category + kind selectors and progress; right properties panel (per-sound name/category/kind/volume/loop + SAVE + ▶ OUTPUT, and bank name/description + SAVE). Local preview streams from the bank-scoped audio endpoint so any bank can be auditioned without going live.
- **`bank_store.py`**: `update_sound` (rename/recategorise/volume/loop/kind — category change re-tags only, since grouping follows the manifest, no file move), `remove_sound`, `update_bank` (name/description/category_order), `bank_file` (read-only resolve for preview, no fork).
- **`routes.py`**: `GET /editor`; `POST /api/banks/{id}/meta`; `POST /api/banks/{id}/sounds` (patch); `DELETE /api/banks/{id}/sounds?path=`; `GET /api/banks/{id}/audio/{path}` (bank-scoped range stream for preview of any bank).
- **Launcher**: soundboard card now has a third button, SOUND EDITOR (the editor page now exists).
- **Tests:** 70 pass (+4: editor page renders; edit+delete sound incl. manifest-driven regrouping; bank meta; bank-scoped preview of a non-active bank).

The sound editor is now functional end-to-end in dev (create bank → upload+convert → edit metadata → go live → switches the control board). **Phase 4 (advanced)** remains: bulk normalize + report, waveform trim/fade, tags/search, `.sndbank` import/export, hotkeys; plus the ffmpeg-bundle verification on a real build before shipping.

---

### 2026-06-09 — Sound editor Phase 4: portability + loudness tools (WIP, unreleased)

Bank portability and the "keep everything at one level" tools.

- **Export / import `.sndbank`**: `GET /api/banks/{id}/export` (zip of bank.json + audio), `POST /api/import` (zip → new custom bank with a fresh id; zip-slip-guarded via safe_join). `bank_store.import_bank()` + `write_sound_bytes()`.
- **Loudness tools**: `POST /api/banks/{id}/analyze` measures every sound (read-only — no fork, works on the builtin) and returns a report flagging anything >2 LUFS off target; `POST /api/banks/{id}/normalize` re-encodes only the sounds that drift beyond a threshold back to −16 LUFS and reports what changed.
- **Editor UI**: EXPORT / IMPORT buttons, 📊 ANALYZE (fills in measured-LUFS chips) and ⇄ NORMALIZE in the centre header, plus a live search filter over the sound list.
- **Tests:** 73 pass (+3: export→import round-trip serves identical audio; analyze is read-only / doesn't fork the builtin; normalize of an already-normalised tone is a clean no-op). E2E verified: upload→−15.95 LUFS, analyze report, 9.5 KB .sndbank export→import.

**Sound editor functional across Phases 1–4** (banks, convert-on-upload, edit, go-live, portability, loudness). **Deferred to a later 4b:** waveform trim/fade, per-sound tags, hotkey/Stream-Deck mapping, and player-side music/SFX ducking. **Pre-ship task:** verify the bundled+codesigned ffmpeg path with a real build.sh run (dev uses Homebrew ffmpeg).

---

### 2026-06-09 — v2.3.0 RELEASE — Soundbank editor

Version `2.2.0` → `2.3.0` (`pyproject.toml`, `CURRENT_VERSION`, spec `CFBundleShortVersionString`/`Version`). Ships the soundbank editor (Phases 1–4).

- **Editor ALL-filter fix:** `buildCats()` treated the ALL selection (`selCat=null`) as "unset" and snapped back to the first category, so ALL never showed Music Cues / the full list. Now `undefined` = unset (default to first category on load), `null` = explicit ALL.
- **ffmpeg bundle VERIFIED:** `scripts/fetch_ffmpeg.sh` vendored arm64 static ffmpeg/ffprobe 7.1.1; the build bundled them to `Contents/Frameworks/ffmpeg/` and codesigned them (`valid on disk` / `satisfies its Designated Requirement`). `_MEIPASS == Contents/Frameworks` confirmed, so `paths.vendor_dir()` resolves them in the frozen app — the converter works in the shipped `.app`, not just dev.
- **73 tests pass.** Build + codesign clean.

Deferred to a later 4b: waveform trim/fade, per-sound tags, hotkey/Stream-Deck mapping, player-side music/SFX ducking.
