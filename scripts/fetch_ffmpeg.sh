#!/bin/bash
# Vendor static arm64 macOS ffmpeg + ffprobe into vendor/ffmpeg/ for bundling.
#
# The shipped .app needs its own ffmpeg: a Finder-launched app has a minimal
# PATH (no Homebrew), so the audio converter relies on the bundled binary.
#
# This is best-effort and NON-FATAL: if it can't obtain an arm64 static binary,
# it prints guidance and exits 0 so the build still produces a working app
# (the converter just stays disabled until a binary is vendored).
#
# Override the sources with env vars if the defaults rot:
#   FFMPEG_URL=... FFPROBE_URL=... scripts/fetch_ffmpeg.sh
#
# You can also just drop arm64 static `ffmpeg` and `ffprobe` into vendor/ffmpeg/
# by hand — this script will detect and keep them.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/vendor/ffmpeg"
mkdir -p "$DEST"

# Default sources: osxexperts publishes arm64 static builds. These names change
# over time — override via env vars if the download 404s.
FFMPEG_URL="${FFMPEG_URL:-https://www.osxexperts.net/ffmpeg711arm.zip}"
FFPROBE_URL="${FFPROBE_URL:-https://www.osxexperts.net/ffprobe711arm.zip}"

have_valid() {  # $1 = path; true if an arm64 mach-o executable
    [ -x "$1" ] && file "$1" | grep -q "arm64"
}

fetch_one() {  # $1 = tool name, $2 = url
    local tool="$1" url="$2" out="$DEST/$1"
    if have_valid "$out"; then
        echo "[ffmpeg] $tool already vendored (arm64) — skipping."
        return 0
    fi
    echo "[ffmpeg] fetching $tool from $url"
    local tmp; tmp="$(mktemp -d)"
    if ! curl -fsSL "$url" -o "$tmp/dl"; then
        echo "[ffmpeg] WARNING: download failed for $tool ($url)."
        rm -rf "$tmp"; return 1
    fi
    # Accept either a raw binary or a zip containing one.
    if file "$tmp/dl" | grep -q "Zip archive"; then
        (cd "$tmp" && unzip -qo dl) || { echo "[ffmpeg] unzip failed"; rm -rf "$tmp"; return 1; }
        local bin; bin="$(find "$tmp" -type f -name "$tool" | head -1)"
        [ -n "$bin" ] || bin="$(find "$tmp" -type f -perm -u+x ! -name 'dl' | head -1)"
        [ -n "$bin" ] && mv "$bin" "$out"
    else
        mv "$tmp/dl" "$out"
    fi
    rm -rf "$tmp"
    chmod +x "$out" 2>/dev/null || true
    if have_valid "$out"; then
        echo "[ffmpeg] vendored $tool OK ($(file -b "$out" | cut -d, -f1))"
        return 0
    fi
    echo "[ffmpeg] WARNING: $tool is missing or not arm64 after fetch."
    return 1
}

ok=0
fetch_one ffmpeg  "$FFMPEG_URL"  || ok=1
fetch_one ffprobe "$FFPROBE_URL" || ok=1

if [ "$ok" -ne 0 ]; then
    echo ""
    echo "[ffmpeg] ────────────────────────────────────────────────────────────"
    echo "[ffmpeg] Could not vendor arm64 static ffmpeg/ffprobe automatically."
    echo "[ffmpeg] The build will continue WITHOUT a bundled converter."
    echo "[ffmpeg] To enable it, place arm64 static binaries here:"
    echo "[ffmpeg]   $DEST/ffmpeg"
    echo "[ffmpeg]   $DEST/ffprobe"
    echo "[ffmpeg] then re-run the build."
    echo "[ffmpeg] ────────────────────────────────────────────────────────────"
fi
exit 0
