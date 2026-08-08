bl_info = {
    "name": "Seto Decal Tool",
    "author": "Seto",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N-Panel > Seto Tools > Decal Tool",
    "description": (
        "GTA V / FiveM authoring tool that integrates with Sollumz. "
        "Turns a face selection into surface-aligned decal.sps decal planes "
        "picked from an external decal library."
    ),
    "category": "Object",
}

# Standalone addon - no dependency on Seto Fake AO or Seto Fake Damage, it only
# shares their "Seto Tools" panel category. The tool lives in its own subpackage
# so this top-level __init__ only aggregates register()/unregister().
from . import decal_tool

_modules = (decal_tool,)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
