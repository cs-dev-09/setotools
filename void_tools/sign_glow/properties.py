"""Scene-level settings: the two things you decide *before* there is a glow.

Everything else about a halo - its two blur radii, their intensities, how far
behind the letters the plane sits - is only meaningful once you can see the
thing, so it lives on the created object and is live there (see
`object_settings.py`). Listing those settings here as well would repeat the
mistake this add-on already made once, where a panel drew seven rows that did
nothing because only the copy on the created object was read.

Resolution and Colour are the exceptions, and they are exceptions for a
reason: they are the two that decide what gets *generated*. A 1024 texture on
a small sign is wasted VRAM in an interior that already has a budget panel
complaining about it, and a halo generated in the wrong colour is a rebuild
you did not need. Both stay live on the object afterwards.
"""

import bpy


# The long side of the generated texture, in pixels. The short side follows the
# sign's aspect ratio, so these are not the final image size - they are the
# quality setting.
RESOLUTIONS = (
    ('256', "256", "Small signs, or a lot of them"),
    ('512', "512", "The default - a readable halo at arm's length in game"),
    ('1024', "1024", "Hero signage seen up close"),
)

DEFAULT_COLOUR = (0.45, 0.85, 1.0, 1.0)


def annotations(update=None):
    """The create-time settings, shared with the per-object group.

    One definition for both, so the value the object starts with and the value
    it carries afterwards cannot drift apart in their ranges or their tooltips.
    `update` is what makes the object's copy live; the Scene's copy has none,
    because changing a default rebuilds nothing.
    """
    return {
        "resolution": bpy.props.EnumProperty(
            name="Resolution",
            description="Pixels along the longer side of the generated halo texture",
            items=RESOLUTIONS,
            default='512',
            update=update,
        ),
        "color": bpy.props.FloatVectorProperty(
            name="Colour",
            description="The colour the halo glows. Alpha scales the whole halo's strength",
            subtype='COLOR',
            size=4,
            min=0.0,
            max=1.0,
            default=DEFAULT_COLOUR,
            update=update,
        ),
    }


class SETO_PG_sign_glow(bpy.types.PropertyGroup):
    __annotations__ = annotations()


def register():
    bpy.utils.register_class(SETO_PG_sign_glow)
    bpy.types.Scene.seto_sign_glow = bpy.props.PointerProperty(
        type=SETO_PG_sign_glow)


def unregister():
    del bpy.types.Scene.seto_sign_glow
    bpy.utils.unregister_class(SETO_PG_sign_glow)
