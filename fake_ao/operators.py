import re

import bpy
import bmesh

from . import geometry
from . import sollumz_integration as szi

_NAME_PATTERN = re.compile(r"^seto_fakeao_(\d{3,})$")
_UV_SCALE_DELTA = -0.08


def _next_fake_ao_name():
    """Explicit sequential naming (seto_fakeao_001, _002, ...) instead of
    relying on Blender's automatic .001 suffixing."""
    max_n = 0
    for name in bpy.data.objects.keys():
        match = _NAME_PATTERN.match(name)
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"seto_fakeao_{max_n + 1:03d}"


def _parent_keep_transform(child, parent):
    """Parent `child` to `parent` without visually moving it, regardless of
    the parent's own transform."""
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def _select_only(context, obj):
    for other in context.selected_objects:
        if other is not obj:
            other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _apply_cube_projection(obj):
    """Equivalent of manually entering Edit Mode, selecting all faces, and
    running UV > Cube Projection - done automatically so the user never has
    to touch Edit Mode for this."""
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    for f in bm.faces:
        f.select = True
    bmesh.update_edit_mesh(obj.data)
    if obj.data.uv_layers:
        obj.data.uv_layers.active_index = 0
    bpy.ops.uv.cube_project()
    bpy.ops.object.mode_set(mode='OBJECT')
    geometry.scale_active_uvs(obj.data, _UV_SCALE_DELTA)


def _set_origin_to_geometry(obj):
    """Equivalent of Object > Set Origin > Origin to Geometry. Assumes `obj`
    is already the only selected/active object (see _select_only)."""
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')


class SETO_OT_create_fake_ao(bpy.types.Operator):
    """Generate a separate Fake AO decal strip along the selected edges"""
    bl_idname = "seto.create_fake_ao"
    bl_label = "Create Fake AO"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None
            and obj.type == 'MESH'
            and context.mode == 'EDIT_MESH'
            and szi.is_sollumz_available()
        )

    def execute(self, context):
        if not szi.is_sollumz_available():
            self.report({'ERROR'}, "Sollumz is not enabled/available. Seto Fake AO & Decals requires Sollumz.")
            return {'CANCELLED'}

        settings = context.scene.seto_fake_ao
        source_obj = context.active_object
        source_mesh = source_obj.data

        # Read the current edge selection while still in Edit Mode. All values
        # are copied out as plain Vectors (local space), so they stay valid
        # after we leave edit mode below.
        bm = bmesh.from_edit_mesh(source_mesh)
        segments, skipped = geometry.gather_selected_edge_segments(bm)

        if not segments:
            self.report({'WARNING'}, "No usable selected edges found (an edge needs at least one adjacent face).")
            return {'CANCELLED'}

        strip_data = geometry.build_strip_mesh_data(
            segments,
            width=settings.width,
            surface_offset=settings.surface_offset,
            alpha_center=settings.alpha_center,
            alpha_outer=settings.alpha_outer,
            invert_fade=settings.invert_fade,
            flip_direction=settings.flip_direction,
        )
        if not strip_data.faces:
            self.report({'WARNING'}, "Could not generate strip geometry from the selected edges (degenerate geometry?).")
            return {'CANCELLED'}

        # Leave Edit Mode now that we're done reading the source BMesh, so we
        # can safely create/select/parent a new object.
        bpy.ops.object.mode_set(mode='OBJECT')

        new_name = _next_fake_ao_name()
        new_mesh = geometry.create_mesh_from_strip_data(new_name, strip_data)
        loop_uv, loop_rgba = geometry.compute_loop_uv_and_alpha(
            new_mesh, strip_data, color_rgb=tuple(settings.color_rgb)
        )

        # UVMap 0 / Color 1: hard dependency on Sollumz, must succeed or the
        # tool has failed at its core job.
        try:
            szi.write_uv_and_color(new_mesh, loop_uv, loop_rgba)
        except szi.SollumzUnavailableError as e:
            bpy.data.meshes.remove(new_mesh)
            self.report({'ERROR'}, f"Sollumz became unavailable while creating UV/Color data: {e}")
            return {'CANCELLED'}

        # Weld near-duplicate vertices (e.g. the two wings of an L-shaped
        # corner meeting at the same edge) - safe to do now since both wings
        # already carry matching UV/Color data at their shared inner edge.
        geometry.merge_by_distance(new_mesh, settings.merge_distance)

        new_obj = bpy.data.objects.new(new_name, new_mesh)

        # The strip was built entirely in source_obj's local space, so copying
        # its world matrix places it exactly on the source geometry regardless
        # of the source object's translation/rotation/non-uniform scale.
        new_obj.matrix_world = source_obj.matrix_world.copy()

        target_collections = source_obj.users_collection or (context.collection,)
        for coll in target_collections:
            coll.objects.link(new_obj)

        # Select only the new object so every subsequent bpy.ops call below
        # (parenting aside) unambiguously targets it, not the source object
        # or anything else that happened to be selected.
        _select_only(context, new_obj)

        # Only parent into a Sollumz Drawable hierarchy if the source object
        # already belongs to one. Otherwise the strip is left fully
        # unparented as an independent object (still placed correctly via
        # the matrix_world copy above).
        drawable_root = szi.find_drawable_parent(source_obj)
        if drawable_root is not None:
            _parent_keep_transform(new_obj, drawable_root)
            try:
                szi.convert_to_drawable_model(new_obj)
            except Exception as e:
                self.report({'WARNING'}, f"'{new_name}' was created, but could not be registered as a Drawable Model: {e}")

        # Shader assignment is best-effort: geometry generation is the primary
        # function of this tool, so a shader failure must not remove the mesh.
        shader_warning = None
        try:
            material = szi.find_or_create_decal_material(reuse=(settings.material_mode == 'AUTO'))
            szi.assign_material_to_object(new_obj, material)
        except szi.SollumzShaderError as e:
            shader_warning = str(e)
        except Exception as e:
            shader_warning = f"unexpected error: {e}"

        # Automatic UV Cube Projection - no manual Edit Mode step required.
        try:
            _apply_cube_projection(new_obj)
        except Exception as e:
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            self.report({'WARNING'}, f"Fake AO mesh created, but automatic Cube Projection failed: {e}")

        # Automatic Origin to Geometry - equivalent to Object > Set Origin > Origin to Geometry.
        _select_only(context, new_obj)
        try:
            _set_origin_to_geometry(new_obj)
        except Exception as e:
            self.report({'WARNING'}, f"Fake AO mesh created, but setting Origin to Geometry failed: {e}")

        msg = f"Created '{new_name}' with {len(strip_data.faces)} strip quad(s)."
        if skipped:
            msg += f" Skipped {skipped} edge(s) with no adjacent face."
        self.report({'INFO'}, msg)

        if shader_warning:
            self.report({'WARNING'}, f"Fake AO mesh created, but {szi.DECAL_SHADER_FILENAME} assignment failed: {shader_warning}")

        return {'FINISHED'}


_classes = (SETO_OT_create_fake_ao,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
