import bpy

from ..shared import groups, icons, panel_layout as pl, viewport_grade as vg
from . import geometry, legend, operators


def _verdict(fraction):
    """Icon and one line for where a mesh sits against the budget.

    The scale is multiples of what vanilla GTA V spends on a mesh this size
    (see properties.py), so the line reads in those terms - and it reports
    rather than tells off. A mesh over budget is not a mistake: hero props
    are meant to be, and the author is the one who knows whether this is
    one. No warning triangles either; the highest band offers the fix
    instead of raising an alarm.
    """
    if fraction <= 0.0:
        return 'CHECKMARK', "Very light. Plenty of headroom."
    if fraction < 0.5:
        return 'CHECKMARK', "Vanilla territory. Right at home."
    if fraction < 0.75:
        return 'INFO', "A little above vanilla. Fine for detail."
    if fraction < 1.0:
        return 'INFO', "Richer than vanilla. Hero-prop territory."
    return 'MOD_DECIM', "Well above vanilla. A LOD or retopo would help."


def _draw_calls(layout, obj):
    """The other half of what a mesh costs, and the cheaper half to fix.

    Each material on an object is a draw call, and in GTA those are often
    dearer than the triangles under them. Vanilla is blunt about it: across
    Franklin's house the median mesh has exactly **one** material and two
    thirds have no more than one, so a prop carrying eight is not detailed,
    it is unmerged. Reported as a line rather than folded into the colour -
    the colour is the triangle verdict, and one number per colour is what
    makes it readable.
    """
    count = len([slot for slot in obj.material_slots if slot.material])
    empty = len(obj.material_slots) - count
    row = layout.row()
    row.label(text=f"{count} material{'s' if count != 1 else ''}"
                   f" = {count} draw call{'s' if count != 1 else ''}")
    if count > 4:
        layout.label(text="Vanilla's median is 1. Merging would help.",
                     icon='INFO')
    if empty:
        layout.label(text=f"{empty} empty material slot"
                          f"{'s' if empty != 1 else ''}.", icon='INFO')


class SETO_PT_density_checker_panel(bpy.types.Panel):
    bl_label = "Density Check"
    bl_idname = "SETO_PT_density_checker_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = pl.TAB
    bl_parent_id = groups.ANALYSIS
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0

    # No Sollumz warning here, deliberately: the other tools cannot build
    # their materials without it, but counting triangles needs nothing beyond
    # Blender, and a budget pass is exactly what someone might want on a
    # machine that has no Sollumz at all.

    def draw_header(self, context):
        icons.draw_header(self.layout, "density_checker", 'MOD_DECIM')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_density_checker
        active = vg.is_active(context, operators.TOOL)

        col = pl.section(layout, "Budget", 'MESH_DATA')
        col.prop(settings, "budget")
        col.prop(settings, "scope")

        pl.create_button(layout, "seto.density_analyze",
                         "Re-Analyze" if active else "Analyze Density",
                         'SHADING_SOLID')

        if not active:
            pl.hint(layout, "Colours every mesh by what vanilla GTA spends.")
            return

        # As prominent as Analyze: this is the way back. It restores every
        # object's own colour and the viewport shading, verbatim.
        row = layout.row()
        row.scale_y = 1.4
        row.operator("seto.density_clear", text="Finish Analysis",
                     icon='LOOP_BACK')

        obj = context.active_object
        if obj is not None and operators.TRIS_PROP in obj:
            box = layout.box()
            col = box.column(align=True)
            col.label(text=obj.name, icon='OUTLINER_OB_MESH')
            tris = obj[operators.TRIS_PROP]
            area = obj[operators.AREA_PROP]
            value = geometry.ratio(tris, settings.budget, area)
            if value is None:
                col.label(text=f"{tris} triangles, no measurable surface")
                col.label(text="Nothing to measure against here.",
                          icon='INFO')
            else:
                density = geometry.density(tris, area)
                col.label(text=f"{tris} triangles, {density:.0f} tris/m²")
                col.label(text=f"{value:.1f}× of the GTA budget")
                icon, advice = _verdict(geometry.fraction(value))
                col.label(text=advice, icon=icon)
            col.separator()
            _draw_calls(col, obj)
        else:
            pl.hint(layout, "Select an analyzed object for its numbers.")

        # What the colours mean and where the numbers come from, in the
        # panel rather than in a popup - see legend.py.
        col = pl.section(layout, "What the colours mean", 'COLOR')
        legend.draw(col)


_classes = (SETO_PT_density_checker_panel,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
