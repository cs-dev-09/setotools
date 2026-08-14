"""Scatter, rebuild, clear, rescan.

Scatter captures the floor region once (local space, onto the floor's ID
properties), seeds the floor's own settings group from the scene panel and
hands the rest to `object_settings.rebuild()` - the same function the live
settings drive afterwards. The scattered objects are the real prop meshes
wherever the prop library provides them (see library.py), each registered
as an MLO entity on the floor's archetype; a prop the library lacks lands
as its measured bounding box in wireframe, exporting identically.
"""

import bmesh
import bpy

from . import dirt, library, object_settings

# Faces steeper than this are walls, not floor, even when selected. cos(60°).
MIN_UP = 0.5


# Positions this close are the same point when deciding whether two faces
# share a side. 0.1 mm: finer than any modelling tolerance, coarser than
# float noise.
WELD_DECIMALS = 4


def _side_key(a, b):
    """A key for one side of a face, from its two corner **positions**.

    Deliberately not the bmesh edge: an MLO floor is routinely two slabs
    that meet exactly but are not welded, so each slab owns its own edge
    along the seam and both look unshared. Keying by position makes the
    two faces agree that the seam is interior - which they visibly did
    not before: the seam was treated as a wall, and both the litter and
    the grime piled along a line straight across the middle of the floor
    (seen in game).
    """
    ka = (round(a[0], WELD_DECIMALS), round(a[1], WELD_DECIMALS),
          round(a[2], WELD_DECIMALS))
    kb = (round(b[0], WELD_DECIMALS), round(b[1], WELD_DECIMALS),
          round(b[2], WELD_DECIMALS))
    return (ka, kb) if ka <= kb else (kb, ka)


def _floor_region(obj):
    """(triangles, boundaries) of the floor region, in **local** space.

    Edit Mode: the selected faces. Object Mode: every upward face. In both,
    faces that do not face up (in world space) are dropped - a selection
    grown over a wall should not put a beer bottle halfway up it.

    The boundary is the rim of the used region - the sides only one used
    face owns - which is what makes Edge Bias mean "near the walls" even
    when the selection is an island in the middle of a bigger floor. It
    is computed from the **faces**, by position: see `_side_key`.
    """
    normal_matrix = obj.matrix_world.inverted_safe().transposed().to_3x3()

    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
        faces = [f for f in bm.faces if f.select]
    else:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        faces = list(bm.faces)

    used = [f for f in faces
            if (normal_matrix @ f.normal).normalized().z >= MIN_UP]

    triangles = []
    sides = {}
    for face in used:
        verts = [tuple(v.co) for v in face.verts]
        for i in range(1, len(verts) - 1):
            triangles.append((verts[0], verts[i], verts[i + 1]))
        for i, corner in enumerate(verts):
            other = verts[(i + 1) % len(verts)]
            key = _side_key(corner, other)
            entry = sides.get(key)
            if entry is None:
                sides[key] = [1, corner + other]
            else:
                entry[0] += 1

    boundaries = [segment for count, segment in sides.values() if count == 1]

    if obj.mode != 'EDIT':
        bm.free()

    return triangles, boundaries


def _report_rebuild(operator, result):
    """One consistent message for Scatter and Re-Scatter."""
    if result is None or result.placed == 0:
        operator.report({'ERROR'}, "Nothing fit - the area is too small "
                                   "for this density and spacing.")
        return {'CANCELLED'}

    dressed = f"{result.dressed} with real models" if result.dressed \
        else "all as placeholder boxes - set the Prop Library in the " \
             "add-on preferences for real models"

    if result.archetype is not None:
        operator.report({'INFO'},
                        f"Scattered {result.placed} props ({dressed}) as "
                        f"entities on '{result.archetype.name}'.")
    else:
        operator.report({'WARNING'},
                        f"Scattered {result.placed} props ({dressed}), but "
                        f"they are not registered as entities: "
                        f"{result.problem or 'no MLO archetype was found'}. "
                        f"Fix that and scatter again.")
    return {'FINISHED'}


class SETO_OT_scatter_create(bpy.types.Operator):
    bl_idname = "seto.scatter_create"
    bl_label = "Scatter"
    bl_description = ("Scatter vanilla GTA props over the selected floor "
                      "faces as MLO entities. Runs again to replace its "
                      "previous layout on the same floor")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        floor = context.active_object

        triangles, boundaries = _floor_region(floor)
        if not triangles:
            self.report({'ERROR'},
                        "No upward-facing floor faces in the selection. "
                        "Select the floor's faces in Edit Mode first.")
            return {'CANCELLED'}

        object_settings.store_region(floor, triangles, boundaries)

        # Seed the floor's live settings from the scene panel: Scatter is
        # the moment the panel's values become this floor's values.
        settings = context.scene.seto_scatter
        data = floor.seto_scatter_data
        was_live = data.live_update
        data.live_update = False  # one rebuild below, not one per field
        data.preset = settings.preset
        data.density = settings.density
        data.seed = settings.seed
        data.edge_bias = settings.edge_bias
        data.scale_jitter = settings.scale_jitter
        data.prop_scale = settings.prop_scale
        data.topple = settings.topple
        data.clustering = settings.clustering
        data.dirt_enabled = settings.dirt_enabled
        data.dirt_amount = settings.dirt_amount
        data.dirt_scale = settings.dirt_scale
        data.live_update = was_live

        result = object_settings.rebuild(floor, context)
        return _report_rebuild(self, result)


class SETO_OT_scatter_rebuild(bpy.types.Operator):
    bl_idname = "seto.scatter_rebuild"
    bl_label = "Re-Scatter"
    bl_description = ("Rebuild this floor's layout from its own settings - "
                      "the manual path when Live Update is off")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return object_settings.has_region(context.active_object)

    def execute(self, context):
        result = object_settings.rebuild(context.active_object, context)
        return _report_rebuild(self, result)


class SETO_OT_scatter_clear(bpy.types.Operator):
    bl_idname = "seto.scatter_clear"
    bl_label = "Clear Scatter"
    bl_description = ("Remove the scattered props from the active floor - "
                      "or every scatter in the file when the active object "
                      "has none - along with their MLO entities")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        active = context.active_object

        # Counted apart, because they are not the same thing: reporting
        # "5 props" for four props and one dirt sheet is a number the user
        # can check and find wrong (seen in a user's log).
        props = 0
        sheets = 0
        if active is not None and any(
                obj.get(object_settings.SRC_PROP) == active.name
                or obj.get(dirt.MARKER) == active.name
                for obj in bpy.data.objects):
            props = object_settings.delete_run(scene, active.name)
            sheets = dirt.remove_overlay(active.name)
            if object_settings.TRIS_PROP in active:
                del active[object_settings.TRIS_PROP]
            if object_settings.BOUNDS_PROP in active:
                del active[object_settings.BOUNDS_PROP]
        else:
            sources = {obj.get(object_settings.SRC_PROP)
                       for obj in bpy.data.objects
                       if obj.get(object_settings.SRC_PROP)}
            sources |= {obj.get(dirt.MARKER) for obj in bpy.data.objects
                        if obj.get(dirt.MARKER)}
            for source in sources:
                props += object_settings.delete_run(scene, source)
                sheets += dirt.remove_overlay(source)
                owner = bpy.data.objects.get(source)
                if owner is not None:
                    if object_settings.TRIS_PROP in owner:
                        del owner[object_settings.TRIS_PROP]
                    if object_settings.BOUNDS_PROP in owner:
                        del owner[object_settings.BOUNDS_PROP]

        if not props and not sheets:
            self.report({'INFO'}, "No scattered props to remove.")
            return {'CANCELLED'}

        parts = []
        if props:
            parts.append(f"{props} scattered prop{'s' if props != 1 else ''}")
        if sheets:
            parts.append("the dirt sheet" if sheets == 1
                         else f"{sheets} dirt sheets")
        self.report({'INFO'}, f"Removed {' and '.join(parts)}.")
        return {'FINISHED'}


class SETO_OT_scatter_optimize_dirt(bpy.types.Operator):
    bl_idname = "seto.scatter_optimize_dirt"
    bl_label = "Optimize Dirt"
    bl_description = ("Crop the dirt overlay to its grime and drop the "
                      "vertices the pattern does not need - Surface "
                      "Painter's optimizer, on this sheet. A later "
                      "rebuild replaces the overlay unoptimized; press "
                      "again when the look is final")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and any(
            o.get(dirt.MARKER) == obj.name for o in bpy.data.objects)

    def execute(self, context):
        import math

        from ..surface_painter import shell as sp_shell
        floor = context.active_object
        overlay = next((o for o in bpy.data.objects
                        if o.get(dirt.MARKER) == floor.name), None)
        if overlay is None:
            self.report({'INFO'}, "No dirt overlay on this floor.")
            return {'CANCELLED'}
        # The tolerance is the user's, next to the button. It defaults
        # far looser than Surface Painter's own: a hand-painted stroke
        # has a shape the artist chose, while this sheet is noise, where
        # a few percent of blotch edge is invisible and every vertex it
        # buys is real cost in an interior full of them. The angle limit
        # is loose regardless - the sheet is flat, so there is no
        # silhouette to protect.
        tolerance = floor.seto_scatter_data.dirt_tolerance
        before, after = sp_shell.optimize_mesh(
            overlay, tolerance=tolerance, angle_limit=math.radians(5.0),
            max_passes=12)
        self.report({'INFO'},
                    f"Dirt overlay: {before} faces down to {after} "
                    f"at tolerance {tolerance:.3f}.")
        return {'FINISHED'}


class SETO_OT_scatter_rescan(bpy.types.Operator):
    bl_idname = "seto.scatter_rescan"
    bl_label = "Rescan Prop Library"
    bl_description = ("Re-index the prop library folder. Indexing a large "
                      "library takes minutes, so it never happens by "
                      "itself - press this after adding or changing "
                      "library .blends")

    def execute(self, context):
        library.forget()
        index = library.get_index(context, allow_scan=True)
        if not index:
            self.report({'WARNING'},
                        "No props found. Set a Prop Library folder of "
                        ".blend files in the add-on preferences.")
            return {'CANCELLED'}
        self.report({'INFO'},
                    f"Indexed {len(index)} catalogue props from the library.")
        return {'FINISHED'}


_classes = (SETO_OT_scatter_create, SETO_OT_scatter_rebuild,
            SETO_OT_scatter_clear, SETO_OT_scatter_optimize_dirt,
            SETO_OT_scatter_rescan)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
