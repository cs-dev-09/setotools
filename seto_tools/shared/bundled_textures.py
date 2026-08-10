"""Finding the texture a tool ships with.

Some tools (Edge Wear, Smooth Edge) always want the same normal map, so
rather than making the user pick a file every time, the texture travels with
the add-on in the tool's own `textures/` folder and is wired in automatically.
That is what makes those tools genuinely one-click, and it means a scene handed
to someone else looks the same on their machine.

Each tool keeps its own folder and calls in here; the scanning rules live in one
place so the two behave identically.

Files are only ever read. The name matters: Sollumz exports the texture name
from the file name without its extension, so `gz_v_ml_wallnormal_n.dds` becomes
the `gz_v_ml_wallnormal_n` reference in the .ydr, which then has to exist in the
asset's TXD.
"""

import os

# .dds first: that is what a GTA normal map normally is, so if someone keeps a
# .dds and a working .png side by side, the .dds is the one that ships.
IMAGE_EXTENSIONS = (".dds", ".png", ".tga", ".jpg", ".jpeg")


def list_textures(directory, preferred_stem=None):
    """Every usable image in `directory`, best candidate first.

    A file whose name (without extension) matches `preferred_stem` wins over
    everything else, so the intended texture can be pinned without having to
    remove the others from the folder.
    """
    try:
        names = os.listdir(directory)
    except OSError:
        return []

    found = []
    for name in names:
        stem, extension = os.path.splitext(name)
        if extension.lower() not in IMAGE_EXTENSIONS:
            continue
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            found.append((stem, extension.lower(), path))

    def rank(entry):
        stem, extension, _ = entry
        preferred = preferred_stem is not None and stem.lower() == preferred_stem.lower()
        return (0 if preferred else 1, IMAGE_EXTENSIONS.index(extension), stem.lower())

    found.sort(key=rank)
    return [path for _, _, path in found]


def bundled_texture_path(directory, preferred_stem=None):
    """The texture to use, or "" when the folder is empty.

    An empty folder is not an error: the calling tool still builds its geometry
    and its material, and only reports that the texture slot was left for the
    user to fill.
    """
    textures = list_textures(directory, preferred_stem)
    return textures[0] if textures else ""


def bundled_texture_name(directory, preferred_stem=None):
    """The name Sollumz will export for the bundled texture, or ""."""
    path = bundled_texture_path(directory, preferred_stem)
    return os.path.splitext(os.path.basename(path))[0] if path else ""
