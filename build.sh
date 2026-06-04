#!/bin/bash
# Mission Control v2 build script.
# Runs the full test suite first; only calls PyInstaller if tests pass.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Mission Control v2 — build                              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Ensure venv exists ────────────────────────────────────────────────────
if [ ! -f "$VENV/bin/python" ]; then
    echo "[build] Creating venv..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet -e "$ROOT/.[dev]"
fi

# ── 2. Run tests (pre-build gate) ────────────────────────────────────────────
echo "[build] Running test suite..."
"$VENV/bin/python" -m pytest -m "not slow" -q --tb=short
echo "[build] Tests passed."
echo ""

# ── 3. PyInstaller ───────────────────────────────────────────────────────────
echo "[build] Running PyInstaller..."
cd "$ROOT"
"$VENV/bin/python" -m PyInstaller mission_control.spec --noconfirm

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Build complete → dist/Mission Control.app               ║"
echo "╚══════════════════════════════════════════════════════════╝"
