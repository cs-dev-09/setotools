import re

import bpy
import bmesh

from . import geometry
from . import sollumz_integration as szi

_NAME_PATTERN = re.compile(r"^Fake_Damage_(\d{3,})$")

# Applied to the UVs straight after the Conformal unwrap, which normalises
# every island into the 0..1 square - the equivalent of selecting all in the
# UV editor and pressing S, 1.5.
_UV_SCALE = 1.5


def _next_fake_damage_name():
    """Explicit sequential naming (Fake_Damage_001, _002, ...) instead of
    relying on Blender's automatic .001 suffixing."""
    max_n = 0
    for name in bpy.data.objects.keys():
        match = _NAME_PATTERN.match(name)
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"Fake_Damage_{max_n + 1:03d}"


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


def _apply_conformal_unwrap(obj):
    """Equivalent of manually entering Edit Mode, selecting all faces, running
    UV > Unwrap with the Conformal method, then scaling the result by
    _UV_SCALE - done automatically so the user never has to touch Edit Mode.

    Replaces the arc-length UVs geometry.py authored; those remain the
    fallback if this fails.
    """
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    for f in bm.faces:
        f.select = True
    bmesh.update_edit_mesh(obj.data)
    if obj.data.uv_layers:
        obj.data.uv_layers.active_index = 0
    bpy.ops.uv.unwrap(method='CONFORMAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    geometry.scale_active_uvs(obj.data, _UV_SCALE)


def _set_origin_to_geometry(obj):
    """Equivalent of Object > Set Origin > Origin to Geometry. Assumes `obj`
    is already the only selected/active object (see _select_only)."""
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')


class SETO_OT_create_fake_damage(bpy.types.Operator):
    """Generate a separate Fake Damage decal strip along the selected edges"""
    bl_idname = "seto.create_fake_damage"
    bl_label = "Create Fake Damage"
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
            self.report({'ERROR'}, "Sollumz is not enabled/available. Seto Fake Damage requires Sollumz.")
            return {'CANCELLED'}

        settings = context.scene.seto_fake_damage
        source_obj = context.active_object
        source_mesh = source_obj.data

        # Read the edge selection while still in Edit Mode. Everything is
        # copied out as plain Vectors (source-object local space) so it stays
        # valid after we leave edit mode below.
        bm = bmesh.from_edit_mesh(source_mesh)
        edges, coords, skipped = geometry.gather_selected_edges(bm)

        if not edges:
            self.report({'WARNING'}, "No usable selected edges found (an edge needs at least one adjacent face).")
            return {'CANCELLED'}

        chains = geometry.build_edge_chains(edges)
        strip_data = geometry.build_damage_mesh_data(
            edges,
            chains,
            coords,
            width=settings.width,
            surface_offset=settings.surface_offset,
            alpha_center=settings.alpha_center,
            alpha_outer=settings.alpha_outer,
            invert_fade=settings.invert_fade,
            flip_direction=settings.flip_direction,
        )
        if not strip_data.faces:
            self.report({'WARNING'}, "Could not generate damage geometry from the selected edges (degenerate geometry?).")
            return {'CANCELLED'}

        # Done reading the source BMesh - leave Edit Mode so we can safely
        # create/select/parent a new object. The source mesh is never modified.
        bpy.ops.object.mode_set(mode='OBJECT')

        new_name = _next_fake_damage_name()
        new_mesh = geometry.create_mesh_from_strip_data(new_name, strip_data)
        loop_uv, loop_rgba = geometry.compute_loop_uv_and_alpha(
            new_mesh, strip_data, color_rgb=tuple(settings.color_rgb)
        )

        # UVMap 0 / Color 1: decal_normal_only's vertex layout requires both
        # TexCoord0 and Colour0, so this must succeed or the tool has failed.
        # The attribute has to exist before the Conformal unwrap below can
        # write into it.
        try:
            szi.write_uv_and_color(new_mesh, loop_uv, loop_rgba)
        except szi.SollumzUnavailableError as e:
            bpy.data.meshes.remove(new_mesh)
            self.report({'ERROR'}, f"Sollumz became unavailable while creating UV/Color data: {e}")
            return {'CANCELLED'}

        # Cleanup runs once, on the finished mesh containing every chain -
        # never per chain - so sections that meet at a junction get a chance to
        # weld to each other. Geometry inside a single chain is already
        # continuous by construction and has nothing to merge.
        geometry.merge_by_distance(new_mesh, settings.merge_distance)

        new_obj = bpy.data.objects.new(new_name, new_mesh)

        # Built entirely in source_obj's local space, so copying its world
        # matrix places the strip exactly on the source geometry regardless of
        # the source object's translation/rotation/non-uniform scale.
        new_obj.matrix_world = source_obj.matrix_world.copy()

        target_collections = source_obj.users_collection or (context.collection,)
        for coll in target_collections:
            coll.objects.link(new_obj)

        # Select only the new object so every subsequent bpy.ops call below
        # unambiguously targets it, not the source object.
        _select_only(context, new_obj)

        # Only parent into a Sollumz Drawable hierarchy if the source object
        # already belongs to one; otherwise the strip stays an independent
        # object, still placed correctly via the matrix_world copy above.
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
        missing_params = []
        try:
            material, missing_params = szi.find_or_create_damage_material(
                reuse=(settings.material_mode == 'AUTO'),
            )
            szi.assign_material_to_object(new_obj, material)
        except szi.SollumzShaderError as e:
            shader_warning = str(e)
        except Exception as e:
            shader_warning = f"unexpected error: {e}"

        # Automatic Conformal unwrap + UV scale - no manual Edit Mode step
        # required. Runs after the material is assigned so it operates on the
        # UV layer the shader actually uses.
        try:
            _apply_conformal_unwrap(new_obj)
        except Exception as e:
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            self.report({'WARNING'}, f"Fake Damage mesh created, but automatic Conformal unwrap failed: {e}")

        # Automatic Origin to Geometry - equivalent to Object > Set Origin > Origin to Geometry.
        _select_only(context, new_obj)
        try:
            _set_origin_to_geometry(new_obj)
        except Exception as e:
            self.report({'WARNING'}, f"Fake Damage mesh created, but setting Origin to Geometry failed: {e}")

        msg = (f"Created '{new_name}': {len(chains)} chain(s), "
               f"{len(strip_data.faces)} quad(s).")
        if skipped:
            msg += f" Skipped {skipped} unusable edge(s)."
        self.report({'INFO'}, msg)

        if shader_warning:
            self.report({'WARNING'}, f"Fake Damage mesh created, but {szi.DAMAGE_SHADER_FILENAME} assignment failed: {shader_warning}")
        elif missing_params:
            self.report({'WARNING'}, f"Shader parameter(s) not found on {szi.DAMAGE_SHADER_FILENAME}: {', '.join(missing_params)}.")

        return {'FINISHED'}


_classes = (SETO_OT_create_fake_damage,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
