import re

import bpy
import bmesh

from . import geometry
from . import object_settings
from . import properties
from . import textures
from ..shared import manual_offset
from ..shared import run_fade
from ..shared import sollumz_integration as szi
from ..shared import strip_settings
from ..shared import vertex_color

# What a generated strip is called. The tool is Edge Wear, so that is what its
# output says - "fake_dmg_003" in the outliner named a tool that no longer
# exists anywhere in the UI.
#
# The old name is still *recognised*: numbering continues past strips made
# before the rename instead of restarting at 001 and colliding with them.
NAME_PREFIX = "edge_wear"
_NAME_PATTERN = re.compile(r"^(?:edge_wear|fake_dmg)_(\d{3,})$")

# Span of the UV island's longer axis once fitted into the 0..1 square.
_UV_SIZE = object_settings.UV_SIZE

# Every generated strip is collected here, created on first use.
COLLECTION_NAME = NAME_PREFIX

# The name this tool used before the rename. A file that already has one keeps
# using it rather than growing a second collection alongside it.
LEGACY_COLLECTION_NAME = "fake_dmg"

# Blender's automatic ".001" suffix, so a collection it had to rename is still
# recognised as ours on the next run instead of spawning ".002", ".003", ...
_SUFFIX_PATTERN = re.compile(r"\.\d{3}$")


def _base_name(name):
    return _SUFFIX_PATTERN.sub("", name)


def _get_or_create_collection(context, name, parent=None):
    """Find or create the collection called `name` under `parent`.

    Reuses one we created earlier even if Blender had to suffix its name, and
    never adopts or moves an unrelated collection the user already has
    somewhere else in the scene.
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


def _next_fake_damage_name():
    """Explicit sequential naming (fake_dmg_001, _002, ...) instead of
    relying on Blender's automatic .001 suffixing."""
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


class SETO_OT_create_fake_damage(bpy.types.Operator):
    """Generate a separate Edge Wear decal strip along the selected edges"""
    bl_idname = "seto.create_fake_damage"
    bl_label = "Create Edge Wear"
    # No 'REGISTER': that is what puts an operator in the "Adjust Last
    # Operation" panel in the bottom-left corner, and this tool does not want
    # it. Everything it offered is on the finished strip itself, in Selected
    # Strip, where it rebuilds live and stays reachable after the next click -
    # the redo panel vanishes the moment you do anything else.
    bl_options = {'UNDO'}

    # Same definitions as the Scene settings - see properties.settings_annotations().
    __annotations__ = properties.settings_annotations()

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None
            and obj.type == 'MESH'
            and context.mode == 'EDIT_MESH'
            and szi.is_sollumz_available()
        )

    def _seed_from_panel(self, context):
        """Fill in any property the caller did not set from the N-panel settings.

        Deliberately done here rather than in invoke(): Blender skips invoke()
        entirely in background mode, and relying on it would mean the operator
        behaves differently when driven from a script than from the button.

        is_property_set() is what distinguishes the two cases:
          * fresh run (button press, or bpy.ops with no arguments) - nothing is
            set, so every value comes from the panel;
          * F9 redo after dragging a slider - that property IS set, so the
            user's live value wins, while the rest fall back to the panel,
            which execute() keeps in sync with whatever last ran.
        """
        panel = context.scene.seto_fake_damage
        for name in properties.SETTING_NAMES:
            if not self.properties.is_property_set(name):
                # Which panel a setting comes from - this tool's, or the
                # Geometry section that owns the strip's shape - is decided in
                # one place, so this cannot drift from what the UI draws.
                setattr(self, name,
                        strip_settings.panel_value(context, name, panel))

    def execute(self, context):
        if not szi.is_sollumz_available():
            self.report({'ERROR'}, "Sollumz is not enabled/available. Seto Edge Wear requires Sollumz.")
            return {'CANCELLED'}

        self._seed_from_panel(context)

        # Read from the operator's own properties, never from the Scene
        # settings: on a redo those are what the F9 panel is editing.
        settings = self
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
            alpha_bottom=settings.alpha_bottom,
            alpha_top=settings.alpha_top,
            up_axis=run_fade.local_up_axis(source_obj.matrix_world),
        )
        if not strip_data.faces:
            self.report({'WARNING'}, "Could not generate damage geometry from the selected edges (degenerate geometry?).")
            return {'CANCELLED'}

        # Done reading the source BMesh - leave Edit Mode so we can safely
        # create/select/parent a new object. The source mesh is never modified.
        bpy.ops.object.mode_set(mode='OBJECT')

        new_name = _next_fake_damage_name()
        new_mesh = geometry.create_mesh_from_strip_data(new_name, strip_data)
        vertex_color.apply_preset(settings, settings.color_preset)
        loop_uv, loop_rgba = geometry.compute_loop_uv_and_alpha(
            new_mesh, strip_data, color_rgb=tuple(settings.color_rgb)
        )

        # UVMap 0 / Color 1: decal_normal_only's vertex layout requires both
        # TexCoord0 and Colour0, so this must succeed or the tool has failed.
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

        # The UVs geometry.py authored are already a straight rectangle in
        # metres; this only fits them into the 0..1 square, aspect intact.
        geometry.normalise_uvs(new_mesh, _UV_SIZE,
                               uv_scale=settings.uv_scale,
                               uv_offset=tuple(settings.uv_offset))

        # Re-applied after the merge: bmesh.ops can leave faces it rebuilt
        # flat, and a hard band at a quad boundary is exactly what a decal
        # strip exists to hide.
        geometry.shade_smooth(new_mesh)

        new_obj = bpy.data.objects.new(new_name, new_mesh)

        # Built entirely in source_obj's local space, so copying its world
        # matrix places the strip exactly on the source geometry regardless of
        # the source object's translation/rotation/non-uniform scale.
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
        # unambiguously targets it, not the source object.
        _select_only(context, new_obj)

        # Only parent into a Sollumz Drawable hierarchy if the source object
        # already belongs to one; otherwise the strip stays an independent
        # object, still placed correctly via the matrix_world copy above.
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
        texture_warning = None
        try:
            material, missing_params, texture_warning = szi.find_or_create_damage_material(
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
            self.report({'WARNING'}, f"Edge Wear mesh created, but setting Origin to Geometry failed: {e}")

        # Stamp the strip with everything needed to regenerate itself later,
        # so its settings stay live in the panel (see object_settings.py).
        # Suppressed: each assignment below fires the live-rebuild callback,
        # which would regenerate the mesh and discard the unwrap just applied.
        with object_settings.suppress_rebuild():
            obj_data = new_obj.seto_fake_damage_data
            obj_data.is_fake_damage = True
            obj_data.source_object = source_obj
            obj_data.edge_keys = object_settings.serialise_edge_keys(edges)
            properties.copy_settings(self, obj_data)
            obj_data.status = ""
            # Where the tool put it. A rebuild records this too, but the strip
            # can be dragged and pinned before one ever runs, and then there
            # would be nothing to measure the drag against.
            manual_offset.reset(new_obj, obj_data)

        # Push the values that actually produced this result back onto the
        # N-panel, so a value dialled in through the F9 panel becomes the
        # starting point for the next strip instead of silently reverting.
        strip_settings.write_back(self, context, context.scene.seto_fake_damage,
                                  properties.SETTING_NAMES)

        msg = (f"Created '{new_name}': {len(chains)} chain(s), "
               f"{len(strip_data.faces)} quad(s).")
        if skipped:
            msg += f" Skipped {skipped} unusable edge(s)."
        self.report({'INFO'}, msg)

        if shader_warning:
            self.report({'WARNING'}, f"Edge Wear mesh created, but {szi.DAMAGE_SHADER_FILENAME} assignment failed: {shader_warning}")
        elif missing_params:
            self.report({'WARNING'}, f"Shader parameter(s) not found on {szi.DAMAGE_SHADER_FILENAME}: {', '.join(missing_params)}.")

        if texture_warning:
            self.report({'WARNING'}, texture_warning)

        return {'FINISHED'}


_classes = (SETO_OT_create_fake_damage,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
