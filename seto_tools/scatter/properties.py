"""Scene-level settings for Trash Scatter.

Scene-level only: the scatter is an act, not an object with a life of its
own. Scatter again with the same source floor and the previous layout is
replaced, so the settings behave like live controls without a per-object
group or a rebuild callback - the operator is the rebuild.
"""

import bpy

from . import catalog


class SETO_PG_scatter(bpy.types.PropertyGroup):
    preset: bpy.props.EnumProperty(
        name="Preset",
        description="Which family of vanilla props gets scattered",
        items=catalog.PRESET_ITEMS,
        default='TRASH',
    )
    density: bpy.props.FloatProperty(
        name="Density",
        description="Props per square metre of selected floor. Spacing may "
                    "place fewer when they genuinely do not fit",
        default=1.0, min=0.05, soft_max=6.0, max=20.0,
    )
    seed: bpy.props.IntProperty(
        name="Seed",
        description="Same seed, same layout. Change it to re-roll the "
                    "arrangement without touching anything else",
        default=1, min=0,
    )
    edge_bias: bpy.props.FloatProperty(
        name="Edge Bias",
        description="How strongly props gather along the edges of the "
                    "selected floor - walls and corners, where litter "
                    "really collects. 0 spreads them evenly",
        default=0.6, min=0.0, max=1.0, subtype='FACTOR',
    )
    scale_jitter: bpy.props.FloatProperty(
        name="Scale Jitter",
        description="Random size variation around 1.0. GTA entities scale "
                    "uniformly, so this is one factor per prop",
        default=0.1, min=0.0, max=0.4, subtype='FACTOR',
    )
    prop_scale: bpy.props.FloatProperty(
        name="Prop Scale",
        description="Every prop's base size. 1.0 is the prop's real size "
                    "in game - litter does not grow when the room does - "
                    "but the choice is yours",
        default=1.0, min=0.1, soft_max=3.0, max=5.0,
    )
    topple: bpy.props.FloatProperty(
        name="Topple",
        description="The chance a standing prop - a bottle, a can - is "
                    "laid on its side instead. Litter that stands to "
                    "attention reads as staged, so everything topples "
                    "by default; lower this only on purpose",
        default=1.0, min=0.0, max=1.0, subtype='FACTOR',
    )
    clustering: bpy.props.FloatProperty(
        name="Clustering",
        description="0 spreads the litter; toward 1 it gathers into "
                    "heaps around a few seeded spots - cigarette butts "
                    "by a doorway, not one per square metre",
        default=0.3, min=0.0, max=1.0, subtype='FACTOR',
    )
    dirt_enabled: bpy.props.BoolProperty(
        name="Floor Dirt",
        description="Lay a procedural dirt overlay over the selected "
                    "floor - the flat decal sheet vanilla interiors use, "
                    "pooled along the walls like the litter",
        default=True,
    )
    dirt_amount: bpy.props.FloatProperty(
        name="Amount",
        description="How dirty the floor is. 0 is clean, 1 is a floor "
                    "you could write your name in",
        default=0.5, min=0.0, max=1.0, subtype='FACTOR',
    )
    dirt_scale: bpy.props.FloatProperty(
        name="Blotch Size",
        description="How large the grime patches are, in metres",
        default=2.0, min=0.5, soft_max=6.0, max=12.0, subtype='DISTANCE',
    )


_classes = (SETO_PG_scatter,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_scatter = bpy.props.PointerProperty(
        type=SETO_PG_scatter)


def unregister():
    del bpy.types.Scene.seto_scatter
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
