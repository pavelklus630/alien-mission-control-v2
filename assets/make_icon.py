#!/usr/bin/env python3
"""Generate alien_icon.png using only stdlib."""
import struct, zlib, math, base64

SIZE = 128

def png(pixels):
    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = b''.join(b'\x00' + bytes([v for px in row for v in px]) for row in pixels)
    return b'\x89PNG\r\n\x1a\n' + \
           chunk(b'IHDR', struct.pack('>IIBBBBB', SIZE, SIZE, 8, 6, 0, 0, 0)) + \
           chunk(b'IDAT', zlib.compress(raw, 9)) + \
           chunk(b'IEND', b'')

def clamp(v): return max(0, min(255, int(v)))
def lerp(a, b, t): return a + (b - a) * t

W = SIZE
H = SIZE
cx = W / 2
cy = H / 2

pixels = [[(5, 5, 5, 255)] * W for _ in range(H)]

def set_px(x, y, r, g, b, a=255):
    if 0 <= x < W and 0 <= y < H:
        br, bg, bb, ba = pixels[y][x]
        fa = a / 255
        pixels[y][x] = (clamp(br + r * fa), clamp(bg + g * fa), clamp(bb + b * fa), 255)

# Background: very dark, slight radial glow
for y in range(H):
    for x in range(W):
        dx, dy = (x - cx) / (W * 0.5), (y - cy) / (H * 0.5)
        d = math.sqrt(dx*dx + dy*dy)
        glow = max(0, 1 - d) * 18
        pixels[y][x] = (clamp(5 + glow * 0.3), clamp(5 + glow), clamp(5 + glow * 0.3), 255)

# Draw filled ellipse with anti-alias softness
def draw_ellipse(ecx, ecy, rx, ry, r, g, b, base_a=220, soft=3.0):
    x0, x1 = int(ecx - rx - soft - 1), int(ecx + rx + soft + 2)
    y0, y1 = int(ecy - ry - soft - 1), int(ecy + ry + soft + 2)
    for y in range(y0, y1):
        for x in range(x0, x1):
            dx = (x - ecx) / rx
            dy = (y - ecy) / ry
            dist = math.sqrt(dx*dx + dy*dy)
            if dist < 1.0:
                alpha = base_a
            elif dist < 1.0 + soft / min(rx, ry):
                t = (dist - 1.0) / (soft / min(rx, ry))
                alpha = base_a * (1 - t)
            else:
                continue
            set_px(x, y, r, g, b, int(alpha))

# XENOMORPH HEAD SHAPE
# Outer elongated skull – tall oval, narrower at bottom
skull_cx = cx
skull_cy = cy - 4
skull_rx = W * 0.28
skull_ry = H * 0.40

# Outer green glow (large, dim)
draw_ellipse(skull_cx, skull_cy, skull_rx * 1.55, skull_ry * 1.3, 0, 80, 10, base_a=45, soft=12.0)
draw_ellipse(skull_cx, skull_cy, skull_rx * 1.25, skull_ry * 1.1, 0, 110, 15, base_a=60, soft=8.0)

# The skull body (dark fill first)
draw_ellipse(skull_cx, skull_cy, skull_rx, skull_ry, 8, 22, 10, base_a=255, soft=2.0)

# Skull rim highlight (bright green edge)
draw_ellipse(skull_cx, skull_cy, skull_rx, skull_ry, 30, 180, 50, base_a=100, soft=1.5)
draw_ellipse(skull_cx, skull_cy, skull_rx * 0.95, skull_ry * 0.95, 5, 12, 6, base_a=255, soft=2.0)

# Inner face cavity (darker elongated oval, offset slightly up)
face_cx = skull_cx
face_cy = skull_cy + 2
face_rx = skull_rx * 0.58
face_ry = skull_ry * 0.62
draw_ellipse(face_cx, face_cy, face_rx, face_ry, 0, 5, 2, base_a=210, soft=2.5)

# Cranial ridge lines (horizontal across the top of the skull)
def draw_ridge(y_frac, alpha):
    y = int(skull_cy - skull_ry * y_frac)
    # calculate width at this y
    dy_norm = (y - skull_cy) / skull_ry
    if abs(dy_norm) >= 1: return
    half_w = skull_rx * math.sqrt(max(0, 1 - dy_norm * dy_norm))
    x0 = int(skull_cx - half_w * 0.82)
    x1 = int(skull_cx + half_w * 0.82)
    for x in range(x0, x1 + 1):
        set_px(x, y,     0, 200, 50, alpha)
        set_px(x, y + 1, 0, 120, 30, alpha // 2)

for i, (frac, alph) in enumerate([(0.72, 160), (0.55, 130), (0.38, 110), (0.22, 90)]):
    draw_ridge(frac, alph)

# Eye sockets: two small dark ovals with amber glow
for ex_off in [-0.28, 0.28]:
    ex = skull_cx + skull_rx * ex_off
    ey = skull_cy - skull_ry * 0.10
    # amber glow
    draw_ellipse(ex, ey, skull_rx * 0.14, skull_ry * 0.10, 200, 120, 0, base_a=90, soft=4.0)
    # dark socket
    draw_ellipse(ex, ey, skull_rx * 0.10, skull_ry * 0.07, 0, 0, 0, base_a=230, soft=1.5)
    # amber centre spark
    draw_ellipse(ex, ey, skull_rx * 0.04, skull_ry * 0.03, 255, 180, 0, base_a=200, soft=1.0)

# Inner teeth / jaw line at the bottom of face cavity
jaw_y = int(face_cy + face_ry * 0.55)
for i in range(-3, 4):
    tx = int(face_cx + i * face_rx * 0.22)
    for ty in range(jaw_y, jaw_y + int(face_ry * 0.18)):
        set_px(tx, ty, 0, 160, 40, 120)

# Save PNG
data = png(pixels)
with open('alien_icon.png', 'wb') as f:
    f.write(data)

b64 = base64.b64encode(data).decode()
print(f"ICON_B64 = '{b64}'")
print(f"\nIcon saved: alien_icon.png ({len(data)} bytes)")
