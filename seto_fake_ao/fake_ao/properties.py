import bpy


def settings_annotations(update=None):
    """Build a fresh set of property definitions for the tool's settings.

    These live in three places:
      * the Scene PropertyGroup below - the N-panel defaults used when
        creating a new strip,
      * the Create Fake AO operator - so Blender's "Adjust Last Operation"
        (F9) panel can re-run it live,
      * the per-object PropertyGroup in object_settings.py - the settings the
        finished strip keeps, which rebuild it live when dragged.

    It has to be a function rather than a module-level dict because a
    bpy.props.* definition cannot be shared between two classes - each class
    needs its own object - so every caller gets a freshly built set.

    `update` is the callback Blender fires when a value changes; only the
    per-object copy passes one.
    """
    return {
        "width": bpy.props.FloatProperty(
            name="Width",
            description="Length of the flat shelf, from the riser out onto the wall surface",
            default=0.1,
            min=0.0001,
            soft_max=1.0,
            subtype='DISTANCE',
            update=update,
        ),
        "surface_offset": bpy.props.FloatProperty(
            name="Surface Offset",
            description="Height of the riser - how far the shelf is lifted off the wall along its normal",
            default=0.0003,
            min=0.0002,
            soft_max=0.05,
            subtype='DISTANCE',
            update=update,
        ),
        "merge_distance": bpy.props.FloatProperty(
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
            update=update,
        ),
        "alpha_center": bpy.props.FloatProperty(
            name="Alpha Center",
            description="Color 1 alpha value at the corner (the base and riser, closest to the originally selected edge)",
            default=0xB3 / 255.0,
            min=0.0,
            max=1.0,
            update=update,
        ),
        "alpha_outer": bpy.props.FloatProperty(
            name="Alpha Outer",
            description="Color 1 alpha value at the far edge of the shelf",
            default=0.0,
            min=0.0,
            max=1.0,
            update=update,
        ),
        "invert_fade": bpy.props.BoolProperty(
            name="Invert Fade",
            description="Swap which side (corner/shelf) receives Alpha Center vs Alpha Outer",
            default=False,
            update=update,
        ),
        "color_rgb": bpy.props.FloatVectorProperty(
            name="Color 1 RGB",
            description="RGB written to Color 1 for every vertex (center and outer alike); only alpha differs between them",
            subtype='COLOR',
            size=3,
            min=0.0,
            max=1.0,
            default=(0.0, 0x99 / 255.0, 0.0),
            update=update,
        ),
        "flip_direction": bpy.props.BoolProperty(
            name="Flip Direction",
            description="Reverse the direction the strip extends from the selected edge",
            default=False,
            update=update,
        ),
        "material_mode": bpy.props.EnumProperty(
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
            update=update,
        ),
    }


# Every setting name, in panel order. Used to copy values between the Scene
# settings, the operator and the per-object settings.
SETTING_NAMES = tuple(settings_annotations().keys())


def copy_settings(source, target):
    """Copy every setting from `source` to `target`.

    Works in any direction, since all three carry the same property names.
    Vector properties come back as a bpy_prop_array rather than a plain tuple,
    so they are unpacked before assignment.
    """
    for name in SETTING_NAMES:
        value = getattr(source, name)
        if hasattr(value, "__len__") and not isinstance(value, str):
            value = tuple(value)
        setattr(target, name, value)


class SETO_PG_fake_ao_settings(bpy.types.PropertyGroup):
    # Assigned rather than written with `name: bpy.props...` syntax so the
    # definitions stay shared with the operator and the per-object group -
    # see settings_annotations().
    __annotations__ = settings_annotations()


_classes = (SETO_PG_fake_ao_settings,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_fake_ao = bpy.props.PointerProperty(type=SETO_PG_fake_ao_settings)


def unregister():
    del bpy.types.Scene.seto_fake_ao
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
