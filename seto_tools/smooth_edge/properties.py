import bpy

from ..shared import sollumz_integration as szi
from ..shared import vertex_color


def settings_annotations(update=None):
    """Build a fresh set of property definitions for the tool's settings.

    These live in three places:
      * the Scene PropertyGroup below - the N-panel defaults used when
        creating a new strip,
      * the Create Smooth Edge operator - so Blender's "Adjust Last Operation"
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
                "How far the strip extends onto each adjacent wall, measured from "
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
            description="Color 1 alpha at the corner itself, where the rounding reads strongest",
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
        "material_mode": bpy.props.EnumProperty(
            name="Material",
            description=f"How to obtain the {szi.SMOOTH_EDGE_SHADER_FILENAME} Sollumz material",
            items=[
                ('AUTO', "Reuse",
                 "Reuse a Smooth Edge material previously created by this tool if one is "
                 "found, otherwise create a new one"),
                ('NEW', "Create",
                 f"Always create a new {szi.SMOOTH_EDGE_SHADER_FILENAME} material"),
            ],
            default='AUTO',
            update=update,
        ),
    }


# Every setting name, in panel order. Used to copy values between the Scene
# settings and the operator's own properties.
SETTING_NAMES = tuple(settings_annotations().keys())


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


class SETO_PG_smooth_edge_settings(bpy.types.PropertyGroup):
    # Assigned rather than written with `name: bpy.props...` syntax so the
    # definitions stay shared with the operator - see settings_annotations().
    __annotations__ = settings_annotations()


_classes = (SETO_PG_smooth_edge_settings,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_smooth_edge = bpy.props.PointerProperty(type=SETO_PG_smooth_edge_settings)


def unregister():
    del bpy.types.Scene.seto_smooth_edge
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
