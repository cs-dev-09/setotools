"""The damage normal map that ships with this tool.

Drop a file into:

    void_tools/fake_damage/textures/

and every strip Edge Wear builds picks it up, in both DiffuseSampler and
BumpSampler. The scanning rules live in shared/bundled_textures.py, which Smooth
Edge uses too; this module only says where this tool's folder is.
"""

import os

from ..shared import bundled_textures

TEXTURE_DIRECTORY = os.path.join(os.path.dirname(__file__), "textures")

# A file with this stem wins over anything else in the folder, so the intended
# texture can be pinned without removing the others.
PREFERRED_STEM = "fake_damage"


def list_textures():
    return bundled_textures.list_textures(TEXTURE_DIRECTORY, PREFERRED_STEM)


def bundled_texture_path():
    return bundled_textures.bundled_texture_path(TEXTURE_DIRECTORY, PREFERRED_STEM)


def bundled_texture_name():
    return bundled_textures.bundled_texture_name(TEXTURE_DIRECTORY, PREFERRED_STEM)
