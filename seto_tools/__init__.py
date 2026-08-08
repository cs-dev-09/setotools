bl_info = {
    "name": "Seto Tools",
    "author": "Seto",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N-Panel > Seto Tools",
    "description": (
        "GTA V / FiveM asset authoring tools that integrate with Sollumz. "
        "Fake AO corner decals, Fake Damage chipped-edge strips, and a Decal Tool "
        "that places library decals on selected faces."
    ),
    "category": "Object",
}

# One add-on, three tools. Each lives in its own subpackage and registers
# itself, so they stay as independent as they were when they shipped as three
# separate add-ons - this top-level __init__ only aggregates their
# register()/unregister() calls, in panel order.
#
# The one thing they genuinely share is shared/sollumz_integration.py, which
# used to be copy-pasted into all three.
from . import fake_ao
from . import fake_damage
from . import decal_tool

_modules = (fake_ao, fake_damage, decal_tool)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
