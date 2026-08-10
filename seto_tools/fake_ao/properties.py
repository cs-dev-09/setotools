import bpy

from ..shared import vertex_color


def settings_annotations(update=None):
    """Build a fresh set of property definitions for the tool's settings.

    These live in three places:
      * the Scene PropertyGroup below - the N-panel defaults used when
        creating a new strip,
      * the Create Ambient Occlusion operator - so Blender's "Adjust Last Operation"
        (F9) panel can re-run it live,
      * the per-object PropertyGroup in object_settings.py - the settings the
        finished strip keeps, which rebuild it live when dragged.

    It has to be a function rather than a module-level dict because a
    bpy.props.* definition cannot be shared between two classes - each class
    needs its own object - so every caller gets a freshly built set.

    `update` is the callback Blender fires when a value changes; only the
    per-object copy passes one.

    Edge Dirt builds its own settings from this same set, so a property here
    belongs to both tools. `bevel_target` is one **nothing** reads any more:
    both tools round the source with a live modifier that always follows the
    strip (see source_bevel.py), so there is no target left to choose. It is
    still declared because strips saved before the change carry a value for it,
    and a missing property is a console error on every one of them.
    """
    return {
        "source_mode": bpy.props.EnumProperty(
            name="Build From",
            description="Where the strip runs",
            items=[
                ('SELECTION', "Selected Edges",
                 "Along the edges selected in Edit Mode - a corner where two "
                 "walls meet, or any edge of the mesh"),
                ('GROUND', "Ground Level",
                 "Along the line where the object crosses a height you give, "
                 "for something that continues past the surface it stands on. "
                 "There is no edge there to select, so the contour is worked "
                 "out by cutting a copy of the mesh - the object itself is not "
                 "touched"),
            ],
            default='SELECTION',
            update=update,
        ),
        "ground_level": bpy.props.FloatProperty(
            name="Ground Level",
            description=(
                "World height the contour is taken at. This is world Z, not a "
                "height above the object, so the floor's own level is the "
                "number to use"
            ),
            default=0.0,
            soft_min=-10.0,
            soft_max=10.0,
            subtype='DISTANCE',
            update=update,
        ),
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
        "alpha_bottom": bpy.props.FloatProperty(
            name="Alpha Bottom",
            description=(
                "Scales the whole strip's alpha at the LOW end of the run, ramping back to "
                "full at the high end. 1.0 leaves it alone. Where Alpha Center/Outer fade "
                "across the shelf, this fades along it - so a corner can let go before it "
                "reaches the floor"
            ),
            default=1.0,
            min=0.0,
            max=1.0,
            update=update,
        ),
        "alpha_top": bpy.props.FloatProperty(
            name="Alpha Top",
            description=(
                "Scales the whole strip's alpha at the HIGH end of the run, ramping back to "
                "full at the low end. 1.0 leaves it alone. Bottom and top are the building's, "
                "not the object's - a rotated source still fades toward the floor"
            ),
            default=1.0,
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
        # Two ticks, not one with a Target enum behind it. Rounding the wall
        # and rounding the decal that runs along it are separate decisions -
        # asking which "target" is a way of making the reader work out that
        # there were two things all along.
        "bevel_mesh": bpy.props.BoolProperty(
            name="Bevel Mesh",
            description=(
                "Round off the SOURCE object's corner, with a Bevel modifier driven "
                "by edge weight. Live: drag the width and the wall follows, untick it "
                "and the modifier comes off, leaving the mesh exactly as it was found. "
                "Off by default - creating a decal should not reshape the wall you ran "
                "it along unless you ask it to"
            ),
            default=False,
            update=update,
        ),
        "bevel_strip": bpy.props.BoolProperty(
            name="Bevel Strip",
            description=(
                "Round off the GENERATED strip's own seam. With Bevel Mesh on as well "
                "and the same width, the two rounds coincide and the decal sits ON the "
                "rounded corner instead of across it"
            ),
            default=False,
            update=update,
        ),
        # Kept so a strip made before the split still loads, and so anything
        # that reads it (older scripts, an F9 redo) keeps working. Nothing
        # draws it any more.
        "bevel_enabled": bpy.props.BoolProperty(
            name="Bevel",
            description="Superseded by Bevel Mesh and Bevel Strip",
            default=False,
            update=update,
        ),
        "bevel_target": bpy.props.EnumProperty(
            name="Bevel",
            description="What gets rounded off",
            items=[
                ('BOTH', "Source + Strip",
                 "Round the source edge, and build the strip so it follows that round with "
                 "the same Width and Segments"),
                ('STRIP', "Strip Only",
                 "Round off the generated strip's own seam and leave the source mesh sharp"),
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
