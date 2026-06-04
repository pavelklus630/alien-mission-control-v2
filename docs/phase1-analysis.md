# ALIEN: Heart of Darkness — Mission Control v1.7.1
## Phase 1 Legacy Analysis Report

> Produced read-only by the `legacy-analyst` charter (run on Sonnet) against the v1 sources:
> `/Users/pavelklus/alien-mission-control` (v1.7.1 canonical) and the dev trees
> `…/CODE/DEV/V_1.6`, `…/CODE/DEV/V_1.7`. No v1 files were modified.

**Executive Summary.** Mission Control is a compact, well-crafted single-user GM toolkit. Its architecture is coherent for its purpose: four in-process Python HTTP services run as daemon threads inside a single Tkinter launcher, packaged into a self-contained macOS .app via PyInstaller. The code is clean, readable, and free of third-party runtime dependencies — everything runs on Python stdlib. The most significant structural debt is that ~200 KB of HTML/CSS/JS is baked as Python string literals inside three of the four service files, making front-end iteration slow and testing harder. There is no authentication; all four ports bind to `0.0.0.0`, which is an intentional LAN-sharing design decision but worth documenting. Path-traversal guards exist on the two services that serve arbitrary files (Soundboard, Map). The v1.7 dev tree has a solid pytest suite that the canonical release clone lacks entirely. For v2, both architecture options (four separate services vs. one unified server with four ports) are viable; this report argues that four separate services is the safer choice for this specific use case, with unified config being the primary thing worth gaining from a partial unification.

---

## 1. Architecture

### Overview

```
macOS .app (PyInstaller bundle)
└── Mission Control.app
    └── alien_launcher.py  ← Tkinter Tk mainloop (main thread)
        ├── threading.Thread → alien_soundboard.ThreadedHTTPServer  :8765
        ├── threading.Thread → alien_terminal.ThreadedHTTPServer    :8770
        ├── threading.Thread → http.server.ThreadingHTTPServer      :8090  (Vibe)
        └── threading.Thread → alien_map.ThreadedHTTPServer         :8085
```

### Tkinter Launcher (`alien_launcher.py`)

The `Launcher` class subclasses `tk.Tk`. The main thread runs Tkinter's `mainloop()`. At startup, the launcher:

1. Resolves `LAN_IP` by connecting a UDP socket to `8.8.8.8` (`alien_launcher.py:49-55`).
2. Adds `SOUNDBOARD/`, `TERMINAL/`, `VIBE/`, `MAP/` to `sys.path`, then imports all four service modules (`alien_launcher.py:62-70`).
3. Builds a Canvas-based UI with four service cards.

Service lifecycle is managed through `self.servers: dict[name, HTTPServer]`.

**Starting a service** (`alien_launcher.py:317-339`): calls `svc["module"].make_server()`, which binds the port and returns an `HTTPServer` instance without starting it. Then `srv.serve_forever(poll_interval=0.05)` is called inside a `daemon=True` thread. Port-binding errors (`OSError`) are caught and logged to a per-service `deque(maxlen=6)`.

**Stopping a service** (`alien_launcher.py:345-354`): pops the server from the dict, calls `srv.shutdown()` then `srv.server_close()` in a separate daemon thread to avoid blocking the UI.

**Status polling** (`alien_launcher.py:370-409`): A dedicated background thread (`_port_watcher`) calls `socket.create_connection("127.0.0.1", port, timeout=0.3)` every 0.8 s for all four ports. The UI redraws every 1 s (`self.after(1000, self._poll)`) by reading `self._port_online` — race-condition safe because dictionary reads of bool values are GIL-protected.

**Update checking** (`alien_launcher.py:418-507`): A daemon thread hits the GitHub releases API, downloads the new `.app` zip, extracts it via `ditto`, writes a shell script that replaces the running `.app` after `sleep 1`, and runs it with `Popen(..., start_new_session=True)` before calling `self._quit()`.

### The Four In-Process HTTP Services

All four use `http.server.ThreadingHTTPServer` (stdlib), which spawns a new daemon thread per request. Each service exports exactly one function, `make_server()`, which binds the port and returns an HTTPServer instance.

| Service | File | Port | HTML delivery | Live-update mechanism |
|---|---|---|---|---|
| Soundboard | `alien_soundboard.py` | 8765 | External `.html` files read on each request | Client polls `/state` at 1 s intervals |
| MU/TH/UR Terminal | `alien_terminal.py` | 8770 | Embedded Python string literals (2 HTML strings, ~76 KB) | Client polls `/poll?since=N` at 0.9 s |
| Vibe Generator | `alien_vibe.py` | 8090 | Embedded Python string literals (2 HTML strings, ~85 KB) | SSE (`/api/events`), polling fallback every 5 s |
| Erebos Map | `alien_map.py` | 8085 | Embedded Python string literal + external map cache files | Client polls `/api/state` at 2 s |

**Soundboard** serves `control.html` and `output.html` from `SOUNDBOARD/` via `_file()` → `path.read_bytes()` on every request (no caching). Audio is served with full HTTP Range support (chunked, 64 KB reads): `alien_soundboard.py:153-186`.

**Terminal** stores all messages in an in-process `list` protected by `threading.Lock()`. The display page polls `/poll?since=N` (cursor-based); the server returns immediately with any messages after index N — this is a classic cursor poll, not SSE or long-polling. No persistence; messages vanish on restart.

**Vibe** uses a real SSE push channel at `/api/events` (`alien_vibe.py:1355-1386`): each connected client gets a `queue.Queue(maxsize=20)`, and `_broadcast()` fans out to all queues. A `": ping\n\n"` keepalive fires every 20 s on timeout. The control page also polls `/api/scene` every 5 s as fallback. Scene state is a plain dict `{"scene": 0}` under `threading.Lock()`.

**Map** serves static map bundle files from `MAP/cache/` via `_serve_cache()`. It stores only a tiny GM-state dict (`{"title_hidden": False, "menu_hidden": False}`) and accepts POST toggling. The display page polls `/api/state` every 2 s.

**Port binding**: all four services bind `("0.0.0.0", PORT)` or `("", PORT)` — LAN-accessible by design.

---

## 2. Technologies & Dependencies

### All stdlib — zero third-party runtime dependencies

Every import across all five Python files is from the standard library:

```python
# alien_soundboard.py:4-11
import re, sys, json, threading
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
import mimetypes

# alien_terminal.py:10-16
import json, sys, time, threading
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# alien_vibe.py:6
import http.server, json, queue, sys, threading

# alien_map.py:8-11
import os, sys, json, threading, mimetypes
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# alien_launcher.py:7-10
import sys, os, time, threading, socket, webbrowser, zipfile, tempfile, subprocess
import urllib.request, json as _json
import tkinter as tk
from collections import deque
```

The test suite (dev dirs only) uses `pytest` and `requests` — build-time dependencies only.

### HTTP Server Implementation

`http.server.ThreadingHTTPServer` (Python 3.7+) is a `socketserver.ThreadingMixIn + http.server.HTTPServer`. It spawns a new daemon thread per accepted connection. Three services subclass it to set `daemon_threads = True` and `allow_reuse_address = True`:

```python
# alien_soundboard.py:36-39
class ThreadedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
```

The Vibe service does not subclass — it uses `http.server.ThreadingHTTPServer` directly with no subclass configuration. `ThreadingHTTPServer` sets `allow_reuse_address = True` by default (Python stdlib default), so this is harmless but inconsistent.

### SSE Implementation (Vibe only)

The SSE approach is in-process queue fan-out: `alien_vibe.py:1355-1386`. Each SSE connection holds a thread (one `ThreadingHTTPServer` thread per open SSE client) that blocks on `q.get(timeout=20)`.

### HTTP Range Streaming (Soundboard audio only)

Implemented manually in `alien_soundboard.py:153-186`: parses `Range: bytes=start-end`, seeks, and streams in 65 536-byte chunks. Path traversal is guarded by:

```python
# alien_soundboard.py:115-119
p = SOUNDS_DIR / unquote(path[7:])
try:
    p.resolve().relative_to(SOUNDS_DIR.resolve())
except ValueError:
    self.send_error(403)
    return
```

### PyInstaller Packaging

`mission_control.spec` builds a one-dir `.app` for macOS arm64 (`target_arch="arm64"`). The spec:

- Bundles `SOUNDBOARD/control.html`, `SOUNDBOARD/output.html`, `SOUNDBOARD/sounds/`, `TERMINAL/sounds/`, `assets/`, and `MAP/cache/` as data.
- Adds all four service dirs to `pathex` and lists them in `hiddenimports` (`mission_control.spec:22`).
- Excludes `numpy`, `PIL`, `pytest` from the bundle.
- `console=False` suppresses the terminal window on macOS.

The Soundboard HTML and all audio are external files in the bundle; Terminal, Vibe, and Map HTML is baked into the Python bytecode.

---

## 3. Weak Points, Tech Debt, and Best-Practice Violations

### 3.1 HTML baked into Python string literals

Three services embed their entire front-end as multi-thousand-line Python raw strings:

- `alien_terminal.py:38-856` — `DISPLAY_HTML` + `INPUT_HTML`, ~76 KB
- `alien_vibe.py:26-1303` — `DISPLAY_HTML` + `CONTROL_HTML`, ~85 KB
- `alien_map.py:35-453` — `DISPLAY_HTML` + `CONTROL_HTML`, ~43 KB

Consequences: no syntax highlighting for HTML/CSS/JS; Python tools lint/parse the entire file as Python; any HTML edit requires navigating ~1400-line Python files; the base64-encoded woff2 font (`Share Tech Mono`, ~54 KB) is duplicated across `alien_terminal.py:43`, `alien_map.py:296`, and the Soundboard's external HTML files — a ~150 KB total redundancy in the repository.

The Soundboard is the exception: `control.html` (72 KB) and `output.html` (23 KB) are external files served at runtime.

### 3.2 No tests in canonical release clone

The canonical repository (`alien-mission-control`) has no `tests/` directory. The dev trees (`V_1.6`, `V_1.7`) contain a full pytest suite under `tests/` with `conftest.py` fixtures, `test_soundboard.py`, `test_terminal.py`, `test_vibe.py`, `test_map.py`. The `build.sh` in dev runs tests before PyInstaller: `V_1.7/build.sh:12`. This suite never made it into the canonical release branch.

### 3.3 Polling mechanisms are inconsistent

Three different live-update patterns exist across four services:
- Soundboard: client polls `/state` (1 s)
- Terminal: cursor-based client poll `/poll?since=N` (0.9 s)
- Vibe: SSE push + 5 s polling fallback
- Map: client polls `/api/state` (2 s)

There is no justified reason for the inconsistency; it is the result of incremental development.

### 3.4 Code duplication across services

The `ThreadedHTTPServer` subclass pattern is repeated verbatim in three of four service files (`alien_soundboard.py:36-39`, `alien_terminal.py:19-21`, `alien_map.py:28-30`). CORS response headers are duplicated individually in every handler across all four services rather than using a shared helper. The `_send`, `_json`, `_html`, `_cors` helpers are independently implemented in each file with near-identical signatures.

### 3.5 Path traversal in the Terminal sound handler

The Terminal's `/sounds/<filename>` handler at `alien_terminal.py:882-920` uses `Path(path[8:]).name` to strip any directory components:

```python
# alien_terminal.py:883
self._sound(Path(path[8:]).name)
```

`Path("../../etc/passwd").name` returns `"passwd"`, so this does effectively neutralize traversal. However, it does so by a `.name`-truncation trick rather than the explicit `resolve().relative_to()` guard used in Soundboard and Map. This is functionally adequate but less explicitly documented and audit-visible.

### 3.6 Map serves entire binary files into memory

`alien_map.py:516-536` (`_serve_cache`) does `data = file_path.read_bytes()` then sends all bytes at once. The Erebos map bundle (`map-bundle.bin`) could be large. There is no Range header support, no streaming, and the entire file is held in RAM during the response. The Soundboard, by contrast, streams audio in 64 KB chunks.

### 3.7 Terminal sound files served without Range support

`alien_terminal.py:912-920` reads the full OGG into memory and sends it as one buffer. Terminal sounds are short (beeps, rattles), so this is not a practical problem, but it diverges from the Soundboard's approach and could matter if a sound file is large.

### 3.8 LAN exposure with no authentication

All four services bind `"0.0.0.0"` and have no authentication, API keys, or IP filtering. `Access-Control-Allow-Origin: *` is set on all endpoints. For a GM running at a table with a private home network, this is an intentional design trade-off (GM wants to open controls on a phone). However, the launcher documentation does not call this out explicitly, and any device on the same network can issue POST commands to change the scene, purge the terminal log, or trigger toggle state.

### 3.9 The Vibe service lacks `allow_reuse_address` and `daemon_threads` in its subclass

Vibe uses bare `http.server.ThreadingHTTPServer` without a configured subclass (`alien_vibe.py:1414`). Python's `ThreadingHTTPServer` does set `allow_reuse_address = True` by default (stdlib), so rapid restart will not fail. However, `daemon_threads` is not set, meaning that if the Vibe server is stopped while SSE clients are connected, the per-client threads will not be marked daemon — they will block `srv.shutdown()` until all SSE connections drop. Under normal use (single-user, local OBS client), this is a minor issue.

### 3.10 Shutdown race during "QUIT"

`alien_launcher.py:364-367`:
```python
def _quit(self):
    self._alive = False
    self._stop_all()
    self.after(500, self.destroy)
```

`_stop_all()` fires daemon threads to call `srv.shutdown()` and `srv.server_close()`. The `self.after(500, ...)` provides a 500 ms window. If a service is slow to shut down (e.g., Vibe with live SSE connections on non-daemon threads), `self.destroy()` is called while shutdown threads may still be running. This is unlikely to cause data loss but could produce logged errors.

### 3.11 Config as magic numbers

Ports (`8765`, `8770`, `8090`, `8085`) are hardcoded in each service file. The UI layout constants (`W=720`, `CARD_H=196`, `GAP=15`, etc.) live at the top of `alien_launcher.py:113-117`. Font choice (`Courier New`) and all palette hex colors are scattered throughout the launcher. None of these are in a shared config file or even a single `config.py`.

### 3.12 No structured logging

All services suppress HTTP access logs entirely with `log_message = lambda *_: None` (`alien_soundboard.py:86`, `alien_terminal.py:862`, `alien_map.py:472`, `alien_vibe.py:1308`). Runtime errors in service threads are caught and appended to the per-service `deque` in the launcher UI only. There is no log file, no `logging` module usage, and no way to debug crashes after the fact from a distributed `.app`.

### 3.13 `scan_sounds()` re-scans the filesystem on every `/sounds.json` request

`alien_soundboard.py:48-60`: `scan_sounds()` calls `SOUNDS_DIR.rglob("*")` on every call to `_sounds()`. Since the sound library is static (loaded once at bundle time), this is pure waste. The result should be computed once at module load time.

### 3.14 Binary assets gitignored

The `.gitignore` (`alien-mission-control/.gitignore:1-3`) excludes:
```
SOUNDBOARD/sounds/
TERMINAL/sounds/
MAP/cache/
```

This means the repository does not contain any audio files or map cache. A fresh clone produces a non-functional app. The `README` presumably documents this, but it means CI cannot run against real audio data and `_selftest()` in `alien_launcher.py` would require separately obtained assets.

### 3.15 Auto-update uses `rm -rf` on the app bundle

`alien_launcher.py:486-487`:
```python
f'rm -rf "{dest}"\n'
f'ditto "{new_app}" "{dest}"\n'
```

This shell script is written to a temp dir and executed via `/bin/bash`. If the `ditto` extraction produces a corrupted `.app` or `new_app` is `None` (caught, but the error handling path at line 477 raises `FileNotFoundError` before the script is written), the user is left without a running app. There is no backup of the old `.app` before deletion.

---

## 4. Keep vs. Rewrite

| Component | Recommendation | Reasoning |
|---|---|---|
| **alien_launcher.py** (Tkinter launcher) | **Keep / minor adapt** | Solid, well-structured; the Canvas-based UI is purposeful and distinctive. Only changes needed: extract config constants, fix quit-race, make update backup safer. |
| **Soundboard server** (`alien_soundboard.py`) | **Keep** | Cleanest service: external HTML files, Range-streaming audio, path-traversal guard, well-tested. Only debt: `scan_sounds()` should be cached. |
| **Terminal server** (`alien_terminal.py`) | **Adapt** | Python logic is correct; HTML must be extracted to external files; cursor-polling is adequate and can remain. |
| **Vibe Generator** (`alien_vibe.py`) | **Adapt** | SSE implementation is good; 1 400-line single file mixing canvas animation, CSS, HTML, and Python is unwieldy; HTML must be extracted. Fix `daemon_threads` omission. |
| **Map server** (`alien_map.py`) | **Keep / minor adapt** | Logic is simple and correct; path-traversal guard is solid. Extract HTML, add streaming for large binary files. |
| **HTML/CSS/JS front-end** | **Adapt** | Extract from Python strings into external `.html` files (mirroring the Soundboard pattern). No framework change needed. |
| **Audio pipeline** | **Keep** | Opus OGG at ~96 kbps VBR, −16 LUFS normalization, Range streaming: this is the right approach and should be preserved as-is. |
| **Packaging (PyInstaller spec)** | **Keep** | Works correctly for a macOS .app; the spec is minimal and readable. Update to bundle extracted HTML files. |
| **Asset handling (.gitignore)** | **Keep approach, improve docs** | Gitignoring binary assets is correct; add a clear README section or setup script for populating assets after clone. |
| **Tests** | **Restore from dev** | The V_1.7 test suite is good and should be merged into the canonical repo; `build.sh` pattern (test-then-build) is the right workflow. |

---

## 5. v2 Architecture Comparison

### Constraint that must hold: four ports remain

The external port numbers `8765/8770/8090/8085` are baked into OBS Browser Source configurations that the user has already set up. They must not change.

### Option A: Four separate in-process services (as today, but improved)

Each service remains a module with its own `make_server()` returning a `ThreadingHTTPServer`. The launcher starts each on its own daemon thread. This is exactly the current architecture.

**How it binds four ports:** each `ThreadingHTTPServer(("0.0.0.0", PORT), Handler)` call creates one `socket.socket`, binds it, and listens. The OS assigns the port to the process. Four separate `socket` objects exist in one Python process.

**Option A tradeoffs:**

| Dimension | Assessment |
|---|---|
| Process/fault isolation | Weak: a Python exception in one handler thread crashes that thread but leaves the process running; a segfault in any C extension would kill all four. In practice, there are no C extensions, so thread-level isolation is sufficient. |
| Shared state & config | Each service module has module-level globals (port, state dict, locks). Services cannot share state without importing each other. For v1, services are independent; this is fine. |
| Packaging (.app) | Excellent. Single PyInstaller bundle, one `alien_launcher.py` entry point. Proven and working. |
| OBS + external monitor | Each service's `/display` or `/output` URL is already a separate browser source. No change needed. |
| Hot-reload during dev | Poor: changing any service file requires restarting the launcher. |
| Testability | Good: each `make_server()` is independently testable (the V_1.7 test suite proves this). |
| Complexity | Low: the architecture is already understood. |

**What Option A gains in v2:** extracting HTML to external files, adding a shared `config.py` for ports and constants, restoring the test suite, unifying the `ThreadedHTTPServer` subclass pattern.

### Option B: Single unified server with four sub-apps, still on four ports

The four service modules become sub-applications or routers mounted under a single server object. But since OBS requires four distinct ports, the unified server must still bind four sockets. In practice, this means one of:

- **B1:** One Python process creates four `ThreadingHTTPServer` instances (same as today), but they are initialized from a shared app class, share a config object, and perhaps share a common `_send`/`_cors` mixin. This is "unified" only in code organization, not in runtime behavior.
- **B2:** A single ASGI/WSGI server (e.g., `uvicorn` with multiple `--port` bindings). But Python's async servers (uvicorn, hypercorn) do not natively bind multiple ports in one process without running multiple worker processes or separate server instances. Binding four ports still requires four server instances.
- **B3 (hypothetical):** A single asyncio event loop with four `asyncio.start_server()` coroutines listening on four ports simultaneously. This is technically feasible but requires rewriting all handlers in async Python and abandoning `ThreadingHTTPServer`.

**Option B tradeoffs:**

| Dimension | B1 (shared config, same server class) | B3 (full asyncio rewrite) |
|---|---|---|
| Process/fault isolation | Same as Option A | Marginally better (no per-request thread overhead), but asyncio errors can affect all four services in one event loop |
| Shared state & config | Explicit shared config module is the main gain | Full sharing possible, but this creates coupling risks |
| Packaging (.app) | Same as today | Adds `uvicorn`/`starlette` or `aiohttp` as runtime dependencies; increases bundle size and build complexity |
| OBS + external monitor | Unchanged | Unchanged |
| Hot-reload during dev | Could add uvicorn `--reload` per service | Natively supported by uvicorn/watchfiles |
| Testability | Same as today | Requires async test infrastructure (pytest-asyncio) |
| Complexity | Low increase | High increase |

### Recommendation for v2

**Choose Option A (four separate in-process services) with shared infrastructure.**

Justification specific to this use case:

1. **Single-user macOS GM toolkit.** High scalability, process isolation, and hot-reload infrastructure are not requirements. The app serves one GM, on one machine, serving at most 3-4 browser windows.

2. **Proven packaging path.** The PyInstaller `.app` approach works today and has no third-party runtime dependencies. Introducing `uvicorn`/`starlette`/`aiohttp` for Option B2/B3 adds PyInstaller bundling complexity, hidden import scanning, and runtime dependency management with no user-visible benefit.

3. **The primary pain points are solvable in Option A.** The key debts — HTML baked into Python strings, no shared config, no tests in canonical repo, inconsistent logging — are all addressable within the Option A structure without changing the runtime model.

4. **Four ports are already four services conceptually.** The Soundboard, Terminal, Vibe, and Map are independently useful (a GM might want only the Terminal running); keeping them as independent modules preserves this. A unified server would couple their lifetimes.

5. **What "unified" meaningfully adds:** a shared `config.py` for ports/constants, a shared `server_utils.py` for `ThreadedHTTPServer` subclass, `_send`, `_cors`, `_json` helpers, and shared `tests/conftest.py`. This is the correct scope of unification — at the code-organization level, not the runtime-architecture level.

---

## Open Questions for the User

1. **Port stability.** Are the four OBS Browser Source URLs fully committed to, or is there flexibility to change them in a v2 that updates the OBS scenes at the same time?
2. **Hot-reload priority.** How much time per session is spent restarting the launcher to test HTML/JS changes? Extracting HTML to external files may suffice, or a dev-mode watch-and-reload wrapper could be added.
3. **Sound file distribution.** How are `SOUNDBOARD/sounds/` and `TERMINAL/sounds/` distributed to new machines? This affects how the CI/test pipeline works in v2.
4. **Platform targets.** macOS arm64 only, or also x86_64 / Windows? Current spec is `target_arch="arm64"`.
5. **Vibe scenes: persistent or reset on restart?** Currently in-memory and lost on restart.
6. **Map: Erebos-only or multi-map?** Cache is `cache/maps/erebos/...`. Is multi-map a v2 target?
7. **Logging/diagnostics.** Is a log file (e.g., `~/Library/Logs/MissionControl/`) desirable, or is the in-UI deque log sufficient?

---

## Framework choice note (carried into Phase 2)

The analyst recommends **Option A**. The architect (Phase 2) should weigh this against the user's explicit Phase 2 requirement to *"use standard, well-established external libraries wherever it makes sense (FastAPI/Flask, Jinja2, pydantic, pytest)"* and the extensibility goals (uploads + future editors). Reconciling these — stdlib's zero-dependency simplicity vs. a mature framework that makes uploads/validation/templating/testing cleaner — is the central Phase 2 architecture decision to make with the user.
