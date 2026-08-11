"""Analyze and Finish - the whole tool is these two operators.

Analyze measures every object in scope and writes its verdict into the
object's viewport colour; Finish puts the colours and the viewport back.
Nothing here touches mesh data: the colour lives on the Object, and the
measurements live in ID properties that Finish removes.

The session itself - who is painting, what each colour was, what the
viewport was showing - belongs to `shared/viewport_grade.py`, because
Texture Budget paints into the same place and the two must not fight over
it. What the measuring means is in `shared/mesh_stats.py`, for the same
reason: two tools grading one object have to have measured it identically.
"""

import bpy

from ..shared import mesh_stats, viewport_grade as vg
from . import geometry

# Who owns the grading session while this tool is showing.
TOOL = 'DENSITY'

# ID properties Analyze leaves on an object, all removed by Finish. The raw
# measurements rather than the verdict: the panel derives density, budget
# ratio and advice from these live, so dialling the Budget after an Analyze
# re-grades the numbers on screen without a re-run.
TRIS_PROP = "seto_density_tris"
AREA_PROP = "seto_density_area"
OWN_PROPS = (TRIS_PROP, AREA_PROP)
vg.owns(TOOL, OWN_PROPS)


def _grade(obj, settings, depsgraph):
    """Measure one object and write its verdict - colour and measurements."""
    tris, area = mesh_stats.world_mesh_stats(obj, depsgraph)
    value = geometry.ratio(tris, settings.budget, area)
    vg.paint(obj, geometry.colour(geometry.fraction(value)))
    obj[TRIS_PROP] = tris
    obj[AREA_PROP] = area
    return value


class SETO_OT_density_analyze(bpy.types.Operator):
    bl_idname = "seto.density_analyze"
    bl_label = "Analyze Density"
    bl_description = ("Colour every mesh in scope by how it spends its GTA "
                      "triangle budget - green under it, red over it")
    # No 'REGISTER', like every other button in this add-on: the scale lives
    # in the panel, where it can be read whenever it is wanted, rather than
    # in a bottom-left popup that covers the viewport and is gone on the
    # next click. Tried both, and the popup was the one that went.
    bl_options = {'UNDO'}

    def execute(self, context):
        settings = context.scene.seto_density_checker
        objects = vg.scope_objects(context, settings.scope)
        if not objects:
            self.report({'ERROR'}, "No mesh objects in scope to analyze.")
            return {'CANCELLED'}

        vg.begin(context, TOOL)
        depsgraph = context.evaluated_depsgraph_get()
        for obj in objects:
            _grade(obj, settings, depsgraph)

        self.report({'INFO'}, f"Analyzed {len(objects)} objects.")
        return {'FINISHED'}


class SETO_OT_density_clear(bpy.types.Operator):
    bl_idname = "seto.density_clear"
    bl_label = "Finish Analysis"
    bl_description = ("End the analysis: restore every object's own colour "
                      "and put the viewport shading back as it was")
    bl_options = {'UNDO'}

    def execute(self, context):
        count = vg.end(context)
        self.report({'INFO'}, f"Cleared {count} objects.")
        return {'FINISHED'}


_classes = (SETO_OT_density_analyze, SETO_OT_density_clear)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
