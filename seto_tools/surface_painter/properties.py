"""Scene and object settings.

The split follows what the setting actually belongs to.

Brush size, strength, falloff, the library folder and the shell build settings
live on the Scene: they are how *you* are working right now, and carrying them
between objects is the point.

The dirt adjustments - opacity, scale, offset, rotation - live on the shell
object, because they are properties of that piece of dirt: they travel with it,
survive a save, and duplicate along with it.

Every update callback here is written to be harmless: Blender swallows
exceptions raised from a property update, so a callback that can throw turns
into a setting that silently does nothing.
"""

import math

import bpy

from . import brush
from . import library
from . import shell


def _owner_object(prop_group):
    owner = prop_group.id_data
    return owner if isinstance(owner, bpy.types.Object) else None


def rebuild_browser(settings):
    """Refill the browser list from the selected category.

    A CollectionProperty rather than a live read of the library cache, because
    template_list needs a real collection to iterate - and because a collection
    is saved in the .blend, so the grid is still populated when the file is
    reopened.

    Never called from draw(): adding to a collection during a redraw is what
    causes Blender's "modifying data in draw" crashes. The two entry points are
    the category's update callback and the Refresh operator.
    """
    settings.browser_items.clear()
    for stem, path in library.get_textures(settings.category):
        entry = settings.browser_items.add()
        entry.name = stem
        entry.path = path
        entry.tooltip = path
    settings["browser_category"] = settings.category

    # Keep the highlighted row pointing at the texture that is actually
    # selected, so the grid opens where the artist left off.
    for index, entry in enumerate(settings.browser_items):
        if entry.name == settings.texture:
            settings["browser_index"] = index
            break
    else:
        settings["browser_index"] = 0


def _on_library_changed(self, context):
    library.scan(self.custom_library_path)
    rebuild_browser(self)


def _on_category_changed(self, context):
    rebuild_browser(self)


def _on_browser_index_changed(self, context):
    """Clicking a tile in the grid selects that texture."""
    index = self.browser_index
    if 0 <= index < len(self.browser_items):
        name = self.browser_items[index].name
        try:
            self.texture = name
        except TypeError:
            # The enum no longer has it (library rescanned under us).
            pass


class SETO_PG_surface_browser_item(bpy.types.PropertyGroup):
    """One texture in the browser list."""

    path: bpy.props.StringProperty(default="")

    # Shown when the row is hovered (template_list's item_dyntip_propname).
    # Tooltips can carry text but never an image, so this is the file itself.
    tooltip: bpy.props.StringProperty(default="")


def _on_brush_changed(self, context):
    brush.apply_alpha_safe(context, self)


def _on_ghost_strength_changed(self, context):
    """Live-update every ghost currently showing."""
    for obj in bpy.data.objects:
        if shell.is_shell(obj) and shell.has_ghost(obj):
            shell.set_ghost_strength(obj, self.ghost_strength)


def _on_dirt_opacity_changed(self, context):
    obj = _owner_object(self)
    if shell.is_shell(obj):
        shell.set_opacity(obj, self.dirt_opacity)


def _on_dirt_repeat_changed(self, context):
    obj = _owner_object(self)
    if shell.is_shell(obj):
        shell.set_repeat(obj, self.dirt_repeat)


def _on_dirt_placement_changed(self, context):
    obj = _owner_object(self)
    if not shell.is_shell(obj):
        return
    shell.apply_uv_transform(obj, self.dirt_offset_u, self.dirt_offset_v,
                             self.dirt_width, self.dirt_height,
                             self.dirt_rotation)
    # Editing mesh UVs does not by itself redraw the viewport, and during a
    # drag that means the decal appears frozen while the numbers change.
    obj.data.update_tag()
    for area in getattr(getattr(context, "screen", None), "areas", ()):
        if area.type == 'VIEW_3D':
            area.tag_redraw()


class SETO_PG_surface_painter(bpy.types.PropertyGroup):
    # ---------------------------------------------------------------- library
    custom_library_path: bpy.props.StringProperty(
        name="Custom Library",
        description=(
            "Folder of texture categories to use instead of the one bundled with "
            "Seto Tools. Each subfolder is a category (dirt, grunge, mold, ...). "
            "Leave empty to use the bundled library"
        ),
        subtype='DIR_PATH',
        default="",
        update=_on_library_changed,
    )

    category: bpy.props.EnumProperty(
        name="Category",
        description="Which kind of surface texture to paint",
        items=library.category_items,
        update=_on_category_changed,
    )

    # The browser grid: every texture in the category, drawn as a large
    # thumbnail in the panel. Blender cannot put an image in a hover tooltip,
    # so showing them all at once is what replaces hovering.
    browser_items: bpy.props.CollectionProperty(type=SETO_PG_surface_browser_item)

    browser_index: bpy.props.IntProperty(
        name="Browsing",
        default=0, min=0,
        update=_on_browser_index_changed,
    )

    browser_rows: bpy.props.IntProperty(
        name="Rows",
        description="How many textures the browser shows before scrolling",
        default=8, min=1, max=40,
    )

    texture: bpy.props.EnumProperty(
        name="Texture",
        description=(
            "The texture to paint. Picking a different one and pressing START "
            "PAINT adds a new layer on top - it never retextures what is "
            "already painted"
        ),
        items=library.texture_items,
    )

    # ------------------------------------------------------------------ brush
    brush_size: bpy.props.IntProperty(
        name="Size",
        description="Brush radius, in pixels",
        default=100, min=1, max=2000, soft_max=500,
        update=_on_brush_changed,
    )

    brush_strength: bpy.props.FloatProperty(
        name="Strength",
        description="How quickly a stroke builds the dirt up",
        default=0.35, min=0.0, max=1.0, subtype='FACTOR',
        update=_on_brush_changed,
    )

    falloff: bpy.props.EnumProperty(
        name="Falloff",
        description="Shape of the brush from its centre to its edge",
        items=brush.FALLOFF_ITEMS,
        default='SMOOTH',
        update=_on_brush_changed,
    )

    erase: bpy.props.BoolProperty(
        name="Erase",
        description="Strokes remove dirt instead of adding it",
        default=False,
        update=_on_brush_changed,
    )

    # ------------------------------------------------------------ shell build
    shell_spacing: bpy.props.FloatProperty(
        name="Vertex Spacing",
        description=(
            "Distance between the paint mesh's vertices. Smaller = finer "
            "strokes and more vertices; the density comes from this, not from "
            "how the wall was modelled"
        ),
        default=0.12, min=0.02, soft_max=1.0, max=5.0, subtype='DISTANCE',
    )

    shell_offset: bpy.props.FloatProperty(
        name="Surface Offset",
        description="How far the paint mesh floats above the wall, to avoid flickering",
        default=0.005, min=0.0005, max=0.1, subtype='DISTANCE',
    )

    ghost_strength: bpy.props.FloatProperty(
        name="Preview Strength",
        description=(
            "How visible the ghosted texture is while positioning it. Preview "
            "only - it never touches the painted strokes"
        ),
        default=0.35, min=0.05, max=1.0, subtype='FACTOR',
        update=_on_ghost_strength_changed,
    )

    optimize_detail: bpy.props.FloatProperty(
        name="Detail",
        description=(
            "How much of the stroke's shape to keep when optimising. Lower "
            "keeps more vertices and reproduces the falloff more exactly; "
            "higher strips the mesh further. The texture is never affected"
        ),
        default=0.02, min=0.001, max=0.25, subtype='FACTOR',
    )

    # ---------------------------------------------------------- session state
    paint_object: bpy.props.PointerProperty(
        name="Painting",
        description="The dirt shell currently being painted",
        type=bpy.types.Object,
    )

    previous_shading: bpy.props.StringProperty(default="")


class SETO_PG_surface_object(bpy.types.PropertyGroup):
    """The dirt adjustments, living on the shell object itself."""

    dirt_opacity: bpy.props.FloatProperty(
        name="Opacity",
        description=(
            "Fade the whole dirt layer. Lossless: every stroke is kept, so "
            "turning it back up restores exactly what you painted"
        ),
        default=1.0, min=0.0, max=1.0, subtype='FACTOR',
        update=_on_dirt_opacity_changed,
    )

    dirt_offset_u: bpy.props.FloatProperty(
        name="Offset X",
        description="Slide the dirt texture sideways, without repainting anything",
        default=0.0, soft_min=-2.0, soft_max=2.0,
        update=_on_dirt_placement_changed,
    )

    dirt_offset_v: bpy.props.FloatProperty(
        name="Offset Y",
        description="Slide the dirt texture up and down, without repainting anything",
        default=0.0, soft_min=-2.0, soft_max=2.0,
        update=_on_dirt_placement_changed,
    )

    dirt_repeat: bpy.props.BoolProperty(
        name="Repeat",
        description=(
            "Tile the texture across the surface. Turn it off for a single "
            "instance - a graffiti you place once rather than a pattern"
        ),
        default=False,
        update=_on_dirt_repeat_changed,
    )

    dirt_width: bpy.props.FloatProperty(
        name="Width",
        description="How wide the dirt pattern is. 2.0 is twice as wide",
        default=1.0, min=0.01, max=100.0, soft_min=0.1, soft_max=10.0,
        update=_on_dirt_placement_changed,
    )

    dirt_height: bpy.props.FloatProperty(
        name="Height",
        description="How tall the dirt pattern is - separate from Width, so a "
                    "streak can be stretched down a wall without widening it",
        default=1.0, min=0.01, max=100.0, soft_min=0.1, soft_max=10.0,
        update=_on_dirt_placement_changed,
    )

    dirt_rotation: bpy.props.FloatProperty(
        name="Rotation",
        description="Rotation of the dirt pattern",
        default=0.0, min=-6.2832, max=6.2832, subtype='ANGLE',
        update=_on_dirt_placement_changed,
    )


_classes = (
    SETO_PG_surface_browser_item,
    SETO_PG_surface_painter,
    SETO_PG_surface_object,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_surface = bpy.props.PointerProperty(type=SETO_PG_surface_painter)
    bpy.types.Object.seto_surface_data = bpy.props.PointerProperty(type=SETO_PG_surface_object)
    # Fill the cache so Category/Texture are usable the first time the panel
    # draws. The browser itself is filled by the first category change or
    # Refresh - draw() must never build it.
    library.scan("")


def unregister():
    del bpy.types.Object.seto_surface_data
    del bpy.types.Scene.seto_surface
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
