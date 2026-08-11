"""Texel maths - how much texture a surface of this size deserves.

Pure functions, no bpy, so the whole scale is testable without a scene.

Resolution alone says nothing: a 512² sheet is generous on a doorknob and
threadbare on a warehouse floor. What matters is **texel density** - how
many texture pixels land on a metre of surface - which is `√(pixels / area)`
and is what an artist actually sees as sharpness.

Vanilla GTA is stricter here than anyone expects. Of the 601 textures in
Franklin's house, 592 are 512 or smaller on both sides - 331 of them 256,
109 of them 128 - and exactly two 1024² sheets exist in the whole
interior. Run the shipped tool over it at a target of **1024** and its
meshes come out at a median of 0.42× and a p75 of 0.90×, the same shape
the triangle budget has, on purpose: the two tools' colours have to mean
the same thing side by side.

The VRAM figure is deliberately an estimate and says so in the panel:
1 byte per pixel is DXT5/BC3, and the ×1.33 is the mip chain. DXT1 halves
it. It is there to turn "340 megapixels" into a number a server owner can
compare against a streaming budget, not to be exact.
"""

import math

BYTES_PER_PIXEL = 1.0        # DXT5/BC3; DXT1 is half this
MIP_FACTOR = 4.0 / 3.0       # a full mip chain adds a third


def texel_density(pixels, area):
    """Texture pixels per metre of surface, or None with nothing to measure."""
    if area <= 1e-9 or pixels <= 0:
        return None
    return math.sqrt(pixels / area)


def ratio(pixels, area, target):
    """How many times the target texel density this surface carries."""
    density = texel_density(pixels, area)
    if density is None or target <= 0:
        return None
    return density / target


def suggested_size(area, target):
    """The square texture that would hit `target` on `area` m², rounded down
    to a power of two - what to say instead of "this is too big"."""
    if area <= 1e-9:
        return 0
    ideal = math.sqrt(area) * target
    if ideal < 8:
        return 8
    return 2 ** int(math.floor(math.log(ideal, 2)))


def vram_bytes(pixels):
    """Rough VRAM cost of `pixels` texture pixels, mips included."""
    return pixels * BYTES_PER_PIXEL * MIP_FACTOR


def format_bytes(count):
    if count >= 1024 * 1024:
        return f"{count / 1024 / 1024:.1f} MB"
    if count >= 1024:
        return f"{count / 1024:.0f} KB"
    return f"{count:.0f} B"
