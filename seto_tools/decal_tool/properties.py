import math

import bpy
from bpy.app.handlers import persistent

from . import library
from . import preferences
from ..shared import sollumz_integration as szi
from ..shared import vertex_color


def rebuild_browser(settings):
    """Refill the texture browser from the selected category.

    The same list Surface Painter uses, for the same reason: a dropdown can
    only show a thumbnail on the row you happen to be hovering, and choosing a
    decal is choosing a picture. A CollectionProperty rather than a live read
    of the library cache, because template_list needs a real collection to
    iterate - and a collection is saved in the .blend, so the list is still
    filled when the file is reopened.

    **Never called from draw().** Adding to a collection during a redraw is
    what causes Blender's "modifying data in draw" crashes. The entry points
    are the category's update callback, the library path's, and Refresh.
    """
    settings.browser_items.clear()
    for stem, path in library.get_textures(settings.category):
        entry = settings.browser_items.add()
        entry.name = stem
        entry.path = path
        entry.tooltip = path

    # Keep the highlighted row on the texture that is actually selected, so
    # the list opens where it was left.
    for index, entry in enumerate(settings.browser_items):
        if entry.name == settings.texture:
            settings["browser_index"] = index
            break
    else:
        settings["browser_index"] = 0


def _on_category_changed(self, context):
    rebuild_browser(self)


def _on_browser_index_changed(self, context):
    """Clicking a row selects that texture."""
    index = self.browser_index
    if 0 <= index < len(self.browser_items):
        try:
            self.texture = self.browser_items[index].name
        except TypeError:
            # The enum no longer has it (library rescanned under us).
            pass


class SETO_PG_decal_browser_item(bpy.types.PropertyGroup):
    """One texture in the browser list."""

    path: bpy.props.StringProperty(default="")

    # Shown on hover (template_list's item_dyntip_propname). A tooltip can
    # carry text but never an image, so this is the file itself.
    tooltip: bpy.props.StringProperty(default="")


class SETO_PG_decal_settings(bpy.types.PropertyGroup):
    # The library folder itself is NOT here - it lives in the add-on preferences
    # so it is remembered across files and restarts. See preferences.py.
    category: bpy.props.EnumProperty(
        name="Category",
        description="Decal category - one subfolder of the decal library",
        items=library.category_items,
        update=_on_category_changed,
    )
    texture: bpy.props.EnumProperty(
        name="Texture",
        description="Decal texture from the selected category",
        items=library.texture_items,
    )

    browser_items: bpy.props.CollectionProperty(type=SETO_PG_decal_browser_item)

    browser_index: bpy.props.IntProperty(
        name="Texture",
        default=0,
        update=_on_browser_index_changed,
    )

    browser_rows: bpy.props.IntProperty(
        name="Rows",
        description="How many textures the browser shows at once",
        default=8, min=3, max=30,
    )

    merge_coplanar: bpy.props.BoolProperty(
        name="Merge Coplanar",
        description=(
            "Treat touching faces that lie in the same plane as one surface, so a wall "
            "split into several quads takes a single decal centred on the whole wall "
            "instead of one decal per quad. Turn off to get one decal per selected face"
        ),
        default=True,
    )

    color_preset: bpy.props.EnumProperty(
        name="Color Preset",
        description="Quick-pick a named vertex colour, or choose Custom to set your own",
        items=vertex_color.enum_items(),
        default='GREEN',
    )
    color_rgb: bpy.props.FloatVectorProperty(
        name="Color 1 RGB",
        description="RGB written to Color 1 for every vertex",
        subtype='COLOR', size=3, min=0.0, max=1.0,
        default=vertex_color.DEFAULT_RGB,
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
    edge_fade: bpy.props.FloatProperty(
        name="Edge Fade",
        description=(
            "Width of the border ring around the decal. Its vertices are held at "
            "alpha 0, so the decal dissolves into the surface instead of ending on a "
            "hard rectangular outline. Capped at just under half the decal, so a fade "
            "wider than the decal blunts rather than turning it inside out"
        ),
        default=0.1,
        min=0.0,
        soft_max=1.0,
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

    material_mode: bpy.props.EnumProperty(
        name="Material",
        description=f"How to obtain the {szi.DECAL_SHADER_FILENAME} Sollumz material",
        items=[
            ('AUTO', "Reuse",
             "Reuse a decal material previously created by this tool for the same "
             "texture file if one is found, otherwise create a new one"),
            ('NEW', "Create",
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


# The browser item registers first: SETO_PG_decal_settings points at it.
_classes = (SETO_PG_decal_browser_item, SETO_PG_decal_settings)


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
