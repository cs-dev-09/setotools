"""The ambient-occlusion texture that ships with this tool.

Drop a file into:

    seto_tools/fake_ao/textures/

and every strip Fake AO builds picks it up, in DiffuseSampler. The scanning
rules live in shared/bundled_textures.py, shared with the other tools; this
module only says where this tool's folder is.
"""

import os

from ..shared import bundled_textures

TEXTURE_DIRECTORY = os.path.join(os.path.dirname(__file__), "textures")

# A file with this stem wins over anything else in the folder, so the intended
# texture can be pinned without removing the others.
PREFERRED_STEM = "fake_ao"


def list_textures():
    return bundled_textures.list_textures(TEXTURE_DIRECTORY, PREFERRED_STEM)


def bundled_texture_path():
    return bundled_textures.bundled_texture_path(TEXTURE_DIRECTORY, PREFERRED_STEM)


def bundled_texture_name():
    return bundled_textures.bundled_texture_name(TEXTURE_DIRECTORY, PREFERRED_STEM)
