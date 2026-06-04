#!/usr/bin/env python3
"""Build a rounded, macOS-style .icns from the alien face art."""
import os, subprocess, tempfile, shutil
from PIL import Image, ImageDraw, ImageOps, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "alien_face_src.png")
OUT_PNG = os.path.join(HERE, "appicon_rounded_1024.png")
OUT_ICNS = os.path.join(HERE, "AlienMissionControl.icns")

S = 1024
MARGIN = 100                      # transparent margin (Apple grid)
TILE = S - 2 * MARGIN            # 824 content tile
RAD = int(TILE * 0.2237)         # continuous-corner radius

# cover-crop the art into the square tile
art = Image.open(SRC).convert("RGB")
art = ImageOps.fit(art, (TILE, TILE), method=Image.LANCZOS)

# slight darkening at the very edges so the rounded form reads cleanly
vig = Image.new("L", (TILE, TILE), 0)
ImageDraw.Draw(vig).rounded_rectangle([0, 0, TILE-1, TILE-1], radius=RAD, fill=255)

# rounded mask (anti-aliased via 4x supersample)
ss = 4
m = Image.new("L", (TILE*ss, TILE*ss), 0)
ImageDraw.Draw(m).rounded_rectangle([0, 0, TILE*ss-1, TILE*ss-1],
                                    radius=RAD*ss, fill=255)
mask = m.resize((TILE, TILE), Image.LANCZOS)

canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
canvas.paste(art, (MARGIN, MARGIN), mask)

# subtle inner border for definition
bd = ImageDraw.Draw(canvas)
bd.rounded_rectangle([MARGIN, MARGIN, MARGIN+TILE-1, MARGIN+TILE-1],
                     radius=RAD, outline=(90, 190, 120, 110), width=3)

# soft drop shadow behind the tile (macOS-ish)
shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sd = ImageDraw.Draw(shadow)
sd.rounded_rectangle([MARGIN, MARGIN+12, MARGIN+TILE-1, MARGIN+TILE-1+12],
                     radius=RAD, fill=(0, 0, 0, 120))
shadow = shadow.filter(ImageFilter.GaussianBlur(22))
out = Image.alpha_composite(shadow, canvas)
out.save(OUT_PNG)
print("wrote", OUT_PNG)

# build iconset -> icns
tmp = tempfile.mkdtemp(suffix=".iconset")
sizes = [16, 32, 128, 256, 512]
for s in sizes:
    out.resize((s, s), Image.LANCZOS).save(os.path.join(tmp, f"icon_{s}x{s}.png"))
    out.resize((s*2, s*2), Image.LANCZOS).save(os.path.join(tmp, f"icon_{s}x{s}@2x.png"))
subprocess.run(["iconutil", "-c", "icns", tmp, "-o", OUT_ICNS], check=True)
shutil.rmtree(tmp, ignore_errors=True)
print("wrote", OUT_ICNS)
