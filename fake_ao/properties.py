import bpy


class SETO_PG_fake_ao_settings(bpy.types.PropertyGroup):
    width: bpy.props.FloatProperty(
        name="Width",
        description="Length of the flat shelf, from the riser out onto the wall surface",
        default=0.1,
        min=0.0001,
        soft_max=1.0,
        subtype='DISTANCE',
    )
    surface_offset: bpy.props.FloatProperty(
        name="Surface Offset",
        description="Height of the riser - how far the shelf is lifted off the wall along its normal",
        default=0.0003,
        min=0.0002,
        soft_max=0.05,
        subtype='DISTANCE',
    )
    merge_distance: bpy.props.FloatProperty(
        name="Merge Distance",
        description=(
            "Vertices closer than this are welded to their shared centroid after all "
            "selected edges have been generated, so neighbouring sections join into one "
            "continuous mesh. Must be larger than Surface Offset to close a corner seam, "
            "but well below Width or the strip collapses"
        ),
        default=0.01,
        min=0.00001,
        soft_max=0.1,
        subtype='DISTANCE',
    )
    alpha_center: bpy.props.FloatProperty(
        name="Alpha Center",
        description="Color 1 alpha value at the corner (the base and riser, closest to the originally selected edge)",
        default=0xB3 / 255.0,
        min=0.0,
        max=1.0,
    )
    alpha_outer: bpy.props.FloatProperty(
        name="Alpha Outer",
        description="Color 1 alpha value at the far edge of the shelf",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    invert_fade: bpy.props.BoolProperty(
        name="Invert Fade",
        description="Swap which side (corner/shelf) receives Alpha Center vs Alpha Outer",
        default=False,
    )
    color_rgb: bpy.props.FloatVectorProperty(
        name="Color 1 RGB",
        description="RGB written to Color 1 for every vertex (center and outer alike); only alpha differs between them",
        subtype='COLOR',
        size=3,
        min=0.0,
        max=1.0,
        default=(0.0, 0x99 / 255.0, 0.0),
    )
    flip_direction: bpy.props.BoolProperty(
        name="Flip Direction",
        description="Reverse the direction the strip extends from the selected edge",
        default=False,
    )
    material_mode: bpy.props.EnumProperty(
        name="Material",
        description="How to obtain the decal.sps Sollumz material",
        items=[
            ('AUTO', "Reuse if Exists",
             "Reuse an existing decal.sps material in this file if one is found, "
             "otherwise create a new one"),
            ('NEW', "Always Create New",
             "Always create a new decal.sps material"),
        ],
        default='AUTO',
    )


_classes = (SETO_PG_fake_ao_settings,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_fake_ao = bpy.props.PointerProperty(type=SETO_PG_fake_ao_settings)


def unregister():
    del bpy.types.Scene.seto_fake_ao
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
