"""The add-on's own panel icons.

Blender's built-in icon names are all this used to draw, and two tools ended up
sharing one: Fake Damage and Smooth Edge both had MOD_EDGESPLIT, which made the
two hardest tools to tell apart look identical in a collapsed tab. There is no
built-in icon for "chipped corner" or "dirt brushed onto a wall", so the icons
now ship with the add-on.

They are 32x32 PNGs, which is exactly the size Blender draws an icon at: giving
it a larger image only means Blender rescales it with its own filter. Loaded
through `bpy.utils.previews`, the same mechanism the decal and dirt thumbnails
use, so nothing is added to `bpy.data.images` and no icon can end up referenced
by a material or exported.

Unlike a built-in icon, a custom one is not tinted by the theme - what is in
the PNG is what is drawn. That is why they are mid-grey with one warm accent
rather than near-white: near-white vanishes on a light theme.
"""

import os

import bpy.utils.previews

_collection = None

FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "icons")


def get(name):
    """Icon id for `<name>.png`, or 0 when it is missing.

    0 is Blender's "no icon" and draws nothing, so a missing file costs a blank
    header rather than a traceback in the middle of a redraw.
    """
    if _collection is None:
        return 0
    preview = _collection.get(name)
    return preview.icon_id if preview is not None else 0


def draw_header(layout, name, fallback):
    """Draw a panel header icon, falling back to a built-in one.

    The fallback matters for a source checkout with the icons folder missing,
    and for any Blender that refuses to load one - a panel with no icon at all
    is hard to tell from a panel that failed to register.
    """
    icon_id = get(name)
    if icon_id:
        layout.label(text="", icon_value=icon_id)
    else:
        layout.label(text="", icon=fallback)


def register():
    global _collection
    if _collection is not None:
        return
    _collection = bpy.utils.previews.new()
    try:
        names = sorted(os.listdir(FOLDER))
    except OSError:
        return
    for filename in names:
        stem, extension = os.path.splitext(filename)
        if extension.lower() != ".png":
            continue
        try:
            _collection.load(stem, os.path.join(FOLDER, filename), 'IMAGE')
        except Exception:
            # A corrupt or unreadable file costs that one icon, not the add-on.
            pass


def unregister():
    global _collection
    if _collection is not None:
        bpy.utils.previews.remove(_collection)
        _collection = None
