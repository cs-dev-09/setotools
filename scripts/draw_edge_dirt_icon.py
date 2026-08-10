"""Draw seto_tools/icons/edge_dirt.png in the style of the others.

32x32, pure white RGB, the art carried entirely by alpha - matching what
fake_ao.png and the rest already do.

**The set is outline drawing, not solid shapes.** Every icon in `icons/` is a
thin white outline of an object, with small marks inside it where a surface
needs something said about it (fake_ao's hatching, fake_damage's chipped rim).
A filled silhouette was tried here first and stood out immediately as not
belonging.

So Edge Dirt is the L profile the tool decals - the same corner Smooth Edge and
Edge Wear draw - with grains along the inside of the crease, largest where the
two surfaces meet and thinning along both of them. That is the strip the tool
builds, and the grains are what keep it from reading as either of the other two
corner icons.
"""
import math
import os
import sys

import bpy

W = H = 32
OUT = sys.argv[-1]

buf = [0.0] * (W * H)


def put(x, y, a):
    if 0 <= x < W and 0 <= y < H:
        i = y * W + x
        buf[i] = min(1.0, max(buf[i], a))


def line(x0, y0, x1, y1, width=1.5, alpha=1.0):
    """Anti-aliased capsule from (x0,y0) to (x1,y1)."""
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    half = width / 2.0
    for y in range(H):
        for x in range(W):
            px, py = x + 0.5, y + 0.5
            t = 0.0 if length2 == 0 else ((px - x0) * dx + (py - y0) * dy) / length2
            t = min(1.0, max(0.0, t))
            d = math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))
            cover = min(1.0, max(0.0, half + 0.5 - d))
            if cover > 0:
                put(x, y, cover * alpha)


def polyline(points, width=1.5):
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        line(x0, y0, x1, y1, width=width)


def grain(cx, cy, r):
    """One speck of dirt. Small enough that a circle is all it can be."""
    for y in range(int(cy - r - 2), int(cy + r + 3)):
        for x in range(int(cx - r - 2), int(cx + r + 3)):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            cover = min(1.0, max(0.0, r + 0.5 - d))
            if cover > 0:
                put(x, y, cover)


# --------------------------------------------------------------- the L profile
# The outer face, then the inner one it is thick by: a wall standing on a
# floor, the shape every strip in this add-on runs along. The outline stops
# short of the tile edge - the frames the set was drawn with are cropped off.
polyline([(6.5, 27.5), (6.5, 5.0), (27.0, 5.0)], width=1.6)
polyline([(11.5, 27.5), (11.5, 10.0), (27.0, 10.0)], width=1.6)
line(6.5, 27.5, 11.5, 27.5, width=1.6)      # the wall's top, cut off
line(27.0, 5.0, 27.0, 10.0, width=1.6)      # the floor's far end, cut off

# -------------------------------------------------------------------- the dirt
# Grains on the inside of the crease. Placed by hand: the sizes have to fall
# away from the corner without falling away evenly, or the run reads as a
# gradient rather than as dirt.
GRAINS = [
    (14.4, 12.6, 1.30),      # in the crease, the biggest of them
    (17.6, 12.2, 0.95),      # out along the floor
    (20.4, 13.0, 1.10),
    (23.2, 12.4, 0.70),
    (25.6, 12.9, 0.55),
    (13.9, 15.8, 1.05),      # and up the wall
    (14.6, 18.9, 0.85),
    (13.7, 21.6, 1.00),
    (14.5, 24.3, 0.60),
    (17.6, 15.4, 0.65),      # one that has come away from the run. Two more
                             # were tried and read as stray pixels at 32 px.
]
for x, y, r in GRAINS:
    grain(x, y, r)

# --------------------------------------------------------------------- output
RAMP = " .:-=+*#%@"
print("\n".join("".join(RAMP[min(9, int(buf[y * W + x] * 9.999))] for x in range(W))
                for y in range(H - 1, -1, -1)))

image = bpy.data.images.new("edge_dirt", width=W, height=H, alpha=True)
pixels = []
for y in range(H):
    for x in range(W):
        pixels += [1.0, 1.0, 1.0, buf[y * W + x]]
image.pixels = pixels
image.alpha_mode = 'STRAIGHT'
image.file_format = 'PNG'

scene = bpy.context.scene
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '8'
# Standard, not the scene's view transform: AgX would wash the white out on the
# way to the file, and these icons are drawn white deliberately.
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0
image.save_render(OUT, scene=scene)

# A dark-ground preview at 8x, purely so the icon can be looked at - white line
# art on transparency is invisible against a white page.
SCALE = 8
preview = bpy.data.images.new("edge_dirt_preview", width=W * SCALE, height=H * SCALE)
ppx = []
for y in range(H * SCALE):
    for x in range(W * SCALE):
        a = buf[(y // SCALE) * W + (x // SCALE)]
        v = 0.10 + 0.90 * a
        ppx += [v, v, v, 1.0]
preview.pixels = ppx
# Never beside OUT: icons.register() loads every .png in that folder, so a
# 256 px preview dropped there would be registered as an icon.
preview.save_render(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "edge_dirt_preview.png"), scene=scene)

print("wrote", OUT, os.path.getsize(OUT), "bytes")
