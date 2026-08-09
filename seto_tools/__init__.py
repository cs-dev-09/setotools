bl_info = {
    "name": "Seto Tools",
    "author": "Seto",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N-Panel > Seto Tools",
    "description": (
        "GTA V / FiveM asset authoring tools that integrate with Sollumz. "
        "Fake AO corner decals, Fake Damage chipped-edge strips, Smooth Edge "
        "normal-map strips, a Decal Tool that places library decals on "
        "selected faces, and a Surface Painter for brushing dirt onto an asset "
        "through a non-destructive mask."
    ),
    "category": "Object",
}

# One add-on, five tools. Each lives in its own subpackage and registers itself,
# so they stay as independent as the first three were when they shipped as
# separate add-ons - this top-level __init__ only aggregates their
# register()/unregister() calls, in panel order.
#
# What they genuinely share lives in shared/: the Sollumz integration, which
# used to be copy-pasted into each of them, the bundled-texture lookup, and the
# Color 1 vertex colour they all write.
from .shared import groups
from . import fake_ao
from . import fake_damage
from . import smooth_edge
from . import decal_tool
from . import surface_painter

# Panel order. groups first, and not only for tidiness: every tool panel now
# hangs off one of its two sections, and Blender drops a panel whose
# bl_parent_id is not registered yet.
_modules = (groups, fake_damage, smooth_edge, fake_ao, decal_tool,
            surface_painter)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
