# Decal Tool subpackage.
#
# Module responsibilities (kept separate on purpose):
#   library.py             - decal library folder scanning + cache, no bpy.data/Sollumz knowledge
#   preferences.py         - add-on preferences: the decal library folder, remembered across files
#   previews.py            - lazily loaded thumbnails for the selected texture
#   geometry.py            - pure bmesh/mathutils face reading and quad generation, no Sollumz knowledge
#   sollumz_integration.py - all calls into the Sollumz addon (detection, shader, texture, UV/Color, LOD)
#   properties.py          - Scene-level settings (PropertyGroup)
#   object_settings.py     - per-decal settings that move/resize it live
#   operators.py           - "Create Decal" / "Refresh Library", tying the modules together
#   ui.py                  - N-Panel

from . import library
from . import preferences
from . import previews
from . import properties
from . import object_settings
from . import operators
from . import ui

# preferences first: registering it scans the remembered library folder, so the
# Category/Texture enums are already populated the first time the panel draws.
_modules = (preferences, previews, properties, object_settings, operators, ui)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
    # The cache is process-global, so drop it when the addon goes away rather
    # than leaving stale categories behind for a later re-enable.
    library.clear()
