import re

import bpy
import bmesh
from mathutils import Vector

from . import geometry
from . import object_settings
from . import properties
from . import source_bevel
from . import textures
from ..shared import manual_offset
from ..shared import sollumz_integration as szi

# What a generated strip is called. The tool is Ambient Occlusion, so that is
# what its output says - "fake_ao_003" in the outliner named a tool that no
# longer exists anywhere in the UI.
#
# The old name is still *recognised*, which is the point of the alternation:
# numbering continues past strips made before the rename instead of restarting
# at 001 and colliding with them, and a .blend full of fake_ao_* keeps working.
NAME_PREFIX = "ambient_occlusion"
_NAME_PATTERN = re.compile(r"^(?:ambient_occlusion|fake_ao)_(\d{3,})$")
# Span of the UV island's longer axis once fitted into the 0..1 square.
_UV_SIZE = object_settings.UV_SIZE

# Every generated strip is collected here, created on first use.
COLLECTION_NAME = NAME_PREFIX

# The name this tool used before the rename. A file that already has one keeps
# using it rather than growing a second collection alongside it.
LEGACY_COLLECTION_NAME = "fake_ao"

# Blender's automatic ".001" suffix, so a collection it had to rename is still
# recognised as ours on the next run instead of spawning ".002", ".003", ...
_SUFFIX_PATTERN = re.compile(r"\.\d{3}$")


def _base_name(name):
    return _SUFFIX_PATTERN.sub("", name)


def _get_or_create_collection(context, name, parent=None):
    """Find or create the collection called `name` under `parent`.

    Reuses one we created earlier even if Blender had to suffix its name, and
    never adopts or moves an unrelated collection the user already has
    somewhere else in the scene. A file made before the rename keeps its
    old-named collection rather than being given a second one beside it.
    """
    parent = parent or context.scene.collection
    accepted = (name, LEGACY_COLLECTION_NAME) if name == COLLECTION_NAME else (name,)

    for child in parent.children:
        if _base_name(child.name) in accepted:
            return child

    existing = bpy.data.collections.get(name)
    if existing is not None and existing is not parent and \
            existing not in context.scene.collection.children_recursive:
        # Exists but is not in this scene (appended, or orphaned) - adopt it.
        parent.children.link(existing)
        return existing

    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def _drawable_collections(drawable_root):
    """The collections the Drawable itself lives in, or None.

    When the source belongs to a Sollumz Drawable, what this tool generates is
    part of that asset, so it belongs beside the rest of it rather than in a
    tool-named collection off to the side. Parenting alone is not enough: an
    object parented to the Drawable but linked somewhere else shows up greyed
    out under it in the outliner, and gets left behind by anything that works
    on the Drawable's collection.
    """
    if drawable_root is None:
        return None
    return list(drawable_root.users_collection) or None


def _next_fake_ao_name():
    """Explicit sequential naming (fake_ao_001, _002, ...) instead of relying
    on Blender's automatic .001 suffixing."""
    max_n = 0
    for name in bpy.data.objects.keys():
        match = _NAME_PATTERN.match(name)
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"{NAME_PREFIX}_{max_n + 1:03d}"


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


def _set_origin_to_geometry(obj):
    """Equivalent of Object > Set Origin > Origin to Geometry. Assumes `obj`
    is already the only selected/active object (see _select_only)."""
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')


class SETO_OT_create_fake_ao(bpy.types.Operator):
    """Generate a separate Ambient Occlusion decal strip along the selected edges"""
    bl_idname = "seto.create_fake_ao"
    bl_label = "Create Ambient Occlusion"
    # No 'REGISTER': that is what puts an operator in the "Adjust Last
    # Operation" panel in the bottom-left corner, and this tool does not want
    # it. Everything it offered is on the finished strip itself, in Selected
    # Strip, where it rebuilds live and stays reachable after the next click -
    # the redo panel vanishes the moment you do anything else.
    bl_options = {'UNDO'}

    # Same definitions as the Scene settings - see properties.settings_annotations().
    __annotations__ = properties.settings_annotations()

    def _seed_from_panel(self, context):
        """Fill in any property the caller did not set from the N-panel settings.

        Deliberately done in execute() rather than invoke(): Blender skips
        invoke() entirely in background mode, so relying on it would make the
        operator behave differently from a script than from the button.
        """
        panel = context.scene.seto_fake_ao
        for name in properties.SETTING_NAMES:
            if not self.properties.is_property_set(name):
                value = getattr(panel, name)
                if hasattr(value, "__len__") and not isinstance(value, str):
                    value = tuple(value)
                setattr(self, name, value)

    @classmethod
    def poll(cls, context):
        # Object Mode is allowed as well now: building from Ground Level reads
        # the whole mesh and needs no selection, so requiring Edit Mode would
        # be requiring a mode with nothing to do in it.
        obj = context.active_object
        return (
            obj is not None
            and obj.type == 'MESH'
            and context.mode in {'EDIT_MESH', 'OBJECT'}
            and szi.is_sollumz_available()
        )

    def execute(self, context):
        if not szi.is_sollumz_available():
            self.report({'ERROR'}, "Sollumz is not enabled/available. Seto Ambient Occlusion requires Sollumz.")
            return {'CANCELLED'}

        self._seed_from_panel(context)

        # Read from the operator's own properties, never from the Scene
        # settings: on a redo those are what the F9 panel is editing.
        settings = self
        source_obj = context.active_object
        source_mesh = source_obj.data

        ground = settings.source_mode == 'GROUND'
        if not ground and context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Enter Edit Mode and select edges, or set "
                                   "Build From to Ground Level.")
            return {'CANCELLED'}

        # Read the current edge selection while still in Edit Mode. All values
        # are copied out as plain Vectors (local space), so they stay valid
        # after we leave edit mode below.
        temporary_bm = None
        if context.mode == 'EDIT_MESH':
            bm = bmesh.from_edit_mesh(source_mesh)
        else:
            # Ground Level from Object Mode: a BMesh of our own, freed below.
            bm = temporary_bm = bmesh.new()
            bm.from_mesh(source_mesh)

        # The source mesh is never written to here. Rounding its corner is a
        # Bevel modifier now, set up after the strip exists and kept in step
        # with it from then on - see source_bevel.py. So the strip is always
        # built from the sharp corner, and the edge indices pointing at that
        # corner stay valid for as long as the mesh does.
        segments = skipped = None

        if ground:
            # World Z, taken into the source's local space. The plane's normal
            # goes through the inverse-transpose, not the plain matrix: under
            # non-uniform scale the two disagree, and that is exactly the case
            # this would silently get wrong.
            inverse = source_obj.matrix_world.inverted()
            plane_co = inverse @ Vector((0.0, 0.0, settings.ground_level))
            plane_no = (inverse.transposed().to_3x3()
                        @ Vector((0.0, 0.0, 1.0))).normalized()
            segments = geometry.gather_ground_edge_segments(bm, plane_co, plane_no)
            if not segments:
                # Nothing crossed. Almost always because the object is STANDING
                # on that height rather than sunk through it - coplanar, so
                # strictly speaking no intersection at all. Lift the plane by
                # the contact tolerance and take the footprint instead.
                step = plane_no.normalized() * geometry.CONTACT_TOLERANCE
                segments = geometry.gather_ground_edge_segments(
                    bm, plane_co + step, plane_no)
                # ...and put the contour back down where it was asked for.
                # Without this the strip starts 2 mm up the wall and reads as
                # floating, with a hairline of bare floor under it - which is
                # exactly the thing the strip exists to hide.
                for segment in segments:
                    segment.v0 -= step
                    segment.v1 -= step
            skipped = 0
            edge_keys = ""
            # There are no source edges to point at, so the contour is frozen
            # onto the strip - the same mechanism a 'Source + Strip' bevel uses
            # for a corner it has rounded away.
            frozen_segments = object_settings.serialise_segments(segments)
        else:
            segments, skipped = geometry.gather_selected_edge_segments(bm)
            edge_keys = object_settings.serialise_edge_keys(bm)
            frozen_segments = ""

        if temporary_bm is not None:
            temporary_bm.free()

        if not segments:
            if ground:
                # Say which of the three it is. "Nothing crosses" is true
                # of an object parked under the floor, one floating above it,
                # and a flat plane lying parallel to it - and the fix is
                # different every time.
                heights = [(source_obj.matrix_world @ vert.co).z
                           for vert in source_mesh.vertices] or [0.0]
                low, high = min(heights), max(heights)
                level = settings.ground_level
                if high < level:
                    detail = (f"it is entirely below it (top at "
                              f"{high:.4g} m). Raise the object, or lower "
                              "Ground Level.")
                elif low > level:
                    detail = (f"it is entirely above it (bottom at "
                              f"{low:.4g} m). Lower the object, or raise "
                              "Ground Level.")
                else:
                    detail = ("it is flat at that height - a horizontal plane "
                              "is parallel to the floor and never crosses it. "
                              "Pick the object that stands ON the floor "
                              "instead.")
                self.report({'WARNING'},
                            f"Nothing crosses Z = {level:.4g} m: {detail}")
            else:
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
            alpha_bottom=settings.alpha_bottom,
            alpha_top=settings.alpha_top,
            up_axis=geometry.local_up_axis(source_obj.matrix_world),
        )
        if not strip_data.faces:
            self.report({'WARNING'}, "Could not generate strip geometry from the selected edges (degenerate geometry?).")
            return {'CANCELLED'}

        # Leave Edit Mode now that we're done reading the source BMesh, so we
        # can safely create/select/parent a new object. Ground Level may have
        # been run from Object Mode, where there is nothing to leave.
        if context.mode == 'EDIT_MESH':
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
        geometry.merge_by_distance(
            new_mesh, geometry.auto_merge_distance(settings.width, settings.surface_offset))

        # Round off the strip's own seam, now that the two wings are welded
        # into one mesh and there is a real edge there to bevel.
        object_settings.apply_strip_bevel(new_mesh, segments, settings)

        # The UVs geometry.py authored are already a straight rectangle in
        # metres; this only fits them into the 0..1 square, aspect intact.
        geometry.normalise_uvs(new_mesh, _UV_SIZE)

        # Re-applied after the merge: bmesh.ops can leave faces it rebuilt
        # flat, and a hard band at a quad boundary is exactly what a decal
        # strip exists to hide.
        geometry.shade_smooth(new_mesh)

        new_obj = bpy.data.objects.new(new_name, new_mesh)

        # The strip was built entirely in source_obj's local space, so copying
        # its world matrix places it exactly on the source geometry regardless
        # of the source object's translation/rotation/non-uniform scale.
        new_obj.matrix_world = source_obj.matrix_world.copy()

        # Generated strips are gathered in their own collection rather than
        # dropped next to the source, so they stay easy to hide, select and
        # export as a group.
        drawable_root = szi.find_drawable_parent(source_obj)
        target_collections = _drawable_collections(drawable_root) or [
            _get_or_create_collection(context, COLLECTION_NAME)
        ]
        for collection in target_collections:
            collection.objects.link(new_obj)

        # Select only the new object so every subsequent bpy.ops call below
        # (parenting aside) unambiguously targets it, not the source object
        # or anything else that happened to be selected.
        _select_only(context, new_obj)

        # Only parent into a Sollumz Drawable hierarchy if the source object
        # already belongs to one. Otherwise the strip is left fully
        # unparented as an independent object (still placed correctly via
        # the matrix_world copy above).
        if drawable_root is not None:
            _parent_keep_transform(new_obj, drawable_root)
            try:
                szi.convert_to_drawable_model(new_obj)
            except Exception as e:
                self.report({'WARNING'}, f"'{new_name}' was created, but could not be registered as a Drawable Model: {e}")

        # Shader assignment is best-effort: geometry generation is the primary
        # function of this tool, so a shader failure must not remove the mesh.
        shader_warning = None
        texture_warning = None
        try:
            material, texture_warning = szi.find_or_create_fake_ao_material(
                texture_path=textures.bundled_texture_path(),
                reuse=(settings.material_mode == 'AUTO'),
            )
            szi.assign_material_to_object(new_obj, material)
        except szi.SollumzShaderError as e:
            shader_warning = str(e)
        except Exception as e:
            shader_warning = f"unexpected error: {e}"

        # Automatic Origin to Geometry - equivalent to Object > Set Origin > Origin to Geometry.
        _select_only(context, new_obj)
        try:
            _set_origin_to_geometry(new_obj)
        except Exception as e:
            self.report({'WARNING'}, f"Ambient Occlusion mesh created, but setting Origin to Geometry failed: {e}")

        # Stamp the strip with everything needed to regenerate itself later,
        # so its settings stay live in the panel (see object_settings.py).
        # Suppressed: each assignment fires the live-rebuild callback, which
        # would regenerate the mesh before this operator has finished with it.
        with object_settings.suppress_rebuild():
            obj_data = new_obj.seto_fake_ao_data
            obj_data.is_fake_ao = True
            obj_data.source_object = source_obj
            obj_data.edge_keys = edge_keys
            obj_data.frozen_segments = frozen_segments
            properties.copy_settings(self, obj_data)
            # Ground Level builds along a contour that is not in the mesh, so
            # there is no edge there to round off.
            # Ground Level has no source edge to round, on either mesh.
            obj_data.bevel_mesh = settings.bevel_mesh and not ground
            obj_data.bevel_strip = settings.bevel_strip and not ground
            obj_data.status = ""
            # Where the tool put it. A rebuild records this too, but the strip
            # can be dragged and pinned before one ever runs, and then there
            # would be nothing to measure the drag against.
            manual_offset.reset(new_obj, obj_data)

        # Round the source's corner to match, with a modifier rather than by
        # cutting it in - so it stays live, and the strip's own Bevel controls
        # both from here on.
        bevel_note = source_bevel.sync(source_obj, leader=new_obj)

        # Push the values that actually produced this result back onto the
        # N-panel, so a value dialled in through the F9 panel becomes the
        # starting point for the next strip instead of silently reverting.
        properties.copy_settings(self, context.scene.seto_fake_ao)

        msg = f"Created '{new_name}' with {len(strip_data.faces)} strip quad(s)."
        if bevel_note:
            msg += f" Source corner rounded by a '{source_bevel.MODIFIER_NAME}' modifier ({bevel_note})."
        if skipped:
            msg += f" Skipped {skipped} edge(s) with no adjacent face."
        self.report({'INFO'}, msg)

        if shader_warning:
            self.report({'WARNING'}, f"Ambient Occlusion mesh created, but {szi.DECAL_SHADER_FILENAME} assignment failed: {shader_warning}")

        if texture_warning:
            self.report({'WARNING'}, texture_warning)

        return {'FINISHED'}


_classes = (SETO_OT_create_fake_ao,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
