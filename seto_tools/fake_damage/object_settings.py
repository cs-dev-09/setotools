"""Per-object settings that rebuild the strip live when you change them.

A generated Fake_Damage object keeps everything needed to regenerate itself:
which object it was built from, which edges were selected, and the settings
that were used. Dragging any of those settings fires an update callback that
regenerates the mesh in place - the same feel as tweaking the width on a
Geometry Nodes modifier, without the geometry actually being procedural.

The rebuild deliberately uses **no bpy.ops at all**. Blender warns against
calling operators from property update callbacks (they run mid-UI-interaction
and can corrupt the undo stack or crash), so everything here goes through
bmesh and the data API:

  * mesh generation       - geometry.py, already ops-free
  * merge/cleanup         - bmesh.ops, safe
  * origin to geometry    - done by hand (shift the verts, compensate in the
                            object matrix) instead of bpy.ops.object.origin_set
  * UVs                   - laid out straight from the chain, then normalised

That last one is why there is no unwrap step to re-run: the UVs are built from
the geometry rather than solved, so a live rebuild produces final UVs, not a
placeholder to be fixed up afterwards.
"""

import contextlib

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import geometry
from ..shared import run_fade
from . import properties
from ..shared import sollumz_integration as szi

# Span of the UV island's longer axis once fitted into the 0..1 square. Kept
# here rather than imported from operators.py, which imports this module.
UV_SIZE = 1.5

# Guards against a rebuild triggering another rebuild through the same
# property callbacks.
_rebuilding = False


@contextlib.contextmanager
def suppress_rebuild():
    """Write to a strip's settings without triggering the live rebuild.

    Needed when the create operator stamps its settings onto a freshly built
    strip: each assignment fires the update callback, and an unsuppressed
    rebuild there would immediately regenerate the mesh - throwing away the
    rebuild there would regenerate the mesh before the operator has finished
    setting it up.
    """
    global _rebuilding
    previous = _rebuilding
    _rebuilding = True
    try:
        yield
    finally:
        _rebuilding = previous


def serialise_edge_keys(edges):
    """Store the selected edges as "va,vb va,vb ..." source-mesh vertex indices.

    Indices rather than positions, so the strip still rebuilds correctly after
    the source mesh is moved, rotated or scaled. Editing the source topology
    invalidates them, which is what `rebuild` reports on.
    """
    return " ".join(f"{e.va},{e.vb}" for e in edges)


def parse_edge_keys(text):
    keys = []
    for token in text.split():
        va, _, vb = token.partition(",")
        try:
            keys.append((int(va), int(vb)))
        except ValueError:
            continue
    return keys


def edges_from_keys(mesh, keys):
    """Rebuild DamageEdge entries for `keys` by reading the source mesh again.

    Returns (edges, coords, missing) - `missing` counts keys whose edge is no
    longer in the mesh (the source was edited since the strip was created).
    """
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.faces.index_update()
    bm.normal_update()

    by_key = {}
    for edge in bm.edges:
        a, b = edge.verts[0].index, edge.verts[1].index
        by_key[(a, b)] = edge
        by_key[(b, a)] = edge

    edges = []
    coords = {}
    missing = 0
    for key in keys:
        edge = by_key.get(key)
        if edge is None:
            missing += 1
            continue
        faces = sorted(edge.link_faces, key=lambda f: f.index)[:2]
        if not faces:
            missing += 1
            continue
        v0, v1 = edge.verts
        if (v1.co - v0.co).length < 1e-8:
            missing += 1
            continue
        coords[v0.index] = v0.co.copy()
        coords[v1.index] = v1.co.copy()
        edges.append(geometry.DamageEdge(
            va=v0.index,
            vb=v1.index,
            normals=[f.normal.copy() for f in faces],
            face_centers=[f.calc_center_median() for f in faces],
        ))

    bm.free()
    return edges, coords, missing


def _centre_origin(obj, mesh):
    """Origin to Geometry (median), done through the data API.

    bpy.ops.object.origin_set is off limits here - see the module docstring -
    so the median is subtracted from every vertex and folded back into the
    object's world matrix, which is exactly what the operator does.
    """
    if not mesh.vertices:
        return Vector((0.0, 0.0, 0.0))

    median = Vector((0.0, 0.0, 0.0))
    for v in mesh.vertices:
        median += v.co
    median /= len(mesh.vertices)

    for v in mesh.vertices:
        v.co -= median

    obj.matrix_world = obj.matrix_world @ Matrix.Translation(median)
    return median


def rebuild(obj):
    """Regenerate `obj`'s mesh from its stored source, edges and settings.

    Returns a short status string for the panel, or None when everything is
    fine. Never raises: this runs from a UI callback, where an exception would
    surface as a traceback in the console on every mouse move.
    """
    global _rebuilding
    if _rebuilding:
        return None

    data = obj.seto_fake_damage_data
    source = data.source_object
    if source is None:
        return "Source object is gone - settings can no longer rebuild this strip."
    if source.type != 'MESH':
        return "Source object is not a mesh."
    if source.mode == 'EDIT':
        return "Source is in Edit Mode - leave it to rebuild."

    keys = parse_edge_keys(data.edge_keys)
    if not keys:
        return "No stored edge selection."

    _rebuilding = True
    try:
        edges, coords, missing = edges_from_keys(source.data, keys)
        if not edges:
            return "Stored edges are gone from the source mesh (was it edited?)."

        chains = geometry.build_edge_chains(edges)
        strip_data = geometry.build_damage_mesh_data(
            edges, chains, coords,
            width=data.width,
            surface_offset=data.surface_offset,
            alpha_center=data.alpha_center,
            alpha_outer=data.alpha_outer,
            invert_fade=data.invert_fade,
            flip_direction=data.flip_direction,
            alpha_bottom=data.alpha_bottom,
            alpha_top=data.alpha_top,
            up_axis=run_fade.local_up_axis(source.matrix_world),
        )
        if not strip_data.faces:
            return "Current settings produce no geometry."

        old_mesh = obj.data
        materials = list(old_mesh.materials)

        new_mesh = geometry.create_mesh_from_strip_data(old_mesh.name, strip_data)
        loop_uv, loop_rgba = geometry.compute_loop_uv_and_alpha(
            new_mesh, strip_data, color_rgb=tuple(data.color_rgb)
        )
        try:
            szi.write_uv_and_color(new_mesh, loop_uv, loop_rgba)
        except Exception:
            # Sollumz went away; the geometry is still worth keeping, and the
            # attributes come back the next time it is available.
            pass
        geometry.merge_by_distance(new_mesh, data.merge_distance)
        geometry.normalise_uvs(new_mesh, UV_SIZE,
                               uv_scale=data.uv_scale,
                               uv_offset=tuple(data.uv_offset))
        geometry.shade_smooth(new_mesh)

        for mat in materials:
            new_mesh.materials.append(mat)

        # Place the object back on the source before re-centring, so repeated
        # rebuilds cannot accumulate origin drift.
        obj.matrix_world = source.matrix_world.copy()
        obj.data = new_mesh
        _centre_origin(obj, new_mesh)

        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

        if missing:
            return f"{missing} stored edge(s) no longer exist in the source mesh."
        return None
    finally:
        _rebuilding = False


def _on_setting_changed(self, context):
    """Property update callback - `self` is the per-object PropertyGroup."""
    obj = getattr(self, "id_data", None)
    if obj is None or not isinstance(obj, bpy.types.Object):
        return
    if _rebuilding or not self.is_fake_damage or not self.live_update:
        return
    self.status = rebuild(obj) or ""


def _object_annotations():
    """Bookkeeping properties, plus the tool's settings wired to rebuild the
    object as soon as they change."""
    annotations = {
        "is_fake_damage": bpy.props.BoolProperty(
            name="Is Edge Wear",
            description="Marks an object as generated by this tool, so the panel knows to show its settings",
            default=False,
        ),
        "source_object": bpy.props.PointerProperty(
            name="Source",
            description="The mesh this strip was generated from. Rebuilding reads its edges again",
            type=bpy.types.Object,
        ),
        "edge_keys": bpy.props.StringProperty(
            name="Edge Keys",
            description="Source-mesh vertex index pairs of the edges this strip was built along",
            default="",
        ),
        "live_update": bpy.props.BoolProperty(
            name="Live Update",
            description=(
                "Rebuild the strip immediately whenever a setting below changes. Turn off on very "
                "heavy selections and use Rebuild Now instead"
            ),
            default=True,
        ),
        "status": bpy.props.StringProperty(
            name="Status",
            description="Why the last rebuild could not run, if it could not",
            default="",
        ),
    }
    annotations.update(properties.settings_annotations(update=_on_setting_changed))
    return annotations


class SETO_PG_fake_damage_object(bpy.types.PropertyGroup):
    __annotations__ = _object_annotations()


class SETO_OT_fake_damage_rebuild(bpy.types.Operator):
    """Regenerate this Edge Wear strip from its stored source edges and settings"""
    bl_idname = "seto.fake_damage_rebuild"
    bl_label = "Rebuild Now"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.seto_fake_damage_data.is_fake_damage

    def execute(self, context):
        obj = context.active_object
        message = rebuild(obj)
        obj.seto_fake_damage_data.status = message or ""
        if message:
            self.report({'WARNING'}, message)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Rebuilt '{obj.name}' ({len(obj.data.polygons)} quad(s)).")
        return {'FINISHED'}


_classes = (
    SETO_PG_fake_damage_object,
    SETO_OT_fake_damage_rebuild,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.seto_fake_damage_data = bpy.props.PointerProperty(type=SETO_PG_fake_damage_object)


def unregister():
    del bpy.types.Object.seto_fake_damage_data
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
