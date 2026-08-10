"""Analyze and Finish - the whole tool is these two operators.

Analyze measures every object in scope and writes its verdict into the
object's viewport colour; Finish puts the colours and the viewport back.
Nothing here touches mesh data: the colour lives on the Object, and the
measurements live in ID properties that Finish removes.

Measuring the **evaluated** mesh is the point, not a nicety. A wall with a
live Bevel modifier - which every strip tool in this add-on adds - exports
what the modifier produces, so counting the base mesh would grade a different
object than the one that ships. Same reason the area is taken in world
space: a plane scaled 10× across covers 10× the floor, and its budget
should say so.
"""

import bpy

from . import geometry

# ID properties Analyze leaves on an object, all removed by Finish. The raw
# measurements rather than the verdict: the panel derives density, budget
# ratio and advice from these live, so dialling the Budget after an Analyze
# re-grades the numbers on screen without a re-run.
SAVED_COLOUR_PROP = "seto_density_saved_colour"
TRIS_PROP = "seto_density_tris"
AREA_PROP = "seto_density_area"


def _scope_objects(context, scope):
    """Mesh objects the scope names, read through the view layer.

    `context.selected_objects` and `context.visible_objects` are screen state
    and background Blender has no screen - the view layer is what actually
    exists everywhere the tests run.
    """
    objects = context.view_layer.objects
    if scope == 'SELECTED':
        pool = [obj for obj in objects if obj.select_get()]
    else:
        pool = [obj for obj in objects if obj.visible_get()]
    return [obj for obj in pool if obj.type == 'MESH']


def _world_mesh_stats(obj, depsgraph):
    """Triangle count and world-space area of the mesh Sollumz would export."""
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        mesh.calc_loop_triangles()
        matrix = eval_obj.matrix_world
        coords = [matrix @ vertex.co for vertex in mesh.vertices]
        area = 0.0
        for tri in mesh.loop_triangles:
            a, b, c = (coords[i] for i in tri.vertices)
            area += (b - a).cross(c - a).length
        return len(mesh.loop_triangles), area * 0.5
    finally:
        eval_obj.to_mesh_clear()


def _grade(obj, settings, depsgraph):
    """Measure one object and write its verdict - colour and measurements."""
    tris, area = _world_mesh_stats(obj, depsgraph)
    value = geometry.ratio(tris, settings.budget, area)
    # Only the first grading saves the colour: running it again must not
    # overwrite the user's own colour with last run's verdict.
    if SAVED_COLOUR_PROP not in obj:
        obj[SAVED_COLOUR_PROP] = list(obj.color)
    obj.color = geometry.colour(geometry.fraction(value))
    obj[TRIS_PROP] = tris
    obj[AREA_PROP] = area
    return value


def _view3d_shadings(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield space.shading


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
        objects = _scope_objects(context, settings.scope)
        if not objects:
            self.report({'ERROR'}, "No mesh objects in scope to analyze.")
            return {'CANCELLED'}

        depsgraph = context.evaluated_depsgraph_get()
        for obj in objects:
            _grade(obj, settings, depsgraph)

        # Object colours are invisible under the default Material shading, so
        # flip the viewport - remembering what it showed before, once, for the
        # same reason the object colours are saved once. Saved even when it
        # already was 'OBJECT': Finish restores this verbatim, and a viewport
        # that started on Object colours should end on them.
        for shading in _view3d_shadings(context):
            if not settings.saved_shading:
                settings.saved_shading = shading.color_type
            if shading.color_type != 'OBJECT':
                shading.color_type = 'OBJECT'

        settings.active = True
        self.report({'INFO'}, f"Analyzed {len(objects)} objects.")
        return {'FINISHED'}


class SETO_OT_density_clear(bpy.types.Operator):
    bl_idname = "seto.density_clear"
    bl_label = "Finish Analysis"
    bl_description = ("End the analysis: restore every object's own colour "
                      "and put the viewport shading back as it was")
    bl_options = {'UNDO'}

    def execute(self, context):
        settings = context.scene.seto_density_checker

        # Every object in the file, not the current scope: the scope may have
        # changed since Analyze ran, and a Finish that misses objects leaves
        # stale verdicts behind.
        count = 0
        for obj in bpy.data.objects:
            if SAVED_COLOUR_PROP in obj:
                obj.color = list(obj[SAVED_COLOUR_PROP])
                del obj[SAVED_COLOUR_PROP]
                count += 1
            for prop in (TRIS_PROP, AREA_PROP):
                if prop in obj:
                    del obj[prop]

        restore = settings.saved_shading or 'MATERIAL'
        for shading in _view3d_shadings(context):
            if shading.color_type == 'OBJECT':
                shading.color_type = restore
        settings.saved_shading = ""
        settings.active = False

        self.report({'INFO'}, f"Cleared {count} objects.")
        return {'FINISHED'}


_classes = (SETO_OT_density_analyze, SETO_OT_density_clear)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
