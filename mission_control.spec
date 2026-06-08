# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Mission Control v2.

Run via build.sh (which runs tests first). Do not run PyInstaller directly
during development — use `python -m mission_control` instead.
"""
import os
from pathlib import Path

ROOT = Path(os.path.abspath("."))
SRC  = ROOT / "src" / "mission_control"
V1   = Path(os.path.expanduser("~/alien-mission-control"))  # v1 asset source until v2 asset pipeline is ready

# ── bundled data ─────────────────────────────────────────────────────────────
# Templates are inside the package and collected via collect_data_files below.
# Binary user assets (sounds, map cache) are bundled at their v1 locations so
# the frozen resolved_sounds_dir / resolved_map_cache_dir paths work correctly.
datas = [
    # App icon
    (str(ROOT / "assets" / "alien_avatar.png"),   "assets"),
    (str(ROOT / "assets" / "AlienMissionControl.icns"), "assets"),

    # Bundled sounds and map cache.
    # Resolved frozen paths: _MEIPASS/soundboard/sounds, terminal/sounds, map/cache.
    # Pointing at v1 library for now; replace once v2 has its own asset pipeline.
    (str(V1 / "SOUNDBOARD" / "sounds"), "soundboard/sounds"),
    (str(V1 / "TERMINAL"  / "sounds"), "terminal/sounds"),
    (str(V1 / "MAP"       / "cache"),  "map/cache"),
]

# Collect all package data (templates, static, shared_static) from the
# installed package. This captures every file under src/mission_control/.
from PyInstaller.utils.hooks import collect_data_files
datas += collect_data_files("mission_control", includes=["**/*.html", "**/*.css", "**/*.js", "**/*.woff2", "**/*.png", "**/*.json"])

# ── hidden imports ───────────────────────────────────────────────────────────
# FastAPI/Starlette/uvicorn use dynamic imports that PyInstaller can't trace.
hidden = [
    # FastAPI + Starlette
    "fastapi", "fastapi.middleware", "fastapi.middleware.cors",
    "starlette", "starlette.middleware", "starlette.middleware.cors",
    "starlette.responses", "starlette.staticfiles", "starlette.templating",
    "starlette.routing",
    # Uvicorn
    "uvicorn", "uvicorn.main", "uvicorn.config", "uvicorn.lifespan.on",
    "uvicorn.protocols.http.h11_impl", "uvicorn.protocols.http.httptools_impl",
    "uvicorn.loops.asyncio", "uvicorn.loops.uvloop",
    # Pydantic v2 + settings
    "pydantic", "pydantic.v1", "pydantic_core",
    "pydantic_settings",
    # Jinja2
    "jinja2", "markupsafe",
    # python-multipart (uploads)
    "multipart",
    # anyio backend
    "anyio", "anyio._backends._asyncio",
    # mission_control services (dynamic imports in supervisor)
    "mission_control.services.soundboard.app",
    "mission_control.services.terminal.app",
    "mission_control.services.vibe.app",
    "mission_control.services.map.app",
]

a = Analysis(
    [str(SRC / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "PIL", "pytest", "httpx"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Mission Control",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    target_arch="arm64",
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Mission Control")

app = BUNDLE(
    coll,
    name="Mission Control.app",
    icon=str(ROOT / "assets" / "AlienMissionControl.icns"),
    bundle_identifier="com.pavelklus.alien.missioncontrol.v2",
    info_plist={
        "CFBundleName":              "Mission Control",
        "CFBundleDisplayName":       "Mission Control",
        "CFBundleShortVersionString": "2.0.1",
        "CFBundleVersion":           "2.0.1",
        "NSHighResolutionCapable":   True,
        "LSMinimumSystemVersion":    "11.0",
    },
)
