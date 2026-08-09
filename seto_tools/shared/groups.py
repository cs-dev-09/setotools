"""The two sections the "Seto Tools" tab is split into.

Five tools side by side in one tab is a wall of collapsible headers with no
hint of which one to reach for. They divide cleanly by what they actually
produce, so the tab now opens on two sections and the tools nest inside them:

    Geometry   builds new mesh along the selected edges
      Fake Damage, Smooth Edge
    Surface    puts texture on a surface that already exists
      Fake AO, Decal Tool, Surface Painter

These two panels are the only top-level panels in the add-on. They own no
settings and draw nothing - a group header is all they are - but they have to
be **registered before** any tool, because Blender resolves `bl_parent_id` at
registration time and drops a child whose parent is not there yet.

Fake AO sits under Surface rather than with the other two strip tools: it is a
strip in how it is built, but what it is for is shading a surface, which is how
the user reaches for it.
"""

import bpy

from . import icons


class SETO_PT_geometry_group(bpy.types.Panel):
    bl_label = "Geometry"
    bl_idname = "SETO_PT_geometry_group"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_order = 0

    def draw_header(self, context):
        icons.draw_header(self.layout, "geometry", 'MESH_DATA')

    def draw(self, context):
        pass


class SETO_PT_surface_group(bpy.types.Panel):
    bl_label = "Surface"
    bl_idname = "SETO_PT_surface_group"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_order = 1

    def draw_header(self, context):
        icons.draw_header(self.layout, "surface", 'MATERIAL')

    def draw(self, context):
        pass


GEOMETRY = SETO_PT_geometry_group.bl_idname
SURFACE = SETO_PT_surface_group.bl_idname

_classes = (SETO_PT_geometry_group, SETO_PT_surface_group)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
