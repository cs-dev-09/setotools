import bpy

from ..shared import budget as budget_scale, groups, icons
from ..shared import panel_layout as pl, viewport_grade as vg
from . import geometry, legend, operators


def _verdict(fraction):
    """Where a mesh sits against the texel target, said without scolding.

    Same five bands as the Density Check, same reason for the tone: a hero
    prop earning a big sheet is not a mistake, and the author is the one who
    knows. The top band names the size that would fit instead of raising an
    alarm - it is the one piece of advice a user can act on immediately.
    """
    if fraction <= 0.0:
        return 'CHECKMARK', "Light on texture. Room to spare."
    if fraction < 0.5:
        return 'CHECKMARK', "Vanilla territory. Right at home."
    if fraction < 0.75:
        return 'INFO', "Sharper than vanilla. Fine up close."
    if fraction < 1.0:
        return 'INFO', "Well above vanilla. Hero-prop territory."
    return 'TEXTURE', "Far above vanilla for its size."


class SETO_PT_texture_budget_panel(bpy.types.Panel):
    bl_label = "Texture Budget"
    bl_idname = "SETO_PT_texture_budget_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_parent_id = groups.ANALYSIS
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 1

    # Like the Density Check, no Sollumz warning: reading image sizes needs
    # nothing beyond Blender.

    def draw_header(self, context):
        icons.draw_header(self.layout, "texture_budget", 'TEXTURE')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_texture_budget
        active = vg.is_active(context, operators.TOOL)

        col = pl.section(layout, "Target", 'TEXTURE')
        col.prop(settings, "target")
        col.prop(settings, "scope")

        pl.create_button(layout, "seto.texture_analyze",
                         "Re-Analyze" if active else "Analyze Textures",
                         'SHADING_TEXTURE')

        if not active:
            # Not "nothing above 512" - that was written from a partial
            # count and is wrong. Franklin's house tops out at 1024, and
            # 256 is its commonest size by a wide margin.
            pl.hint(layout, "Vanilla GTA tops out at 1024. Most of it is 256.")
            return

        row = layout.row()
        row.scale_y = 1.4
        row.operator("seto.texture_clear", text="Finish Analysis",
                     icon='LOOP_BACK')

        # The number a server owner actually argues about, first.
        col = pl.section(layout, "Scene total", 'IMAGE_DATA')
        vram = geometry.vram_bytes(settings.total_pixels)
        col.label(text=f"{settings.image_count} textures, "
                       f"≈{geometry.format_bytes(vram)} VRAM")
        if settings.biggest_name:
            col.label(text=f"Largest: {settings.biggest_name} "
                           f"(~{settings.biggest_size}px)")
        col.separator()
        foot = col.column(align=True)
        foot.scale_y = 0.8
        foot.label(text="Estimate: 1 byte/px with mips.")
        foot.label(text="Franklin's house: ≈55 MB. 592 of its 601")
        foot.label(text="textures are 512² or smaller; the other")
        foot.label(text="nine reach 1024, none go past it.")

        obj = context.active_object
        if obj is not None and operators.TEXELS_PROP in obj:
            box = layout.box()
            col = box.column(align=True)
            col.label(text=obj.name, icon='OUTLINER_OB_MESH')
            texels = obj[operators.TEXELS_PROP]
            area = obj[operators.AREA_PROP]
            pixels = obj[operators.PIXELS_PROP]
            if texels == operators.NO_TEXTURE:
                col.label(text="No texture on it - nothing to grade.",
                          icon='INFO')
            else:
                side = int(round(pixels ** 0.5))
                col.label(text=f"~{side}px over {area:.2f} m²")
                col.label(text=f"{texels:.0f} texels/m")
                value = geometry.ratio(pixels, area, settings.target)
                icon, advice = _verdict(budget_scale.fraction(value))
                col.label(text=f"{value:.1f}× of the target")
                col.label(text=advice, icon=icon)
                if value >= 1.0:
                    fits = geometry.suggested_size(area, settings.target)
                    col.label(text=f"{fits}² would hit the target.",
                              icon='INFO')
                col.separator()
                col.label(text="All its textures: "
                               f"≈{geometry.format_bytes(obj[operators.BYTES_PROP])}")
        else:
            pl.hint(layout, "Select an analyzed object for its numbers.")

        # Same block the Density Check draws, in this tool's units - see
        # legend.py.
        col = pl.section(layout, "What the colours mean", 'COLOR')
        legend.draw(col)


_classes = (SETO_PT_texture_budget_panel,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
