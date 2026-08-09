"""Surface Painter texture library: scanning and caching.

Deliberately free of bpy.data knowledge - this module only knows about folders
and image files on disk. Nothing is loaded into Blender here; an image only
enters the file when it is actually painted with.

The library is a folder of category subfolders:

    textures/surface_painter/
        dirt/     Dirt_Concrete_01.png  Dirt_Grime_02.png ...
        grunge/
        mold/

The add-on ships that tree empty - the folders are there to drop files into,
and each one carries a README saying so. No textures are bundled: dirt sheets
are large, they would be most of the download, and anyone using this already
has a library of their own. Point **Custom Library** at it.

A custom library replaces the bundled tree wholesale rather than merging with
it: a half-and-half library where you cannot tell which Dirt folder a texture
came from is worse than picking one.

Scanning is NOT done on UI redraw. The cache is refilled from exactly three
places: registration, the Custom Library path's update callback, and the Refresh
operator. The enum callbacks below only ever read the cache.
"""

import os

# Folder names the bundled tree ships, in the order they are offered, with the
# labels the panel shows. A folder only appears as a category once it actually
# contains textures, and a folder that is not listed here still works - it just
# gets a title-cased version of its own name, which is what makes an arbitrary
# custom library work without being registered anywhere.
CATEGORY_LABELS = {
    "dirt": "Dirt",
    "grunge": "Grunge",
    "dust": "Dust",
    "mold": "Mold",
    "wetness": "Wetness",
    "damage": "Damage",
}
CATEGORY_ORDER = tuple(CATEGORY_LABELS.keys())

# Blender reads all of these. .dds support depends on the compression format,
# which is why a load failure is reported per texture rather than up front.
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tga", ".dds")

# Placeholder enum entries. An EnumProperty whose items callback returns an
# empty list raises, so both callbacks always return at least one item.
NO_CATEGORY = "NONE"
NO_TEXTURE = "NONE"

# The folder shipped inside the add-on: seto_tools/textures/surface_painter/
_ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED_ROOT = os.path.join(_ADDON_ROOT, "textures", "surface_painter")

# {folder_name: [(stem, absolute_path), ...]}, sorted case-insensitively.
_cache = {"root": "", "categories": {}}

# Blender does not keep a reference to the strings returned by a dynamic
# EnumProperty items callback, and a garbage-collected item string is a hard
# crash. Every list built below is parked here before being returned.
_enum_items_ref = {"category": [], "texture": []}


def _is_image(filename):
    return filename.lower().endswith(IMAGE_EXTENSIONS)


def _scan_directory(path):
    """[(stem, absolute_path), ...] for the image files directly in `path`."""
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
    textures.sort(key=lambda entry: entry[0].lower())
    return textures


def resolve_root(custom_path=""):
    """The library folder to read, honouring Blender's "//" relative prefix."""
    if custom_path:
        if custom_path.startswith("//"):
            import bpy
            custom_path = bpy.path.abspath(custom_path)
        return os.path.abspath(custom_path)
    return BUNDLED_ROOT


def scan(custom_path=""):
    """Rescan the library and replace the cache. Returns (categories, textures).

    Never raises: a missing or empty library leaves the enums showing their
    placeholder entry, which the panel turns into a readable hint. That matters
    because this runs from a property update callback, where an exception would
    be swallowed by Blender and leave a silently stale cache.
    """
    root = resolve_root(custom_path)
    categories = {}

    if os.path.isdir(root):
        try:
            with os.scandir(root) as entries:
                subdirs = sorted(
                    (e.path for e in entries if e.is_dir()),
                    key=lambda p: os.path.basename(p).lower(),
                )
        except OSError:
            subdirs = []

        for subdir in subdirs:
            textures = _scan_directory(subdir)
            if textures:
                categories[os.path.basename(subdir)] = textures

    _cache["root"] = root
    _cache["categories"] = categories
    return len(categories), sum(len(v) for v in categories.values())


def clear():
    _cache["root"] = ""
    _cache["categories"] = {}


def get_root():
    return _cache["root"]


def is_using_bundled():
    return os.path.normcase(_cache["root"]) == os.path.normcase(BUNDLED_ROOT)


def get_categories():
    """Folder names that actually contain textures, known ones first.

    A folder Surface Painter ships is listed before any extra folder the user
    dropped in, and in CATEGORY_ORDER above, so Dirt does not end up sorted below
    someone's "aaa_test" folder.
    """
    found = _cache["categories"].keys()
    known = [name for name in CATEGORY_ORDER if name in found]
    extra = sorted((f for f in found if f not in known), key=str.lower)
    return known + extra


def category_label(folder_name):
    label = CATEGORY_LABELS.get(folder_name.lower())
    return label if label else folder_name.replace("_", " ").title()


def get_textures(category):
    """[(stem, absolute_path), ...] for `category`, or [] if unknown."""
    return _cache["categories"].get(category, [])


def has_textures():
    return any(_cache["categories"].values())


def texture_path(category, texture):
    """Absolute path of one texture, or "" if it is not in the cache.

    Never raises - it is called from panel draw code, where a stale selection is
    normal rather than an error.
    """
    for stem, path in get_textures(category):
        if stem == texture:
            return path
    return ""


def resolve_texture(category, texture):
    """(stem, absolute_path) for the selected texture.

    Raises LibraryError with a user-facing message when the category is empty or
    the named texture has gone missing since the last scan.
    """
    textures = get_textures(category)
    if not textures:
        raise LibraryError(f"No textures found in category '{category_label(category)}'.")
    for stem, path in textures:
        if stem == texture:
            return stem, path
    raise LibraryError(
        f"Texture '{texture}' is no longer in '{category_label(category)}'. Press Refresh."
    )


class LibraryError(Exception):
    """The selected texture is not in the library any more."""


def category_items(self, context):
    """EnumProperty items callback - reads the cache only, never the disk."""
    items = [
        (name, category_label(name), f"{len(get_textures(name))} texture(s)")
        for name in get_categories()
    ]
    if not items:
        items = [(NO_CATEGORY, "<no categories>",
                  "No texture folders found - press Refresh, or set a Custom Library")]
    _enum_items_ref["category"] = items
    return items


def texture_items(self, context):
    """EnumProperty items callback - reads the cache only, never the disk.

    Five-element items, so every row in the dropdown carries the texture's own
    thumbnail instead of a generic icon. Blender has no way to put an image in a
    tooltip, so showing it on the row itself is the closest thing to previewing
    on hover - and it also makes the enum usable with template_icon_view, which
    is what the thumbnail grid button uses.

    Previews are loaded lazily by previews.get_icon_id, so a category with
    hundreds of files still only decodes what is actually on screen.
    """
    from . import previews

    items = []
    for number, (stem, path) in enumerate(get_textures(self.category)):
        items.append((stem, stem, os.path.basename(path),
                      previews.get_icon_id(path), number))
    if not items:
        items = [(NO_TEXTURE, "<no textures>",
                  "This category has no usable image files", 'ERROR', 0)]
    _enum_items_ref["texture"] = items
    return items
