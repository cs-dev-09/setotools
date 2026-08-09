import bpy

from ..shared import vertex_color


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
            description=(
                "Length of the flat shelf, from the riser out onto the wall surface. Keep it "
                "clear of Bevel Width: the round eats into it, and what is left is what the "
                "AO has to fade out across"
            ),
            default=0.25,
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
            max=0.05,
            subtype='DISTANCE',
            update=update,
        ),
        "alpha_center": bpy.props.FloatProperty(
            name="Alpha Center",
            description="Color 1 alpha value at the corner (the base and riser, closest to the originally selected edge)",
            default=vertex_color.DEFAULT_ALPHA_CENTER,
            min=0.0,
            max=1.0,
            update=update,
        ),
        "alpha_outer": bpy.props.FloatProperty(
            name="Alpha Outer",
            description="Color 1 alpha value at the far edge of the shelf",
            default=vertex_color.DEFAULT_ALPHA_OUTER,
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
            default=vertex_color.DEFAULT_RGB,
            update=update,
        ),
        "flip_direction": bpy.props.BoolProperty(
            name="Flip Direction",
            description="Reverse the direction the strip extends from the selected edge",
            default=False,
            update=update,
        ),
        "bevel_enabled": bpy.props.BoolProperty(
            name="Bevel",
            description=(
                "Round the corner off as well as decal it. A razor-sharp corner reads as "
                "sharp under the best AO there is, so this is on by default"
            ),
            default=True,
            update=update,
        ),
        "bevel_target": bpy.props.EnumProperty(
            name="Bevel",
            description="What gets rounded off",
            items=[
                ('BOTH', "Source + Strip",
                 "Round the source edge, and build the strip so it follows that round with "
                 "the same Width and Segments. Both meshes end up the same shape, which is "
                 "the only way the decal sits ON the rounded corner instead of across it"),
                ('STRIP', "Strip Only",
                 "Round off the generated strip's own seam and leave the source mesh sharp. "
                 "The round hides the sharp corner underneath it"),
                ('SOURCE', "Source Only",
                 "Round the source edge, then run a flat strip along the chamfer's rim onto "
                 "each wall, leaving the round itself bare"),
            ],
            default='BOTH',
            update=update,
        ),
        "bevel_width": bpy.props.FloatProperty(
            name="Bevel Width",
            description="Offset of the round, the same measure as Width in Blender's own Bevel",
            default=0.0833,
            min=0.0,
            soft_max=0.5,
            subtype='DISTANCE',
            update=update,
        ),
        "bevel_segments": bpy.props.IntProperty(
            name="Segments",
            description="1 is a flat chamfer; higher rounds the corner off",
            default=4,
            min=1,
            soft_max=8,
            max=32,
            update=update,
        ),
        "bevel_profile": bpy.props.FloatProperty(
            name="Profile Shape",
            description="Superellipse profile: 0.5 is a circular round, below concave, above convex",
            default=0.5,
            min=0.0,
            max=1.0,
            update=update,
        ),
        "material_mode": bpy.props.EnumProperty(
            name="Material",
            description="How to obtain the decal.sps Sollumz material",
            items=[
                ('AUTO', "Reuse",
                 "Reuse an existing decal.sps material in this file if one is found, "
                 "otherwise create a new one"),
                ('NEW', "Create",
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
