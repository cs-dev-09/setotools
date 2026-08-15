"""Finding a bundled texture again after the add-on has moved.

The textures the strip tools ship with live inside the add-on, and Blender
records where an image came from as an **absolute path** - so a scene saved
today says, in as many words,
`.../scripts/addons/seto_tools/fake_ao/textures/tl_v_office_shadow.dds`.

That is fine until the add-on is not there any more. Two things move it:

  * **an update**, which deletes the folder and writes it again. Blender is
    holding the file open, so textures go pink until it is restarted and reads
    them from the path a second time - which is why the docs say to restart;
  * **the rename to `void_tools`, and installing as an extension**, both of
    which change the path for good. Nothing brings those back on its own: the
    scene keeps asking for a folder that no longer exists, and restarting
    Blender does not help because the answer really is gone.

So the path is repaired on load. An image is only touched when all three hold:

  1. it is missing - a file that opens is never second-guessed;
  2. its path ends in `<something>/textures/<file>`, the shape our tools use;
  3. **that exact relative path exists inside this add-on.** This is what makes
     it safe: the only file it can ever point an image at is one we ship, so a
     missing texture belonging to some other add-on cannot be captured by it.

It repairs the *image datablock*, never the file. Nothing here writes to disk.
"""

import os
import re

import bpy
from bpy.app.handlers import persistent

# The add-on's own directory - shared/ is one level in.
_PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# `<tool>/textures/<file>`, with either separator, because a path saved on
# Windows is read on macOS and the other way round.
_BUNDLED = re.compile(r"([^\\/]+)[\\/]textures[\\/]([^\\/]+)$")


def _shipped_equivalent(missing_path):
    """Where this texture lives in the add-on now, or None."""
    match = _BUNDLED.search(missing_path)
    if match is None:
        return None
    tool, filename = match.groups()
    candidate = os.path.join(_PACKAGE, tool, "textures", filename)
    return candidate if os.path.isfile(candidate) else None


def repair_all():
    """Re-point every missing bundled texture. Returns the images repaired."""
    repaired = []
    for image in bpy.data.images:
        if image.source != 'FILE' or not image.filepath:
            continue
        try:
            current = bpy.path.abspath(image.filepath)
        except (ValueError, RuntimeError):
            continue
        if os.path.isfile(current):
            continue
        candidate = _shipped_equivalent(current)
        if candidate is None:
            continue
        image.filepath = candidate
        try:
            image.reload()
        except RuntimeError:
            continue        # unreadable for some other reason; leave it alone
        repaired.append(image)
    return repaired


@persistent
def _on_load(_file):
    repaired = repair_all()
    if repaired:
        # Worth a line in the console: the scene has been changed from what was
        # saved, and somebody wondering why their file is dirty deserves to be
        # able to find out.
        print(f"[Void Tools] Re-pointed {len(repaired)} bundled texture(s) at "
              f"the add-on's current location.")


def _repair_once():
    """The deferred pass over the file that was already open."""
    repair_all()
    return None                 # one shot


def register():
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)

    # The file that is already open still wants fixing - installing an update
    # does not reload it - but **not from here**. While Blender registers
    # add-ons at startup, `bpy.data` is a `_RestrictData` stand-in: reaching
    # for `bpy.data.images` raises AttributeError, register() fails, and the
    # whole add-on is dropped. The tab simply does not appear, which is how
    # this shipped in 1.2.3.
    #
    # A zero-interval timer runs the moment the event loop starts, by which
    # time the real data is there. In background Blender there is no event
    # loop and nothing to repair for a user to look at, so it never fires -
    # and that is also why the first version's `if not bpy.app.background`
    # guard kept every test from ever seeing the bug.
    bpy.app.timers.register(_repair_once, first_interval=0.0)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if bpy.app.timers.is_registered(_repair_once):
        bpy.app.timers.unregister(_repair_once)
