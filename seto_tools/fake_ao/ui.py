import bpy

from ..shared import groups, icons, manual_offset, panel_layout as pl, ui_common


def _draw_bevel(layout, settings, tool_label="Ambient Occlusion",
                show_target=False):
    """The Bevel block: two ticks, drawn on the finished strip.

    Rounding the wall and rounding the decal that runs along it are two
    decisions, so they are two checkboxes rather than one checkbox and a Target
    enum behind it - "Bevel Mesh" and "Bevel <tool>", each saying plainly which
    mesh it touches. Both are live: the source's round is a modifier and the
    strip's is rebuilt, so dragging Width moves whichever is ticked.

    `show_target` is for Edge Dirt, which still cuts its source bevel in
    destructively at creation and has a warning to show for it.
    """
    box = layout.box()
    box.label(text="Bevel", icon='MOD_BEVEL')

    ticks = box.column(align=True)
    ticks.prop(settings, "bevel_mesh", text="Bevel Mesh")
    ticks.prop(settings, "bevel_strip", text=f"Bevel {tool_label}")

    on = settings.bevel_mesh or settings.bevel_strip
    body = box.column(align=True)
    body.enabled = on
    if show_target:
        body.prop(settings, "bevel_target", text="")
    body.prop(settings, "bevel_width", text="Width")
    body.prop(settings, "bevel_segments", text="Segments")
    body.prop(settings, "bevel_profile", text="Profile Shape")

    if not on:
        return

    if settings.bevel_mesh:
        box.label(text="Modifies the source mesh.", icon='ERROR')

    if settings.bevel_width >= settings.width:
        # The round eats the shelf: there is nothing flat left for the AO to
        # fade out across, and Blender clamps the bevel, so the strip's round
        # stops matching the source's.
        note = box.column(align=True)
        note.alert = True
        note.label(text="Bevel Width is not below Width.", icon='ERROR')
        note.label(text="Raise Width to leave room to fade.")


class SETO_PT_fake_ao_panel(bpy.types.Panel):
    bl_label = "Ambient Occlusion"
    bl_idname = "SETO_PT_fake_ao_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Under the Surface section, first of its three (Decal Tool 1, Surface
    # Painter 2). It builds a strip like the two Geometry tools do, but what it
    # is for is shading a surface - which is how it gets reached for.
    bl_category = "Seto Tools"
    bl_parent_id = groups.SURFACE
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0

    def draw_header(self, context):
        icons.draw_header(self.layout, "fake_ao", 'SHADING_RENDERED')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_fake_ao

        if ui_common.draw_sollumz_warning(layout):
            return

        # Nothing that the finished strip can change lives here any more. Every
        # shape and fade setting was listed twice - once as a default, once on
        # the strip itself - and the two looked identical, so the natural thing
        # to do was drag the top one and watch nothing happen. What is left is
        # what genuinely has to be decided before there is a strip to look at:
        # where it runs, and which material it gets.
        ground = settings.source_mode == 'GROUND'
        col = pl.section(layout, "Build", 'MOD_SOLIDIFY')
        col.prop(settings, "source_mode", text="")
        if ground:
            col.prop(settings, "ground_level")
        col.prop(settings, "material_mode", text="Material")

        pl.create_button(layout, "seto.create_fake_ao",
                         "Create Ambient Occlusion", 'MOD_SOLIDIFY')

        if ground:
            pl.hint(layout, "Select the object. No Edit Mode needed.")
        else:
            pl.edit_mode_hint(layout, context)


class SETO_PT_fake_ao_object_panel(pl.SelectedPanel, bpy.types.Panel):
    """Settings of the selected Ambient Occlusion strip, editable after the fact.

    Nested under the Ambient Occlusion section rather than given its own tab, and only
    drawn when the active object is actually one of our strips. Every row here
    is live: changing it rebuilds the strip in place.
    """
    bl_label = "Selected Strip"
    bl_idname = "SETO_PT_fake_ao_object_panel"
    bl_parent_id = "SETO_PT_fake_ao_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_fake_ao_data.is_fake_ao)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        data = obj.seto_fake_ao_data

        pl.object_header(layout, obj, data)

        col = pl.section(layout, "Shape", 'MOD_SOLIDIFY')
        if data.source_mode == 'GROUND':
            # Live: the contour is re-cut at this height on every change.
            layout.prop(data, "ground_level")

        col.prop(data, "width")
        col.prop(data, "surface_offset")
        col.prop(data, "flip_direction")

        # Across the shelf first, then along the run - the two fades answer
        # different questions and used to sit in one unlabelled column.
        col = pl.section(layout, "Fade", 'IMAGE_ALPHA')
        col.prop(data, "alpha_center")
        col.prop(data, "alpha_outer")
        col.prop(data, "invert_fade")
        col.separator()
        col.prop(data, "alpha_bottom")
        col.prop(data, "alpha_top")

        manual_offset.draw(layout, data, "seto_fake_ao_data")

        if data.edge_keys:
            _draw_bevel(layout, data)
        else:
            # Ground Level: the line this runs along is not in the mesh, so
            # there is no edge to round - on either mesh.
            pl.hint(layout, "Bevel needs a selected edge.")

        if not data.live_update:
            pl.rebuild_button(layout, "seto.fake_ao_rebuild")


_classes = (SETO_PT_fake_ao_panel, SETO_PT_fake_ao_object_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
