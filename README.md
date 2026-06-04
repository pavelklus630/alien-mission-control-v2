# Mission Control v2

Greenfield rewrite of the **Alien RPG GM toolkit** ("Mission Control") — a macOS app that runs four LAN-reachable services for running tabletop sessions:

| Service          | Port | Purpose                                  |
|------------------|------|------------------------------------------|
| Soundboard       | 8765 | Ambient/SFX playback (Opus/OGG, Range)   |
| MU/TH/UR Terminal| 8770 | In-fiction computer terminal             |
| Vibe Generator   | 8090 | Mood/visual atmosphere display           |
| Erebos Map       | 8085 | Ship/station map display                 |

Each service exposes a `/control` page (operator) and an `/output` or `/display` page (OBS Browser Source / external monitor).

> v2 is a clean-architecture rewrite of [alien-mission-control](https://github.com/pavelklus630/alien-mission-control) (v1.7.1). Status: **early development** — see [`DEVLOG.md`](DEVLOG.md).

## Status
Phase 0 (repo setup) complete. Phase 1 (analysis) next. Nothing here is runnable yet.
