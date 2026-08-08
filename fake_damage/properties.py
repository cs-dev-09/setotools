import bpy

from . import sollumz_integration as szi


class SETO_PG_fake_damage_settings(bpy.types.PropertyGroup):
    width: bpy.props.FloatProperty(
        name="Damage Width",
        description=(
            "How far the damage strip extends onto each adjacent wall, measured from "
            "the selected edge. The generated ribbon is this wide on BOTH sides of the "
            "corner"
        ),
        default=0.04,
        min=0.0001,
        soft_max=1.0,
        subtype='DISTANCE',
    )
    surface_offset: bpy.props.FloatProperty(
        name="Surface Offset",
        description=(
            "How far the strip is lifted off the surface along the corner bisector, "
            "to stop it z-fighting with the source mesh"
        ),
        default=0.0003,
        min=0.0002,
        soft_max=0.05,
        subtype='DISTANCE',
    )
    merge_distance: bpy.props.FloatProperty(
        name="Merge Distance",
        description=(
            "Vertices closer than this are welded to their shared centroid once ALL "
            "chains have been generated, so separate chains meeting at a junction join "
            "into one continuous mesh. Must be larger than Surface Offset to close a "
            "seam, but well below Damage Width or the strip collapses"
        ),
        default=0.01,
        min=0.00001,
        soft_max=0.1,
        subtype='DISTANCE',
    )
    alpha_center: bpy.props.FloatProperty(
        name="Alpha Center",
        description="Color 1 alpha at the corner itself, where the damage is strongest",
        default=1.0,
        min=0.0,
        max=1.0,
    )
    alpha_outer: bpy.props.FloatProperty(
        name="Alpha Outer",
        description="Color 1 alpha at the far edge of the strip, so the decal fades out",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    invert_fade: bpy.props.BoolProperty(
        name="Invert Fade",
        description="Swap which side (corner/outer edge) receives Alpha Center vs Alpha Outer",
        default=False,
    )
    color_rgb: bpy.props.FloatVectorProperty(
        name="Color 1 RGB",
        description="RGB written to Color 1 for every vertex; only alpha differs between corner and outer edge",
        subtype='COLOR',
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
    )
    flip_direction: bpy.props.BoolProperty(
        name="Flip Direction",
        description="Reverse the direction the wings extend from the selected edge",
        default=False,
    )
    material_mode: bpy.props.EnumProperty(
        name="Material",
        description=f"How to obtain the {szi.DAMAGE_SHADER_FILENAME} Sollumz material",
        items=[
            ('AUTO', "Reuse if Exists",
             "Reuse a Fake Damage material previously created by this tool if one is "
             "found, otherwise create a new one"),
            ('NEW', "Always Create New",
             f"Always create a new {szi.DAMAGE_SHADER_FILENAME} material"),
        ],
        default='AUTO',
    )


_classes = (SETO_PG_fake_damage_settings,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_fake_damage = bpy.props.PointerProperty(type=SETO_PG_fake_damage_settings)


def unregister():
    del bpy.types.Scene.seto_fake_damage
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
