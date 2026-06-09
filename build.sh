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

# ── 3. Vendor ffmpeg/ffprobe (best-effort; converter stays off if unavailable) ─
echo "[build] Vendoring ffmpeg/ffprobe..."
bash "$ROOT/scripts/fetch_ffmpeg.sh"
echo ""

# ── 4. PyInstaller ───────────────────────────────────────────────────────────
echo "[build] Running PyInstaller..."
cd "$ROOT"
"$VENV/bin/python" -m PyInstaller mission_control.spec --noconfirm

# ── 5. Codesign bundled binaries ─────────────────────────────────────────────
# Under the hardened runtime a Finder-launched app cannot spawn unsigned nested
# binaries. Ad-hoc sign ffmpeg/ffprobe (and re-sign the app) for local use.
# Set CODESIGN_ID to a Developer ID to notarize for distribution.
APP="$ROOT/dist/Mission Control.app"
SIGN_ID="${CODESIGN_ID:--}"
if [ -d "$APP" ]; then
    while IFS= read -r bin; do
        echo "[build] codesign $bin"
        codesign --force --timestamp=none -s "$SIGN_ID" "$bin" 2>/dev/null || true
    done < <(find "$APP/Contents" -type f \( -name ffmpeg -o -name ffprobe \))
    # Re-sign the bundle so the new nested signatures are sealed in.
    codesign --force --deep -s "$SIGN_ID" "$APP" 2>/dev/null || true
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Build complete → dist/Mission Control.app               ║"
echo "╚══════════════════════════════════════════════════════════╝"
