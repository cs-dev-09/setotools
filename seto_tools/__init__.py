bl_info = {
    "name": "Seto Tools",
    "author": "Seto",
    "version": (1, 6, 2),
    "blender": (4, 2, 0),
    "location": "View3D > N-Panel > Seto Tools",
    "description": (
        "GTA V / FiveM asset authoring tools that integrate with Sollumz. "
        "Ambient Occlusion corner decals, Edge Dirt strips, Edge Wear "
        "chipped-edge strips, Smooth Edge normal-map strips, a Decal Tool that "
        "places library decals on selected faces, and a Surface Painter for "
        "brushing dirt onto an asset through a non-destructive mask."
    ),
    "category": "Object",
}

# One add-on, six tools. Each lives in its own subpackage and registers itself,
# so they stay as independent as the first three were when they shipped as
# separate add-ons - this top-level __init__ only aggregates their
# register()/unregister() calls, in panel order.
#
# What they genuinely share lives in shared/: the Sollumz integration, which
# used to be copy-pasted into each of them, the bundled-texture lookup, and the
# Color 1 vertex colour they all write.
from .shared import icons
from .shared import strip_settings
from .shared import manual_offset
from .shared import groups
from . import fake_ao
from . import edge_dirt
from . import fake_damage
from . import smooth_edge
from . import decal_tool
from . import surface_painter

# Panel order. icons first because every panel header asks it for an icon id,
# then groups - and that one is not merely tidiness: every tool panel hangs off
# one of its two sections, and Blender drops a panel whose bl_parent_id is not
# registered yet.
_modules = (icons, strip_settings, manual_offset, groups, fake_damage,
            smooth_edge, fake_ao, decal_tool, surface_painter, edge_dirt)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
