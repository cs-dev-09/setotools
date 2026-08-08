import textwrap

import bpy

from . import sollumz_integration as szi


def _wrap(text, width):
    return textwrap.wrap(text, width) or [""]


class SETO_PT_fake_ao_panel(bpy.types.Panel):
    bl_label = "seto_fake_ao"
    bl_idname = "SETO_PT_fake_ao_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Fake AO & Decals"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_fake_ao

        available, status_msg = szi.get_status_message()
        if not available:
            box = layout.box()
            box.label(text="Sollumz not available:", icon='ERROR')
            col = box.column(align=True)
            for line in _wrap(status_msg, 40):
                col.label(text=line)
            return

        col = layout.column(align=True)
        col.prop(settings, "width")
        col.prop(settings, "surface_offset")
        col.prop(settings, "merge_distance")

        layout.separator()
        col = layout.column(align=True)
        col.prop(settings, "alpha_center")
        col.prop(settings, "alpha_outer")
        layout.prop(settings, "invert_fade")

        layout.separator()
        layout.prop(settings, "flip_direction")
        layout.prop(settings, "material_mode")

        layout.separator()
        layout.operator("seto.create_fake_ao", text="Create Fake AO", icon='MOD_SOLIDIFY')

        if context.mode != 'EDIT_MESH':
            layout.label(text="Enter Edit Mode and select edges first.", icon='INFO')


_classes = (SETO_PT_fake_ao_panel,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
