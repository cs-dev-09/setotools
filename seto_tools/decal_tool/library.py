"""Decal library scanning and caching.

Deliberately free of bpy.data / Sollumz knowledge: this module only knows about
directories and image files on disk. Images are never loaded into Blender here -
that happens in sollumz_integration.load_image(), and only for the one texture a
material actually needs.

The library is a folder of category subfolders:

    Decals/
        Dirt/    dirt_01.png  dirt_02.png ...
        Cracks/  crack_01.png ...

Scanning is NOT done on UI redraw. The cache is refilled from exactly three
places: the addon's initial scan, the library path property's update callback,
and the "Refresh Library" operator. The enum item callbacks below only ever read
the cache, so a library with hundreds of decals costs nothing to draw.
"""

import os

# Blender can read all of these; .dds support depends on the compression format,
# which is why a load failure is reported per texture rather than up front.
IMAGE_EXTENSIONS = (".png", ".tga", ".dds", ".jpg", ".jpeg")

# Synthetic category for images sitting directly in the library root, so a flat
# folder without subfolders still works.
ROOT_CATEGORY = "(root)"

# Placeholder enum entries. An EnumProperty whose items callback returns an empty
# list raises, so both callbacks always return at least one item.
NO_CATEGORY = "NONE"
NO_TEXTURE = "NONE"

# {category_name: [(stem, absolute_path), ...]}, both lists sorted case-insensitively.
_cache = {"root": None, "categories": {}}

# Blender does not keep a reference to the strings returned by a dynamic
# EnumProperty items callback, and a garbage-collected item string is a hard
# crash. Every list built below is parked here before being returned.
_enum_items_ref = {"category": [], "texture": []}


class DecalLibraryError(Exception):
    """The library folder is unset, missing, or contains no usable textures."""


def _is_image(filename):
    return filename.lower().endswith(IMAGE_EXTENSIONS)


def _sort_key(entry):
    return entry[0].lower()


def _scan_directory(path):
    """Return [(stem, absolute_path), ...] for the image files directly in `path`."""
    textures = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_file() and _is_image(entry.name):
                    stem = os.path.splitext(entry.name)[0]
                    textures.append((stem, os.path.abspath(entry.path)))
    except OSError:
        # An unreadable category folder is skipped rather than failing the whole
        # scan - the rest of the library is still perfectly usable.
        return []
    textures.sort(key=_sort_key)
    return textures


def scan(root_path):
    """Rescan `root_path` and replace the cache.

    Returns (category_count, texture_count). Raises DecalLibraryError if the
    path is unset or does not exist; an existing but empty folder is not an
    error (the enums just stay empty), so the user can point at a library
    before filling it.
    """
    if not root_path:
        clear()
        raise DecalLibraryError("No decal library folder set.")

    root = os.path.abspath(bpy_path_abspath(root_path))
    if not os.path.isdir(root):
        clear()
        raise DecalLibraryError(f"Decal library folder does not exist: {root}")

    categories = {}

    root_textures = _scan_directory(root)
    if root_textures:
        categories[ROOT_CATEGORY] = root_textures

    try:
        with os.scandir(root) as entries:
            subdirs = sorted(
                (e.path for e in entries if e.is_dir()),
                key=lambda p: os.path.basename(p).lower(),
            )
    except OSError as e:
        clear()
        raise DecalLibraryError(f"Could not read decal library folder: {e}")

    for subdir in subdirs:
        textures = _scan_directory(subdir)
        if textures:
            categories[os.path.basename(subdir)] = textures

    _cache["root"] = root
    _cache["categories"] = categories

    return len(categories), sum(len(v) for v in categories.values())


def bpy_path_abspath(path):
    """Resolve Blender's "//" relative-to-blend-file prefix, without importing
    bpy at module level (keeps this module importable/testable on its own)."""
    if path.startswith("//"):
        import bpy
        return bpy.path.abspath(path)
    return path


def scan_safe(root_path):
    """scan() that never raises - for use from a property update callback, where
    an exception would be swallowed by Blender anyway."""
    try:
        return scan(root_path)
    except DecalLibraryError:
        return 0, 0


def clear():
    _cache["root"] = None
    _cache["categories"] = {}


def get_root():
    return _cache["root"]


def get_categories():
    return sorted(_cache["categories"].keys(), key=str.lower)


def get_textures(category):
    """[(stem, absolute_path), ...] for `category`, or [] if unknown."""
    return _cache["categories"].get(category, [])


def has_textures():
    return any(_cache["categories"].values())


def texture_path(category, texture):
    """Absolute path of one texture, or "" if it is not in the cache.

    Unlike resolve_texture() this never raises - it is called from panel draw
    code, where a stale selection is normal rather than an error.
    """
    for stem, path in get_textures(category):
        if stem == texture:
            return path
    return ""


def resolve_texture(category, texture, randomize=False, rng=None):
    """Return (stem, absolute_path) for one decal.

    With `randomize`, any texture in `category` may come back; otherwise the
    named `texture` is used. Raises DecalLibraryError with a user-facing message
    when the category is empty or the named texture is gone.
    """
    textures = get_textures(category)
    if not textures:
        raise DecalLibraryError(f"No textures found in category '{category}'.")

    if randomize:
        return rng.choice(textures) if rng is not None else textures[0]

    for stem, path in textures:
        if stem == texture:
            return stem, path

    raise DecalLibraryError(
        f"Texture '{texture}' is no longer in category '{category}'. Press Refresh Library."
    )


def category_items(self, context):
    """EnumProperty items callback - reads the cache only, never the disk."""
    items = [
        (name, name, f"{len(get_textures(name))} texture(s)")
        for name in get_categories()
    ]
    if not items:
        items = [(NO_CATEGORY, "<no categories>",
                  "Set a decal library folder and press Refresh Library")]
    _enum_items_ref["category"] = items
    return items


def texture_items(self, context):
    """EnumProperty items callback - reads the cache only, never the disk."""
    items = [
        (stem, stem, os.path.basename(path))
        for stem, path in get_textures(self.category)
    ]
    if not items:
        items = [(NO_TEXTURE, "<no textures>",
                  "This category has no usable image files")]
    _enum_items_ref["texture"] = items
    return items
