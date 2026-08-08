bl_info = {
    "name": "Seto Fake AO & Decals",
    "author": "Seto",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N-Panel > Seto Fake AO & Decals",
    "description": (
        "GTA V / FiveM decal authoring tools that integrate with Sollumz. "
        "First tool: Fake AO corner decal generator."
    ),
    "category": "Object",
}

# Each tool lives in its own subpackage (fake_ao, and future decal tools)
# so they can be added/removed independently. This top-level __init__ just
# aggregates their register()/unregister() calls.
from . import fake_ao

_modules = (fake_ao,)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
