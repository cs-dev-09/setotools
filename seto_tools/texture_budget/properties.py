"""Scene-level settings for the Texture Budget.

One target and a scope. Like the Density Check there is no per-object group
and no live rebuild, because the tool builds nothing.

1024 texels per metre is the default because it is where vanilla sits: run
over Franklin's house it puts three quarters of the render meshes under 1×
(p75 = 0.90×), the same proportion the triangle budget leaves under its
own. Tighten it for a streaming-tight server, loosen it for close-up hero
work - the colour scale rides along either way.
"""

import bpy

from ..shared import viewport_grade as vg


class SETO_PG_texture_budget(bpy.types.PropertyGroup):
    target: bpy.props.FloatProperty(
        name="Texels / Metre",
        description="Texture pixels a metre of surface should carry. 1024 "
                    "matches vanilla GTA V interiors, where all but a "
                    "handful of textures are 512x512 or smaller",
        default=1024.0, min=16.0, soft_max=8192.0,
    )
    scope: bpy.props.EnumProperty(
        name="Scope",
        description="Which objects Analyze measures",
        items=vg.SCOPE_ITEMS,
        default='VISIBLE',
    )
    # Scene totals from the last run, for the summary the panel draws. Kept
    # on the Scene rather than recomputed in draw(): walking every image on
    # every redraw is exactly the sort of thing that makes a panel stutter.
    total_pixels: bpy.props.FloatProperty(default=0.0, options={'HIDDEN'})
    image_count: bpy.props.IntProperty(default=0, options={'HIDDEN'})
    biggest_name: bpy.props.StringProperty(default="", options={'HIDDEN'})
    biggest_size: bpy.props.IntProperty(default=0, options={'HIDDEN'})


_classes = (SETO_PG_texture_budget,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_texture_budget = bpy.props.PointerProperty(
        type=SETO_PG_texture_budget)


def unregister():
    del bpy.types.Scene.seto_texture_budget
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
