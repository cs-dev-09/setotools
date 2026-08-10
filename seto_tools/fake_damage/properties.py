import bpy

from ..shared import sollumz_integration as szi
from ..shared import strip_settings
from ..shared import vertex_color


def settings_annotations(update=None):
    """Build a fresh set of property definitions for the tool's settings.

    These live in three places:
      * the Scene PropertyGroup below - the N-panel defaults used when
        creating a new strip,
      * the Create Edge Wear operator - so Blender's "Adjust Last Operation"
        (F9) panel can re-run it live,
      * the per-object PropertyGroup in object_settings.py - the settings the
        finished strip keeps, which rebuild it live when dragged.

    It has to be a function rather than a module-level dict because a
    bpy.props.* definition cannot be shared between two classes - each class
    needs its own object - so every caller gets a freshly built set.

    `update` is the callback Blender fires when a value changes; the
    per-object copy passes its rebuild function here, the other two leave it
    None so nothing happens until the operator runs.
    """
    return {
        "width": bpy.props.FloatProperty(
            name="Width",
            description=(
                "How far the damage strip extends onto each adjacent wall, measured from "
                "the selected edge. The generated ribbon is this wide on BOTH sides of the "
                "corner"
            ),
            default=0.04,
            min=0.0001,
            soft_max=1.0,
            subtype='DISTANCE',
            update=update,
        ),
        "surface_offset": bpy.props.FloatProperty(
            name="Surface Offset",
            description=(
                "How far the strip is lifted off the surface along the corner bisector, "
                "to stop it z-fighting with the source mesh"
            ),
            default=0.0003,
            min=0.0002,
            soft_max=0.05,
            subtype='DISTANCE',
            update=update,
        ),
        "merge_distance": bpy.props.FloatProperty(
            name="Merge Distance",
            description=(
                "Vertices closer than this are welded to their shared centroid once ALL "
                "chains have been generated, so separate chains meeting at a junction join "
                "into one continuous mesh. Must be larger than Surface Offset to close a "
                "seam, but well below Width or the strip collapses"
            ),
            default=0.01,
            min=0.00001,
            soft_max=0.1,
            subtype='DISTANCE',
            update=update,
        ),
        "alpha_center": bpy.props.FloatProperty(
            name="Alpha Center",
            description="Color 1 alpha at the corner itself, where the damage is strongest",
            default=vertex_color.DEFAULT_ALPHA_CENTER,
            min=0.0,
            max=1.0,
            update=update,
        ),
        "alpha_outer": bpy.props.FloatProperty(
            name="Alpha Outer",
            description="Color 1 alpha at the far edge of the strip, so the decal fades out",
            default=vertex_color.DEFAULT_ALPHA_OUTER,
            min=0.0,
            max=1.0,
            update=update,
        ),
        "invert_fade": bpy.props.BoolProperty(
            name="Invert Fade",
            description="Swap which side (corner/outer edge) receives Alpha Center vs Alpha Outer",
            default=False,
            update=update,
        ),
        "color_rgb": bpy.props.FloatVectorProperty(
            name="Color 1 RGB",
            description="RGB written to Color 1 for every vertex; only alpha differs between corner and outer edge",
            subtype='COLOR',
            size=3,
            min=0.0,
            max=1.0,
            default=vertex_color.DEFAULT_RGB,
            update=update,
        ),
        "flip_direction": bpy.props.BoolProperty(
            name="Flip Direction",
            description="Reverse the direction the wings extend from the selected edge",
            default=False,
            update=update,
        ),
        # The fitted island is generic; these place it on the part of the
        # bundled damage texture that actually holds the crease. Applied in the
        # order you would do it by hand in the UV editor: scale about the
        # island's own centre, then move.
        "uv_scale": bpy.props.FloatProperty(
            name="UV Scale",
            description=(
                "Scales the finished UV island about its own centre. Above 1 the island "
                "grows past the 0..1 square, which is how the strip lands on a narrow "
                "band of the texture instead of stretching the whole image over it"
            ),
            default=3.5,
            min=0.001,
            soft_max=10.0,
            update=update,
        ),
        "uv_offset": bpy.props.FloatVectorProperty(
            name="UV Offset",
            description="Moves the finished UV island across the texture, after scaling",
            size=2,
            default=(0.3906, 0.0),
            subtype='XYZ',
            update=update,
        ),
        "material_mode": bpy.props.EnumProperty(
            name="Material",
            description=f"How to obtain the {szi.DAMAGE_SHADER_FILENAME} Sollumz material",
            items=[
                ('AUTO', "Reuse",
                 "Reuse a Edge Wear material previously created by this tool if one is "
                 "found, otherwise create a new one"),
                ('NEW', "Create",
                 f"Always create a new {szi.DAMAGE_SHADER_FILENAME} material"),
            ],
            default='AUTO',
            update=update,
        ),
    }


# Every setting name, in panel order. Used to copy values between the Scene
# settings and the operator's own properties.
SETTING_NAMES = tuple(settings_annotations().keys())

# What this tool alone owns. Everything else describes the strip's shape and
# fade, which Smooth Edge builds identically, so it lives on the Geometry
# section instead - see shared/strip_settings.py.
UNIQUE_NAMES = tuple(n for n in SETTING_NAMES
                     if n not in strip_settings.SHARED_NAMES)


def copy_settings(source, target):
    """Copy every setting from `source` to `target`.

    Works in both directions (Scene settings <-> operator), since both carry
    the same property names. Vector properties come back as a bpy_prop_array
    rather than a plain tuple, so they are unpacked before assignment.
    """
    for name in SETTING_NAMES:
        value = getattr(source, name)
        if hasattr(value, "__len__") and not isinstance(value, str):
            value = tuple(value)
        setattr(target, name, value)


class SETO_PG_fake_damage_settings(bpy.types.PropertyGroup):
    # Only this tool's own settings. The shared ones are still in
    # settings_annotations(), because the operator and the finished strip both
    # need the full set - it is the *panel* that no longer keeps a second copy.
    __annotations__ = {name: prop
                       for name, prop in settings_annotations().items()
                       if name in UNIQUE_NAMES}


_classes = (SETO_PG_fake_damage_settings,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_fake_damage = bpy.props.PointerProperty(type=SETO_PG_fake_damage_settings)


def unregister():
    del bpy.types.Scene.seto_fake_damage
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
