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
