# Fake AO tool subpackage.
#
# Module responsibilities (kept separate on purpose):
#   geometry.py            - pure bmesh/mathutils strip generation, no Sollumz/bpy.data knowledge
#   sollumz_integration.py - all calls into the Sollumz addon (detection, naming, shader, LOD)
#   properties.py          - Scene-level settings (PropertyGroup)
#   object_settings.py     - per-object settings that rebuild the strip live
#   operators.py           - the "Create Fake AO" operator that ties geometry + integration together
#   ui.py                  - N-Panel

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
