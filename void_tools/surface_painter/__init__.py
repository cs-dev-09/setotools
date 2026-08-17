# Surface Painter subpackage.
#
# Paint dirt onto a GTA V asset without ever touching the asset: START PAINT
# spawns a dense "paint mesh" (a dirt shell) floating just above the surface,
# with a Sollumz decal.sps material whose blend factor is Color 1's alpha -
# so the brush paints alpha, and what is painted is exactly what exports.
#
# Module responsibilities (kept separate on purpose):
#   shell.py     - the dirt shell: creation, mask, opacity, UV placement
#   library.py   - texture folder scanning + cache, no bpy.data knowledge
#   previews.py  - lazily loaded thumbnails (dropdown rows + the big grid)
#   brush.py     - driving Blender's vertex paint brush in alpha mode
#   properties.py- Scene brush/build settings + per-shell dirt adjustments
#   operators.py - Start / Stop / Clear / Remove / Normal Map / Refresh
#   ui.py        - N-Panel
#
# Sollumz is required: the decal material and the drawable conversion come
# from it, via shared/sollumz_integration.py.

from . import library
from . import previews
from . import properties
from . import operators
from . import ui

_modules = (previews, properties, operators, ui)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
    library.clear()
