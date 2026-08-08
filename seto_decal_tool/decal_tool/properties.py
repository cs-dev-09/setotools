import math

import bpy
from bpy.app.handlers import persistent

from . import library
from . import preferences
from . import sollumz_integration as szi


class SETO_PG_decal_settings(bpy.types.PropertyGroup):
    # The library folder itself is NOT here - it lives in the add-on preferences
    # so it is remembered across files and restarts. See preferences.py.
    category: bpy.props.EnumProperty(
        name="Category",
        description="Decal category - one subfolder of the decal library",
        items=library.category_items,
    )
    texture: bpy.props.EnumProperty(
        name="Texture",
        description="Decal texture from the selected category",
        items=library.texture_items,
    )

    width: bpy.props.FloatProperty(
        name="Width",
        description="Size of the generated decal along its local X axis",
        default=1.0,
        min=0.0001,
        soft_max=10.0,
        subtype='DISTANCE',
    )
    height: bpy.props.FloatProperty(
        name="Height",
        description="Size of the generated decal along its local Y axis (up, on a wall)",
        default=1.0,
        min=0.0001,
        soft_max=10.0,
        subtype='DISTANCE',
    )
    surface_offset: bpy.props.FloatProperty(
        name="Surface Offset",
        description=(
            "How far the decal is lifted off the selected face along its normal, "
            "to stop it z-fighting with the source mesh"
        ),
        default=0.003,
        min=0.0001,
        soft_max=0.05,
        subtype='DISTANCE',
    )
    rotation: bpy.props.FloatProperty(
        name="Rotation",
        description=(
            "Rotation of the decal around the selected face's normal, so the same "
            "value reads identically on a floor, a wall or a slanted surface"
        ),
        default=0.0,
        subtype='ANGLE',
    )

    random_rotation: bpy.props.BoolProperty(
        name="Random Rotation",
        description="Give each generated decal its own rotation instead of using the Rotation value",
        default=False,
    )
    rotation_min: bpy.props.FloatProperty(
        name="Min Rotation",
        description="Lower bound for random rotation",
        default=0.0,
        subtype='ANGLE',
    )
    rotation_max: bpy.props.FloatProperty(
        name="Max Rotation",
        description="Upper bound for random rotation",
        default=math.tau,
        subtype='ANGLE',
    )

    random_scale: bpy.props.BoolProperty(
        name="Random Scale",
        description="Multiply each generated decal's Width and Height by its own random factor",
        default=False,
    )
    scale_min: bpy.props.FloatProperty(
        name="Min Scale",
        description="Lower bound for the random size multiplier",
        default=0.75,
        min=0.01,
        soft_max=4.0,
    )
    scale_max: bpy.props.FloatProperty(
        name="Max Scale",
        description="Upper bound for the random size multiplier",
        default=1.25,
        min=0.01,
        soft_max=4.0,
    )

    random_texture: bpy.props.BoolProperty(
        name="Random Texture",
        description="Pick each generated decal's texture at random from the selected category",
        default=False,
    )

    random_position: bpy.props.BoolProperty(
        name="Random Position",
        description=(
            "Scatter each decal to a random spot within the face it is placed on, instead "
            "of putting every one at the face center. Turn this on when you are placing "
            "several decals on one large face, otherwise they all land on top of each other"
        ),
        default=False,
    )

    # There is deliberately no alpha here. Decals are generated fully opaque
    # (Color 1 alpha 1.0) and the vertex colour alpha is then dialled in live on
    # the finished decal, in the Selected Decal section - you can see what you
    # are doing there, which you cannot before the decal exists.

    material_mode: bpy.props.EnumProperty(
        name="Material",
        description=f"How to obtain the {szi.DECAL_SHADER_FILENAME} Sollumz material",
        items=[
            ('AUTO', "Reuse if Exists",
             "Reuse a decal material previously created by this tool for the same "
             "texture file if one is found, otherwise create a new one"),
            ('NEW', "Always Create New",
             f"Always create a new {szi.DECAL_SHADER_FILENAME} material (still one per "
             "distinct texture within a single Create Decal run)"),
        ],
        default='AUTO',
    )


@persistent
def _on_blend_file_loaded(_dummy):
    """Make sure the library cache is filled after a file is opened.

    The cache is process-global and the library folder is a preference, so
    nothing about it actually changes when a file is loaded - this only covers
    the case where the cache is still empty (Blender started with a file, and
    the folder was configured in a previous session).

    Deliberately writes nothing into the opened file: filling a scene property
    here would immediately mark a freshly opened .blend as modified.
    """
    path = preferences.get_library_path()
    if path and not library.get_categories():
        library.scan_safe(path)


_classes = (SETO_PG_decal_settings,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_decal = bpy.props.PointerProperty(type=SETO_PG_decal_settings)

    if _on_blend_file_loaded not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_blend_file_loaded)


def unregister():
    if _on_blend_file_loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_blend_file_loaded)

    del bpy.types.Scene.seto_decal
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
