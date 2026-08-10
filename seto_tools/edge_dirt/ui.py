import bpy

from . import textures
from ..fake_ao.ui import _draw_bevel
from ..shared import groups, icons, panel_layout as pl, ui_common


def _draw_texture_row(layout):
    """What is in the tool's textures/ folder, since that is the whole setting.

    There is no file picker here on purpose: the texture travels with the
    add-on so a scene handed to someone else looks the same on their machine.
    That only works if the panel says which file it found - otherwise an empty
    folder is invisible until the strip comes out untextured.

    The scan behind this is cached on the folder's mtime (see
    shared/bundled_textures.py) - a panel is redrawn on every mouse move, and
    this used to be a directory listing each time.
    """
    name = textures.bundled_texture_name()
    box = layout.box()
    box.scale_y = 0.8
    if name:
        box.label(text=name, icon='TEXTURE')
    else:
        column = box.column(align=True)
        column.label(text="No texture bundled.", icon='ERROR')
        column.label(text="Drop one into edge_dirt/textures/.")


class SETO_PT_edge_dirt_panel(bpy.types.Panel):
    bl_label = "Edge Dirt"
    bl_idname = "SETO_PT_edge_dirt_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Last of the Surface section (Ambient Occlusion 0, Decal Tool 1, Surface
    # Painter 2). It is built exactly like Ambient Occlusion and sits next to
    # it, which is how it gets reached for: same strip, dirt instead of shadow.
    bl_category = "Seto Tools"
    bl_parent_id = groups.SURFACE
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 3

    def draw_header(self, context):
        # The add-on's own icon; the built-in is only the fallback for a
        # checkout with icons/ missing - see shared/icons.py.
        icons.draw_header(self.layout, "edge_dirt", 'BRUSH_DATA')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_edge_dirt

        if ui_common.draw_sollumz_warning(layout):
            return

        _draw_texture_row(layout)

        # Everything the finished strip can change has been taken out of here:
        # it was listed twice, identically, and only the copy on the strip did
        # anything. What is left is what has to be true before there is a strip
        # at all - where it runs, and what it is made of.
        ground = settings.source_mode == 'GROUND'
        col = pl.section(layout, "Build", 'MOD_SOLIDIFY')
        col.prop(settings, "source_mode", text="")
        if ground:
            col.prop(settings, "ground_level")
        col.prop(settings, "material_mode", text="Material")

        pl.create_button(layout, "seto.create_edge_dirt", "Create Edge Dirt",
                         'MOD_SOLIDIFY')

        if ground:
            pl.hint(layout, "Select the object. No Edit Mode needed.")
        else:
            pl.edit_mode_hint(layout, context)


class SETO_PT_edge_dirt_object_panel(pl.SelectedPanel, bpy.types.Panel):
    """Settings of the selected Edge Dirt strip, editable after the fact.

    Nested under the Edge Dirt section rather than given its own tab, and only
    drawn when the active object is actually one of our strips. Every row here
    is live: changing it rebuilds the strip in place.
    """
    bl_label = "Selected Strip"
    bl_idname = "SETO_PT_edge_dirt_object_panel"
    bl_parent_id = "SETO_PT_edge_dirt_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_edge_dirt_data.is_edge_dirt)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        data = obj.seto_edge_dirt_data

        pl.object_header(layout, obj, data)

        col = pl.section(layout, "Shape", 'MOD_SOLIDIFY')
        col.prop(data, "width")
        col.prop(data, "surface_offset")
        col.prop(data, "flip_direction")

        # Across the strip first, then along the run - the two fades answer
        # different questions and used to sit in one unlabelled column.
        col = pl.section(layout, "Fade", 'IMAGE_ALPHA')
        col.prop(data, "alpha_center")
        col.prop(data, "alpha_outer")
        col.prop(data, "invert_fade")
        col.separator()
        col.prop(data, "alpha_bottom")
        col.prop(data, "alpha_top")

        _draw_bevel(layout, data, tool_label="Edge Dirt")

        if not data.live_update:
            pl.rebuild_button(layout, "seto.edge_dirt_rebuild")


_classes = (SETO_PT_edge_dirt_panel, SETO_PT_edge_dirt_object_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
