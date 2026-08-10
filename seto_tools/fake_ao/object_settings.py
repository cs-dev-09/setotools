"""Per-object settings that rebuild the strip live when you change them.

A generated fake_ao object keeps everything needed to regenerate itself:
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
  * UVs                   - laid out straight from each wing, then normalised

That last one is why there is no unwrap step to re-run: the UVs are built from
the geometry rather than projected, so a live rebuild produces final UVs, not
a placeholder to be fixed up afterwards.
"""

import contextlib
import json

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import geometry
from . import properties
from . import source_bevel
from ..shared import sollumz_integration as szi

# Span of the UV island's longer axis once fitted into the 0..1 square. Kept
# here rather than imported from operators.py, which imports this module.
UV_SIZE = 1.5

# Guards against a rebuild triggering another rebuild through the same
# property callbacks.
_rebuilding = False


def is_rebuilding():
    """Whether a rebuild is already running.

    Exposed for Edge Dirt, which drives the same machinery through its own
    per-object group and needs the same guard - see rebuild().
    """
    return _rebuilding


@contextlib.contextmanager
def suppress_rebuild():
    """Write to a strip's settings without triggering the live rebuild.

    Needed when the create operator stamps its settings onto a freshly built
    strip: each assignment fires the update callback, and an unsuppressed
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


def serialise_segments(segments):
    """Freeze EdgeSegments onto the strip, as JSON in the source's local space.

    The fallback for the one case stored vertex indices cannot survive: a
    'Source + Strip' bevel builds the strip from the SHARP corner and then
    rounds it to match, so by the time the strip exists the edge it was built
    from has been beveled away and its indices mean nothing.

    Local space, so this still follows the source object being moved, rotated
    or scaled - the strip copies its world matrix either way. What it cannot
    follow is the source's vertices being edited afterwards, which is the same
    limit the index path has.
    """
    return json.dumps([{
        "v0": list(seg.v0), "v1": list(seg.v1),
        "n": [list(n) for n in seg.normals],
        "c": [list(c) for c in seg.face_centers],
    } for seg in segments], separators=(",", ":"))


def parse_segments(text):
    """Read serialise_segments() back. Returns [] on anything unreadable, so a
    hand-edited or truncated value degrades into "cannot rebuild" rather than a
    traceback on every mouse move."""
    try:
        entries = json.loads(text)
    except (ValueError, TypeError):
        return []
    segments = []
    for entry in entries:
        try:
            segments.append(geometry.EdgeSegment(
                v0=Vector(entry["v0"]),
                v1=Vector(entry["v1"]),
                normals=[Vector(n) for n in entry["n"]],
                face_centers=[Vector(c) for c in entry["c"]],
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return segments


def _face_key(face):
    """A face as its sorted vertex indices - stable for as long as the stored
    edge indices are, which is the same contract the whole rebuild runs on."""
    return "/".join(str(i) for i in sorted(v.index for v in face.verts))


def serialise_edge_keys(bm, exclude_faces=None):
    """Store the selected edges as "va,vb va,vb ..." source-mesh vertex indices.

    Indices rather than positions, so the strip still rebuilds correctly after
    the source mesh is moved, rotated or scaled. Editing the source topology
    invalidates them, which is what `rebuild` reports on.

    When faces were excluded (the source bevel's chamfer - see
    geometry.bevel_source_edges), the surviving faces are recorded alongside
    the edge as "va,vb:i/j/k;i/j/k". Without that, a rebuild would read the
    source again, find the chamfer face perfectly usable, and quietly grow a
    wing onto it that the original strip never had.
    """
    bm.verts.index_update()
    keys = []
    for edge in bm.edges:
        if not edge.select or not edge.link_faces:
            continue
        faces = geometry.faces_for_edge(edge, exclude_faces)
        if not faces:
            continue
        token = f"{edge.verts[0].index},{edge.verts[1].index}"
        if len(faces) != len(edge.link_faces):
            token += ":" + ";".join(_face_key(f) for f in faces)
        keys.append(token)
    return " ".join(keys)


def parse_edge_keys(text):
    """Returns [(va, vb, face_keys)], face_keys being None when every adjacent
    face is allowed - which is what strips created before the bevel option
    existed store."""
    keys = []
    for token in text.split():
        edge_part, _, face_part = token.partition(":")
        va, _, vb = edge_part.partition(",")
        try:
            va, vb = int(va), int(vb)
        except ValueError:
            continue
        face_keys = None
        if face_part:
            face_keys = set()
            for spec in face_part.split(";"):
                try:
                    face_keys.add(frozenset(int(i) for i in spec.split("/")))
                except ValueError:
                    continue
        keys.append((va, vb, face_keys))
    return keys


def segments_from_keys(mesh, keys):
    """Rebuild EdgeSegment entries for `keys` by reading the source mesh again.

    Mirrors geometry.gather_selected_edge_segments, but keyed on stored vertex
    indices instead of the live selection.

    Returns (segments, missing) - `missing` counts keys whose edge is no longer
    in the mesh (the source was edited since the strip was created).
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

    segments = []
    missing = 0
    for va, vb, face_keys in keys:
        edge = by_key.get((va, vb))
        if edge is None:
            missing += 1
            continue
        if face_keys is None:
            faces = geometry.faces_for_edge(edge)
        else:
            # Same filtering the strip was created with, expressed as the faces
            # that survived rather than the ones that were excluded.
            excluded = {f for f in edge.link_faces
                        if frozenset(v.index for v in f.verts) not in face_keys}
            faces = geometry.faces_for_edge(edge, excluded)
        if not faces:
            missing += 1
            continue
        segments.append(geometry.EdgeSegment(
            v0=edge.verts[0].co.copy(),
            v1=edge.verts[1].co.copy(),
            normals=[f.normal.copy() for f in faces],
            face_centers=[f.calc_center_median() for f in faces],
        ))

    bm.free()
    return segments, missing


def apply_strip_bevel(mesh, segments, settings):
    """Round off the strip's seam, if the settings ask for it.

    Shared by the create operator and the live rebuild so both produce the
    same mesh; `settings` is whichever of the three carriers of the tool's
    settings is in play (see properties.settings_annotations).

    The tolerance for finding the seam has to cover how far the welded corner
    ends up from the original edge: each wing is lifted off its wall by
    Surface Offset before welding, and the weld itself moves vertices up to
    the merge distance.
    """
    if not settings.bevel_strip:
        return 0
    corner_points = [(seg.v0, seg.v1) for seg in segments]
    merge = geometry.auto_merge_distance(settings.width, settings.surface_offset)
    tolerance = max(merge, settings.surface_offset) * 2.0 + 1e-6
    return geometry.bevel_strip_corners(
        mesh, corner_points,
        width=settings.bevel_width,
        segments=settings.bevel_segments,
        profile=settings.bevel_profile,
        tolerance=tolerance,
    )


def _centre_origin(obj, mesh):
    """Origin to Geometry (median), done through the data API.

    bpy.ops.object.origin_set is off limits here - see the module docstring -
    so the median is subtracted from every vertex and folded back into the
    object's world matrix, which is exactly what the operator does.
    """
    if not mesh.vertices:
        return

    median = Vector((0.0, 0.0, 0.0))
    for v in mesh.vertices:
        median += v.co
    median /= len(mesh.vertices)

    for v in mesh.vertices:
        v.co -= median

    obj.matrix_world = obj.matrix_world @ Matrix.Translation(median)


def _ground_segments(source, level):
    """The contour where `source` crosses world height `level`.

    The same two passes the create operator makes - at the height asked for,
    and a whisker above it for an object that is standing on that height rather
    than sunk through it - kept here so a rebuild and a create cannot drift.
    """
    import bmesh
    from mathutils import Vector

    bm = bmesh.new()
    try:
        bm.from_mesh(source.data)
        inverse = source.matrix_world.inverted()
        plane_co = inverse @ Vector((0.0, 0.0, level))
        plane_no = (inverse.transposed().to_3x3()
                    @ Vector((0.0, 0.0, 1.0))).normalized()
        segments = geometry.gather_ground_edge_segments(bm, plane_co, plane_no)
        if not segments:
            step = plane_no.normalized() * geometry.CONTACT_TOLERANCE
            segments = geometry.gather_ground_edge_segments(
                bm, plane_co + step, plane_no)
            for segment in segments:
                segment.v0 -= step
                segment.v1 -= step
        return segments
    finally:
        bm.free()


def rebuild(obj, data=None):
    """Regenerate `obj`'s mesh from its stored source, edges and settings.

    Returns a short status string for the panel, or None when everything is
    fine. Never raises: this runs from a UI callback, where an exception would
    surface as a traceback in the console on every mouse move.

    `data` is the per-object settings group to read; it defaults to this tool's
    own. Edge Dirt builds the identical strip and differs only in the texture on
    it, so it passes its own group in here rather than carrying a second copy of
    this function that would drift from this one.
    """
    global _rebuilding
    if _rebuilding:
        return None

    data = data if data is not None else obj.seto_fake_ao_data
    source = data.source_object
    if source is None:
        # Cleared on purpose, most likely: a strip that has been moved
        # somewhere else of its own accord has to be cut loose first, or the
        # next rebuild puts it back on the object it came from. Said as a fact
        # rather than as an error, because that is what it is.
        return "Detached from its source - settings no longer rebuild it."
    if source.type != 'MESH':
        return "Source object is not a mesh."
    if source.mode == 'EDIT':
        return "Source is in Edit Mode - leave it to rebuild."

    keys = parse_edge_keys(data.edge_keys)
    frozen = data.frozen_segments
    if not keys and not frozen:
        return "No stored edge selection."

    _rebuilding = True
    try:
        if getattr(data, "source_mode", 'SELECTION') == 'GROUND':
            # Re-cut at whatever height the panel is showing now, rather than
            # replaying the contour that was frozen at creation - that is what
            # makes Ground Level a slider you can drag and watch.
            segments, missing = _ground_segments(source, data.ground_level), 0
        elif frozen:
            # The corner this was built from no longer exists in the source -
            # see serialise_segments().
            segments, missing = parse_segments(frozen), 0
        else:
            segments, missing = segments_from_keys(source.data, keys)
        if not segments:
            return "Stored edges are gone from the source mesh (was it edited?)."

        strip_data = geometry.build_strip_mesh_data(
            segments,
            width=data.width,
            surface_offset=data.surface_offset,
            alpha_center=data.alpha_center,
            alpha_outer=data.alpha_outer,
            invert_fade=data.invert_fade,
            flip_direction=data.flip_direction,
            alpha_bottom=data.alpha_bottom,
            alpha_top=data.alpha_top,
            up_axis=geometry.local_up_axis(source.matrix_world),
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
        geometry.merge_by_distance(
            new_mesh, geometry.auto_merge_distance(data.width, data.surface_offset))
        # Strip bevel only. The source bevel physically altered the source
        # mesh once, at creation - re-running it here would chamfer the
        # chamfer, every time a slider moved.
        apply_strip_bevel(new_mesh, segments, data)
        geometry.normalise_uvs(new_mesh, UV_SIZE)
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
    if _rebuilding or not self.is_fake_ao or not self.live_update:
        return
    self.status = rebuild(obj) or ""
    # The strip's Bevel drives the source's round as well as its own, so the
    # two stay the same shape while a slider is being dragged. Cheap enough to
    # run on every change: it only ever touches this source's own modifier and
    # the edges its strips own.
    source_bevel.sync(self.source_object, leader=obj)


def _object_annotations():
    """Bookkeeping properties, plus the tool's settings wired to rebuild the
    object as soon as they change."""
    annotations = {
        "is_fake_ao": bpy.props.BoolProperty(
            name="Is Ambient Occlusion",
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
        "frozen_segments": bpy.props.StringProperty(
            name="Frozen Segments",
            description=(
                "The corner geometry this strip was built from, kept verbatim for the case "
                "where the source edge was beveled away and its indices no longer mean anything"
            ),
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


class SETO_PG_fake_ao_object(bpy.types.PropertyGroup):
    __annotations__ = _object_annotations()


class SETO_OT_fake_ao_rebuild(bpy.types.Operator):
    """Regenerate this Ambient Occlusion strip from its stored source edges and settings"""
    bl_idname = "seto.fake_ao_rebuild"
    bl_label = "Rebuild Now"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.seto_fake_ao_data.is_fake_ao

    def execute(self, context):
        obj = context.active_object
        message = rebuild(obj)
        obj.seto_fake_ao_data.status = message or ""
        if message:
            self.report({'WARNING'}, message)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Rebuilt '{obj.name}' ({len(obj.data.polygons)} quad(s)).")
        return {'FINISHED'}


_classes = (
    SETO_PG_fake_ao_object,
    SETO_OT_fake_ao_rebuild,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.seto_fake_ao_data = bpy.props.PointerProperty(type=SETO_PG_fake_ao_object)


def unregister():
    del bpy.types.Object.seto_fake_ao_data
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
