"""Writing an uncompressed DDS, because GTA reads DDS and Blender cannot write one.

Blender saves PNG, TGA, EXR - nothing GTA's pipeline takes directly. Every other
tool in this add-on sidesteps that by shipping a `.dds` or by pointing at one the
user already has; Sign Glow **generates** its texture, so it has to be able to
put one on disk.

The format written is A8R8G8B8: 32 bits per pixel, no compression, no mipmaps.
That is the least clever DDS there is, and deliberately so - it is the one
variant OpenIV, CodeWalker, Sollumz and the game all read without argument, and
a halo is a smooth gradient, which is exactly what block compression ruins. The
cost is size (a 512x512 halo is 1 MB), and the answer to that is to compress it
in a texture tool afterwards if it matters.

Two details that are easy to get wrong and invisible when you do:

  * **DDS stores its rows top-down**, Blender's pixel buffer is bottom-up. The
    rows are flipped here; forget it and every texture is upside down, which on
    a symmetrical halo looks *almost* right.
  * **The channel order is BGRA**, not RGBA. Getting that wrong swaps red and
    blue - and a blue sign glow that should be orange reads as a colour-picker
    bug rather than a byte-order one.

`encode()` takes plain numbers and returns bytes, so it can be checked without
Blender in the loop.
"""

import struct

import numpy as np

# Header flags: CAPS | HEIGHT | WIDTH | PITCH | PIXELFORMAT.
_HEADER_FLAGS = 0x0000100F
# Pixel-format flags: RGB | ALPHAPIXELS - i.e. "uncompressed, and the alpha
# channel means something".
_PF_FLAGS = 0x41
_CAPS_TEXTURE = 0x1000


def encode(width, height, pixels):
    """Return the bytes of an A8R8G8B8 .dds file.

    `pixels` is a flat float sequence in Blender's own layout: RGBA per pixel,
    bottom row first, values 0-1. Anything outside that range is clamped rather
    than wrapped, because a halo built from several blurred layers can overshoot
    1.0 and a wrapped highlight comes out as a black hole in the middle of it.
    """
    flat = np.asarray(pixels, dtype=np.float32)
    expected = width * height * 4
    if flat.size != expected:
        raise ValueError(
            f"expected {expected} floats for {width}x{height} RGBA, got {flat.size}")

    rows = np.clip(flat.reshape(height, width, 4), 0.0, 1.0)
    quantised = (rows * 255.0 + 0.5).astype(np.uint8)
    top_down = quantised[::-1]
    bgra = np.ascontiguousarray(top_down[..., [2, 1, 0, 3]])

    header = bytearray()
    header += b'DDS '
    header += struct.pack('<I', 124)            # dwSize, always 124
    header += struct.pack('<I', _HEADER_FLAGS)
    header += struct.pack('<I', height)
    header += struct.pack('<I', width)
    header += struct.pack('<I', width * 4)      # pitch: one row of 32-bit pixels
    header += struct.pack('<I', 0)              # depth
    header += struct.pack('<I', 0)              # mipmap count
    header += b'\x00' * 44                      # dwReserved1[11]
    header += struct.pack('<I', 32)             # pixel-format size
    header += struct.pack('<I', _PF_FLAGS)
    header += struct.pack('<I', 0)              # fourCC - none, it is uncompressed
    header += struct.pack('<I', 32)             # bits per pixel
    header += struct.pack('<I', 0x00FF0000)     # red mask
    header += struct.pack('<I', 0x0000FF00)     # green mask
    header += struct.pack('<I', 0x000000FF)     # blue mask
    header += struct.pack('<I', 0xFF000000)     # alpha mask
    header += struct.pack('<I', _CAPS_TEXTURE)
    header += b'\x00' * 16                      # caps2-4 and dwReserved2

    return bytes(header) + bgra.tobytes()


def write_image(image, filepath):
    """Write a Blender image to `filepath` as .dds. Returns the path written.

    The image is *not* repointed at the file here. Whether the datablock should
    become a file reference is the caller's decision - Sign Glow does want that
    (Sollumz embeds what the image points at), but a plain "save a copy" does
    not, and doing it silently would replace a packed image with a path that
    might be on a drive the .blend never sees again.
    """
    width, height = image.size
    buffer = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(buffer)
    with open(filepath, 'wb') as handle:
        handle.write(encode(width, height, buffer))
    return filepath
