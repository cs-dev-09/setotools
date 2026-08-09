# Lighting tool subpackage.
#
# Automates the GTA V / FiveM interior "god ray" setup that Sollumz otherwise
# requires three separate, manually kept-in-sync pieces of data for:
#
#   * a Sollumz Spot Light   - a real Blender LIGHT object inside the Drawable,
#                              exported to .ydr by Sollumz's ydr/lights.py
#   * a Light Shaft          - a CExtensionDefLightShaft on the YTYP archetype
#   * a Dust Particle        - a CExtensionDefParticleEffect on the same
#                              archetype (optional)
#
# The last two are NOT scene objects: they live in
# scene.ytyps[i].archetypes[j].extensions[k] and are exported to .ytyp. That
# split is the reason this tool needs its own grouping system rather than plain
# Blender parenting - see properties.py.
#
# Module responsibilities (kept separate on purpose, matching the other tools):
#   godray.py              - pure mathutils opening analysis, no Sollumz/bpy.data knowledge
#   ../shared/sollumz_integration.py - all calls into the Sollumz addon, shared with the other tools
#   properties.py          - Scene-level settings (PropertyGroup)
#   operators.py           - Create God Rays / Aim / Sync / Duplicate
#   ui.py                  - N-Panel
#
#   group.py               - per-setup data on the root Empty, and the master
#                            control fan-out that keeps the three parts in step

from . import properties
from . import group
from . import operators
from . import presets
from . import ui

# properties before group (group builds its master controls from the same
# definitions), and both before ui, which draws them.
_modules = (properties, group, operators, presets, ui)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
