"""The sections the "Seto Tools" tab is split into.

Six tools side by side in one tab is a wall of collapsible headers with no
hint of which one to reach for. They divide cleanly by what they actually
produce, so the tab opens on sections and the tools nest inside them:

    Geometry   builds new mesh along the selected edges
      Edge Wear, Smooth Edge
    Surface    puts texture on a surface that already exists
      Ambient Occlusion, Decal Tool, Surface Painter, Edge Dirt
    Analysis   reads the scene and reports, builds nothing
      Density Check

These panels are the only top-level panels in the add-on. They own no
settings and draw nothing - a group header is all they are - but they have to
be **registered before** any tool, because Blender resolves `bl_parent_id` at
registration time and drops a child whose parent is not there yet.

Ambient Occlusion sits under Surface rather than with the other two strip tools: it is a
strip in how it is built, but what it is for is shading a surface, which is how
the user reaches for it.
"""

import bpy

from . import icons
from . import sollumz_integration as szi
from . import strip_settings


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
        # The strip's shape, drawn once for both tools below it - see
        # strip_settings. Nothing when Sollumz is missing: each tool says so
        # itself, and repeating the warning three times down one tab is worse
        # than saying it where the buttons are.
        if not szi.get_status_message()[0]:
            return
        strip_settings.draw(self.layout, strip_settings.get(context))


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


class SETO_PT_analysis_group(bpy.types.Panel):
    bl_label = "Analysis"
    bl_idname = "SETO_PT_analysis_group"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_order = 2

    def draw_header(self, context):
        icons.draw_header(self.layout, "analysis", 'VIEWZOOM')

    def draw(self, context):
        pass


GEOMETRY = SETO_PT_geometry_group.bl_idname
SURFACE = SETO_PT_surface_group.bl_idname
ANALYSIS = SETO_PT_analysis_group.bl_idname

_classes = (SETO_PT_geometry_group, SETO_PT_surface_group,
            SETO_PT_analysis_group)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
