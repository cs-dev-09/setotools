"""The strip shape, owned by the Geometry section rather than by either tool.

Edge Wear and Smooth Edge build the *same* strip along the selected edges and
then put a different texture on it. Every geometry and fade setting was
therefore declared twice, drawn twice, and stacked one on top of the other in
the tab - which is exactly what a tester complained about: the same seven rows,
listed again a few centimetres further down.

They now live here, on `scene.seto_edge_strip`, and the Geometry section panel
draws them once. Each tool's own panel keeps only what is genuinely its own:
Edge Wear its UV placement, Smooth Edge nothing at all.

**The values are shared, and that is the point.** Setting Width to 4 cm sets it
for both, because on one asset you almost always want the same. What is *not*
shared is a finished strip: every created object still carries its own full
copy of these settings and rebuilds from that, so two strips made minutes apart
with different widths both keep theirs.

Ambient Occlusion deliberately does not join in. It sits in the Surface section
and its Width means something else - the flat shelf the AO fades across,
defaulting to 0.25 m against 0.04 m here - so sharing would have the two
overwriting each other every time you switched tools.
"""

import bpy

from . import vertex_color

# Which of a tool's settings come from the section rather than from the tool.
# Anything not in here is the tool's own - `uv_scale` and `uv_offset` today.
SHARED_NAMES = (
    "width",
    "surface_offset",
    "merge_distance",
    "alpha_center",
    "alpha_outer",
    "alpha_bottom",
    "alpha_top",
    "invert_fade",
    "color_rgb",
    "flip_direction",
    "material_mode",
)


def annotations(update=None):
    """The shared property definitions.

    Worded for both tools: the descriptions used to say "the damage strip" and
    "the smooth edge strip" separately, and one of them would have been a lie
    wherever it was drawn.

    A fresh set is built per call - a `bpy.props.*` definition cannot be shared
    between two classes.
    """
    return {
        "width": bpy.props.FloatProperty(
            name="Width",
            description=(
                "How far the strip extends onto each adjacent wall, measured "
                "from the selected edge. The generated ribbon is this wide on "
                "BOTH sides of the corner"
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
                "How far the strip is lifted off the surface along the corner "
                "bisector, to stop it z-fighting with the source mesh"
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
                "Vertices closer than this are welded to their shared centroid "
                "once ALL chains have been generated, so separate chains "
                "meeting at a junction join into one continuous mesh. Must be "
                "larger than Surface Offset to close a seam, but well below "
                "Width or the strip collapses"
            ),
            default=0.01,
            min=0.00001,
            soft_max=0.1,
            subtype='DISTANCE',
            update=update,
        ),
        "alpha_center": bpy.props.FloatProperty(
            name="Alpha Center",
            description="Color 1 alpha at the corner itself, where the effect is strongest",
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
        "alpha_bottom": bpy.props.FloatProperty(
            name="Alpha Bottom",
            description=(
                "Scales the whole strip's alpha at the LOW end of the run, "
                "ramping back to full at the high end. 1.0 leaves it alone. "
                "Where Alpha Center/Outer fade across the strip, this fades "
                "along it - so an edge can let go before it reaches the floor"
            ),
            default=1.0,
            min=0.0,
            max=1.0,
            update=update,
        ),
        "alpha_top": bpy.props.FloatProperty(
            name="Alpha Top",
            description=(
                "Scales the whole strip's alpha at the HIGH end of the run, "
                "ramping back to full at the low end. 1.0 leaves it alone. "
                "Bottom and top are the building's, not the object's - a "
                "rotated source still fades toward the floor"
            ),
            default=1.0,
            min=0.0,
            max=1.0,
            update=update,
        ),
        "invert_fade": bpy.props.BoolProperty(
            name="Invert Fade",
            description=(
                "Swap which side (corner/outer edge) receives Alpha Center vs "
                "Alpha Outer"
            ),
            default=False,
            update=update,
        ),
        "color_rgb": bpy.props.FloatVectorProperty(
            name="Color 1 RGB",
            description=(
                "RGB written to Color 1 for every vertex; only alpha differs "
                "between corner and outer edge"
            ),
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
            description="How each tool obtains its Sollumz material",
            items=[
                ('AUTO', "Reuse",
                 "Reuse a material this tool created earlier, if one is found, "
                 "otherwise create a new one"),
                ('NEW', "Create",
                 "Always create a new material"),
            ],
            default='AUTO',
            update=update,
        ),
    }


def get(context):
    return context.scene.seto_edge_strip


def panel_value(context, name, tool_settings):
    """The panel value for `name` - from the section if shared, else the tool.

    This is the single place that decides which of the two panels a setting is
    read from, so an operator cannot drift from what the UI actually draws.
    """
    source = get(context) if name in SHARED_NAMES else tool_settings
    value = getattr(source, name)
    if hasattr(value, "__len__") and not isinstance(value, str):
        value = tuple(value)
    return value


def write_back(operator, context, tool_settings, names):
    """Push what just ran back onto the panels it came from.

    Keeps the section and the tool showing the values of the last run, which is
    what makes an F9 redo pick up where the previous one left off.
    """
    shared = get(context)
    for name in names:
        value = getattr(operator, name)
        if hasattr(value, "__len__") and not isinstance(value, str):
            value = tuple(value)
        setattr(shared if name in SHARED_NAMES else tool_settings, name, value)


def draw(layout, settings):
    """What has to be decided BEFORE there is a strip to look at.

    Which is almost nothing. Every shape and fade setting used to be listed
    here as well as on the finished strip, and the two blocks were identical -
    so the natural thing to do was drag the one at the top of the tab and watch
    nothing happen, because that one only seeds the *next* Create.

    They are gone. A strip is made with the defaults and then dialled in on
    itself, where every drag rebuilds it in front of you. The material choice
    stays: it decides what the strip is built with, not how it looks
    afterwards.
    """
    layout.prop(settings, "material_mode")


class SETO_PG_edge_strip_settings(bpy.types.PropertyGroup):
    # Assigned rather than declared with `name: bpy.props...` so the
    # definitions stay shareable - see annotations().
    __annotations__ = annotations()


_classes = (SETO_PG_edge_strip_settings,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_edge_strip = bpy.props.PointerProperty(
        type=SETO_PG_edge_strip_settings)


def unregister():
    del bpy.types.Scene.seto_edge_strip
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
