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
- **Pattern validated.** Stopped before porting Terminal/Vibe/Map — awaiting user review of the Soundboard reference implementation.
