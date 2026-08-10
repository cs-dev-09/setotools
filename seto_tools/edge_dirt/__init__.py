# Edge Dirt tool subpackage.
#
# The same strip Ambient Occlusion builds, carrying a dirt texture instead of an
# AO shadow. Because it is the same strip, the maths and the live-rebuild
# machinery are *imported* from fake_ao rather than copied - a second copy of
# 700 lines of geometry would drift from the original the first time either was
# fixed. What this package owns is what genuinely differs: its own Scene and
# per-object settings, its own material and bundled texture, and its own panel.
#
# Module responsibilities:
#   properties.py      - Scene-level settings (PropertyGroup)
#   object_settings.py - per-object settings that rebuild the strip live
#   operators.py       - the "Create Edge Dirt" operator
#   textures.py        - where this tool's bundled dirt texture lives
#   ui.py              - N-Panel

from . import properties
from . import object_settings
from . import operators
from . import ui

_modules = (properties, object_settings, operators, ui)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
