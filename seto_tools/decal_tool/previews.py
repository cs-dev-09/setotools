"""Thumbnail previews for the selected decal texture.

Only the texture actually being looked at is ever loaded, and each one is loaded
at most once per session - a library with hundreds of decals costs nothing until
you click through it. Blender's preview system decodes them off the main thread,
so loading from a draw callback is the intended usage rather than a hack.

These are previews, not images: nothing is added to bpy.data.images, so this
cannot affect what a decal material points at or what gets exported.
"""

import os

import bpy.utils.previews

_collection = None

# Paths that failed to load, so a broken or unsupported file is not retried on
# every single redraw.
_failed = set()


def get_icon_id(path):
    """Preview icon id for the image at `path`, or 0 when unavailable."""
    if _collection is None or not path or path in _failed:
        return 0
    if not os.path.isfile(path):
        _failed.add(path)
        return 0

    preview = _collection.get(path)
    if preview is None:
        try:
            preview = _collection.load(path, path, 'IMAGE')
        except Exception:
            # Unsupported format (some .dds variants), unreadable file, or a
            # name clash - none of which is worth interrupting a redraw over.
            _failed.add(path)
            return 0
    return preview.icon_id


def is_loaded(path):
    """True if `path` has been loaded into the preview cache.

    Separate from get_icon_id() because Blender only renders preview icons when
    there is a UI: in background mode a perfectly good preview still reports an
    icon_id of 0, so "did it load" and "does it have an icon yet" are different
    questions.
    """
    return _collection is not None and _collection.get(path) is not None


def failed_to_load(path):
    return path in _failed


def forget(path=None):
    """Drop a cached preview (or all of them) so the next draw reloads it."""
    if _collection is None:
        return
    if path is None:
        _collection.clear()
        _failed.clear()
    else:
        if path in _collection:
            del _collection[path]
        _failed.discard(path)


def register():
    global _collection
    if _collection is None:
        _collection = bpy.utils.previews.new()


def unregister():
    global _collection
    if _collection is not None:
        bpy.utils.previews.remove(_collection)
        _collection = None
    _failed.clear()
