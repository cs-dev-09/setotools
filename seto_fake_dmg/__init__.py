bl_info = {
    "name": "Seto Fake Damage",
    "author": "Seto",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N-Panel > Seto Fake Damage",
    "description": (
        "GTA V / FiveM authoring tool that integrates with Sollumz. "
        "Generates chipped-edge damage decal strips along selected edges."
    ),
    "category": "Object",
}

# Standalone addon - no dependency on Seto Fake AO. The tool lives in its own
# subpackage so this top-level __init__ only aggregates register()/unregister().
from . import fake_damage

_modules = (fake_damage,)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
