"""Pure mesh-generation logic for the Fake AO strip.

This module has no knowledge of Sollumz. It only knows how to turn a set of
selected BMesh edges (in the source object's local space) into a lightweight
strip mesh, with a per-vertex UV and alpha value already computed. All
Sollumz-specific attribute naming/creation happens in sollumz_integration.py.
"""

from dataclasses import dataclass, field

import bpy
import bmesh
from mathutils import Matrix, Vector


@dataclass
class EdgeSegment:
    """One selected edge plus every adjacent face that gets its own wing of
    the L-shaped strip.

    `normals`/`face_centers` have 2 entries for a true architectural corner
    (edge shared by two walls - one wing per wall) and 1 entry for a
    boundary edge (e.g. a door frame edge with only one adjacent face -
    a single wing, since there's no second wall to wrap onto).
    """
    v0: Vector
    v1: Vector
    normals: list
    face_centers: list


@dataclass
class StripMeshData:
    verts: list = field(default_factory=list)          # list[Vector], local space
    faces: list = field(default_factory=list)           # list[tuple[int, int, int, int]]
    vertex_uv: list = field(default_factory=list)        # list[tuple[float, float]], aligned with verts
    vertex_alpha: list = field(default_factory=list)     # list[float], aligned with verts


@dataclass
class _Wing:
    """One end of one generated wing, as needed by the miter pass."""
    corner: Vector       # the original selected-edge endpoint this end sits on
    normal: Vector       # the wall this wing lies on
    tangent: Vector      # in-plane direction the wing extends toward
    outer_index: int     # index into StripMeshData.verts of this end's OUTER vertex


def _quantize(vec, places=4):
    """Round a vector into a dict key so points/normals that are the same to
    within float noise group together."""
    return (round(vec.x, places), round(vec.y, places), round(vec.z, places))


def _oriented_quad_indices(p0_i0, p1_i1, p2_i2, p3_i3, desired_normal):
    """Return the 4 vertex indices in whichever winding order (forward or
    reversed) makes the resulting face normal point toward `desired_normal`.

    Each argument is a (point: Vector, index: int) pair for one corner of the
    quad, given in a candidate cyclic order. Computed directly against the
    actual point positions rather than assumed algebraically, so it is
    correct regardless of how the tangent/offset directions were derived or
    sign-corrected upstream.
    """
    (p0, i0), (p1, i1), (p2, i2), (p3, i3) = p0_i0, p1_i1, p2_i2, p3_i3
    normal = (p1 - p0).cross(p2 - p1)
    if normal.dot(desired_normal) < 0.0:
        return (i3, i2, i1, i0)
    return (i0, i1, i2, i3)


def auto_merge_distance(width, surface_offset):
    """How close two vertices have to be before they are welded together.

    Used to be a slider, and it was a slider with exactly one correct answer:
    big enough to close the seam where two wings meet, small enough not to
    collapse the strip. Both bounds come from the other two settings, so it is
    worked out rather than asked for.

    The seam is the wide end of it. Each wing is lifted off its own wall by
    Surface Offset along that wall's normal, so at a right-angled corner the
    two wings' inner edges end up `surface_offset * sqrt(2)` apart - and more
    than that on a shallower corner. Four times Surface Offset covers a corner
    down to about 30 degrees, and is still two orders of magnitude below Width
    at the defaults.

    The floor keeps float noise between wings generated from different edges
    weldable when Surface Offset is at its smallest; the Width ceiling is the
    backstop that stops the weld eating a strip that is narrower than the
    offset it sits on.
    """
    return min(max(surface_offset * 4.0, 1e-4), width * 0.25)


def faces_for_edge(edge, exclude_faces=None):
    """The up-to-2 adjacent faces that get a wing, in a deterministic order.

    Sorted by lowest face.index so the same pair of faces always resolves in
    the same order across every edge that borders them (e.g. a subdivided
    corner edge).

    `exclude_faces` is a set of BMFaces that must never receive a wing - used
    by the source bevel, whose chamfer faces are the highlight and are
    deliberately left bare.
    """
    faces = edge.link_faces
    if exclude_faces:
        faces = [f for f in faces if f not in exclude_faces]
    return sorted(faces, key=lambda f: f.index)[:2]


def gather_selected_edge_segments(bm, exclude_faces=None):
    """Read selected edges from an edit-mode BMesh.

    For each selected edge, collects up to 2 adjacent faces (see
    faces_for_edge). Edges left with no usable face - no linked face at all
    (a fully detached edge), or every linked face excluded - are skipped and
    counted.

    All values are copied out as plain Vectors so the result stays valid
    after the BMesh/edit-mode goes away.

    Returns (segments: list[EdgeSegment], skipped_count: int).
    """
    segments = []
    skipped = 0

    for edge in bm.edges:
        if not edge.select:
            continue

        faces = faces_for_edge(edge, exclude_faces)
        if not faces:
            skipped += 1
            continue

        segments.append(EdgeSegment(
            v0=edge.verts[0].co.copy(),
            v1=edge.verts[1].co.copy(),
            normals=[f.normal.copy() for f in faces],
            face_centers=[f.calc_center_median() for f in faces],
        ))

    return segments, skipped


def build_strip_mesh_data(segments, width, surface_offset, alpha_center, alpha_outer,
                           invert_fade, flip_direction):
    """Build strip geometry for each edge segment independently (no welding
    between segments - see Version 0.1 limitations).

    Builds an "L" shaped corner piece that WRAPS BOTH adjacent walls when the
    selected edge has two (a true architectural corner): one flat wing lying
    on each wall, both meeting at the shared corner edge - like a physical
    angle-bracket corner bead. For a boundary edge with only one adjacent
    face (e.g. a door frame edge), only a single wing is generated (there is
    no second wall to wrap onto).

    Each wing, independently, for its own wall:

        INNER (at the corner, offset off the wall by `surface_offset`
               to avoid z-fighting) ---- OUTER (extends onto that wall's
                                                 surface by `width`)
    """
    data = StripMeshData()
    wings = []

    inner_alpha = alpha_outer if invert_fade else alpha_center
    outer_alpha = alpha_center if invert_fade else alpha_outer

    for seg in segments:
        edge_vec = seg.v1 - seg.v0
        edge_len = edge_vec.length
        if edge_len < 1e-8:
            continue
        edge_dir = edge_vec / edge_len

        for face_normal, face_center in zip(seg.normals, seg.face_centers):
            if face_normal.length < 1e-8:
                continue
            normal = face_normal.normalized()

            tangent = normal.cross(edge_dir)
            if tangent.length < 1e-8:
                # Edge is parallel to the face normal (degenerate face) - can't orient a wing.
                continue
            tangent.normalize()

            # Point the tangent toward the interior of this specific wall (i.e.
            # "onto the surface, away from the corner") rather than away from the mesh.
            edge_mid = (seg.v0 + seg.v1) * 0.5
            if tangent.dot(face_center - edge_mid) < 0.0:
                tangent.negate()

            if flip_direction:
                tangent.negate()

            offset = normal * surface_offset
            inner0 = seg.v0 + offset
            inner1 = seg.v1 + offset
            outer0 = inner0 + tangent * width
            outer1 = inner1 + tangent * width

            base_idx = len(data.verts)
            data.verts.extend([inner0, inner1, outer1, outer0])
            # UVs in metres, laid out straight from the wing itself: U runs
            # along the selected edge, V across the shelf. Built rather than
            # projected, so the island is a clean rectangle whatever direction
            # the edge points in - see normalise_uvs().
            data.vertex_uv.extend([
                (0.0, 0.0), (edge_len, 0.0), (edge_len, width), (0.0, width),
            ])
            data.vertex_alpha.extend([inner_alpha, inner_alpha, outer_alpha, outer_alpha])

            face = _oriented_quad_indices(
                (inner0, base_idx + 0), (inner1, base_idx + 1),
                (outer1, base_idx + 2), (outer0, base_idx + 3),
                normal,
            )
            data.faces.append(face)

            # Record what this wing needs for mitering: which original edge
            # endpoint each OUTER vertex belongs to, plus the wing's own
            # in-plane frame. Index layout is [inner0, inner1, outer1, outer0],
            # so the outer vertex on the v0 end is base_idx+3 and on the v1
            # end is base_idx+2.
            wings.append(_Wing(corner=seg.v0, normal=normal, tangent=tangent,
                               outer_index=base_idx + 3))
            wings.append(_Wing(corner=seg.v1, normal=normal, tangent=tangent,
                               outer_index=base_idx + 2))

    _miter_coplanar_wings(data, wings, width, surface_offset)

    return data


def _miter_coplanar_wings(data, wings, width, surface_offset):
    """Trim overlapping wings into a clean mitered joint.

    Two wings generated from different selected edges that meet at a shared
    endpoint AND lie on the SAME wall are coplanar, so they overlap in area
    near that shared point - welding cannot fix that, because their outer
    vertices are a full `width` apart. The fix is the same one a picture
    frame uses: move both outer vertices to the point where the two wings'
    outer edges actually cross.

    Wings on *different* walls (a real 3D corner) are left alone - they meet
    along the shared edge and never overlap in area.
    """
    groups = {}
    for wing in wings:
        key = (_quantize(wing.corner), _quantize(wing.normal))
        groups.setdefault(key, []).append(wing)

    for group in groups.values():
        if len(group) != 2:
            # 1 wing = nothing to miter against. 3+ wings meeting coplanarly
            # at one point has no single well-defined miter point, so leave
            # it to the weld pass rather than guessing.
            continue

        wing_a, wing_b = group
        miter = _miter_vector(wing_a.tangent, wing_b.tangent, wing_a.normal, width)
        if miter is None:
            # Tangents are (nearly) parallel - the edges are collinear, so
            # the wings sit end to end and never overlap. Nothing to do.
            continue

        miter_point = wing_a.corner + wing_a.normal * surface_offset + miter
        data.verts[wing_a.outer_index] = miter_point
        data.verts[wing_b.outer_index] = miter_point


def _miter_vector(tangent_a, tangent_b, normal, width):
    """In-plane vector `m` from the shared corner to the miter point, i.e. the
    point that sits exactly `width` away from BOTH wings' edge lines:

        m . tangent_a = width      (on wing A's outer edge line)
        m . tangent_b = width      (on wing B's outer edge line)
        m . normal    = 0          (stays in the wall plane)

    Returns None when the system is singular (tangents parallel).
    """
    matrix = Matrix((tangent_a, tangent_b, normal))
    if abs(matrix.determinant()) < 1e-6:
        return None
    try:
        return matrix.inverted() @ Vector((width, width, 0.0))
    except ValueError:
        return None


# How far off parallel a chamfer edge may be and still count as running along
# the original edge. Generous, so a chamfer over a curved rim still qualifies.
_ALONG_TOLERANCE = 0.9


def _runs_along_any(edge, directions):
    vec = edge.verts[1].co - edge.verts[0].co
    if vec.length < 1e-8:
        return False
    vec.normalize()
    return any(abs(vec.dot(d)) >= _ALONG_TOLERANCE for d in directions)


def bevel_source_edges(bm, width, segments, profile):
    """Chamfer the selected edges of the SOURCE mesh, in place.

    This is the one thing in the tool that modifies the object you started
    from, which is why it is opt-in. It is the manual workflow it replaces:
    bevel the razor-sharp corner so it catches a highlight, then run the decal
    along it.

    Afterwards the selection is moved onto the chamfer's **rim** edges - the
    ones where the chamfer meets each original wall - because those, not the
    edge that no longer exists, are where the AO now has to start.

    Returns the set of faces the bevel created. They are handed to
    gather_selected_edge_segments as `exclude_faces`: each rim edge then has
    exactly one usable face (its wall), so the strip fades outward onto both
    walls and leaves the chamfer itself clean. Two rim edges each growing a
    wing onto the shared chamfer would just overlap.

    Returns an empty set when there is nothing to bevel, leaving the selection
    untouched.
    """
    edges = [edge for edge in bm.edges if edge.select]
    if not edges or width <= 0.0:
        return set()

    # Read before the bevel deletes the originals: which way each selected
    # edge ran. Used below to tell the chamfer's long sides apart from the
    # caps at either end of it.
    directions = []
    for edge in edges:
        vec = edge.verts[1].co - edge.verts[0].co
        if vec.length > 1e-8:
            directions.append(vec.normalized())

    result = bmesh.ops.bevel(
        bm,
        geom=edges,
        offset=width,
        offset_type='OFFSET',
        profile_type='SUPERELLIPSE',
        segments=max(1, int(segments)),
        profile=profile,
        affect='EDGES',
        # Inherit the material of the wall each face came from. bmesh defaults
        # this to 0, which is NOT what Blender's own Bevel does - its Material
        # Index defaults to -1, "same as the adjacent face". Left at the bmesh
        # default the chamfer is dragged onto slot 0 whatever that happens to
        # be, and a corner beveled through a wall whose brick is in slot 1 comes
        # out as a band of the wrong material running the length of the corner.
        material=-1,
        # Never let a bevel eat past a neighbouring edge, the way ticking
        # Clamp Overlap in Blender's own bevel keeps it sane on thin walls.
        clamp_overlap=True,
        loop_slide=True,
    )
    new_faces = set(result.get("faces", ()))
    if not new_faces:
        return set()

    bm.normal_update()

    for vert in bm.verts:
        vert.select = False
    for edge in bm.edges:
        edge.select = False
    for face in bm.faces:
        face.select = False
    for face in new_faces:
        for edge in face.edges:
            if all(linked in new_faces for linked in edge.link_faces):
                continue  # inside the chamfer, on a multi-segment round
            if not _runs_along_any(edge, directions):
                # A cap: the short edge closing the chamfer off at the end of
                # the run. It borders a wall too, but running the AO along it
                # would decal the end cap, not the corner.
                continue
            edge.select_set(True)

    # Deliberately no select_flush(True): flushing selection up from the
    # vertices would pull the caps straight back in, since both of their
    # vertices belong to rim edges. Everything was cleared before the rim was
    # selected, and nothing is cleared after - assigning `select` on a face
    # flushes DOWN, and would deselect the rim edges again.
    bm.verts.index_update()
    bm.faces.index_update()
    bm.normal_update()

    return new_faces


def bevel_strip_corners(mesh, corner_points, width, segments, profile, tolerance):
    """Chamfer the strip's own corner - the seam where its two wings meet.

    Run on the finished, welded strip, so the two wings are already one
    continuous mesh and the seam is a real edge with a face on either side.
    A wing that never got a partner (a boundary edge like a door frame) has
    only one face along that edge and is left alone: there is no corner there
    to round.

    The seam is found by position rather than by dihedral angle: an edge whose
    two ends sit on `corner_points` - the original selected-edge endpoints -
    within `tolerance`. Angle would misread a curved rim, where the joints
    between consecutive wings are bent too.

    Called after the UV/Color attributes are written, so bmesh interpolates
    them onto the new chamfer. Both sides of the seam carry the same values
    (they are the same conceptual point), so the chamfer comes out at a
    constant corner alpha - which is what an AO corner wants anyway.

    Returns the number of seams beveled.
    """
    if width <= 0.0 or not corner_points:
        return 0

    bm = bmesh.new()
    bm.from_mesh(mesh)

    limit = tolerance * tolerance
    targets = []
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        a, b = edge.verts[0].co, edge.verts[1].co
        for p, q in corner_points:
            if ((a - p).length_squared <= limit and (b - q).length_squared <= limit) or \
                    ((a - q).length_squared <= limit and (b - p).length_squared <= limit):
                targets.append(edge)
                break

    if targets:
        bmesh.ops.bevel(
            bm,
            geom=targets,
            offset=width,
            offset_type='OFFSET',
            profile_type='SUPERELLIPSE',
            segments=max(1, int(segments)),
            profile=profile,
            affect='EDGES',
            material=-1,      # inherit, like Blender's own Bevel - see bevel_source_edges
            clamp_overlap=True,
            loop_slide=True,
        )

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return len(targets)


def create_mesh_from_strip_data(name, strip_data):
    """Create a new bpy.types.Mesh (position/face data only) from StripMeshData."""
    mesh = bpy.data.meshes.new(name)
    verts = [tuple(v) for v in strip_data.verts]
    mesh.from_pydata(verts, [], strip_data.faces)
    mesh.update()
    return mesh


def compute_loop_uv_and_alpha(mesh, strip_data, color_rgb=(1.0, 1.0, 1.0)):
    """Expand the per-vertex UV/alpha values out to per-loop (face-corner) arrays,
    matching Blender's CORNER-domain attribute layout.

    `color_rgb` is constant across every vertex (center and outer alike) -
    only alpha varies between center/outer, per Sollumz's Color 1 fade design.
    """
    r, g, b = color_rgb
    loop_uv = [(0.0, 0.0)] * len(mesh.loops)
    loop_rgba = [(r, g, b, 1.0)] * len(mesh.loops)

    for loop in mesh.loops:
        vidx = loop.vertex_index
        loop_uv[loop.index] = strip_data.vertex_uv[vidx]
        loop_rgba[loop.index] = (r, g, b, strip_data.vertex_alpha[vidx])

    return loop_uv, loop_rgba


def _snap_clusters_to_centroid(bm, distance):
    """Move every group of vertices lying within `distance` of each other onto
    their shared centroid, so the weld that follows lands on the average
    position instead of snapping to whichever vertex happens to survive.

    Grouping is transitive (a chain of close vertices forms one cluster),
    matching how Blender's own Merge by Distance behaves.
    """
    verts = list(bm.verts)
    count = len(verts)
    if count < 2:
        return

    parent = list(range(count))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    limit = distance * distance
    for i in range(count):
        co_i = verts[i].co
        root_i = find(i)
        for j in range(i + 1, count):
            if (verts[j].co - co_i).length_squared <= limit:
                root_j = find(j)
                if root_i != root_j:
                    parent[root_j] = root_i
                    root_i = find(i)

    clusters = {}
    for i in range(count):
        clusters.setdefault(find(i), []).append(i)

    for members in clusters.values():
        if len(members) < 2:
            continue
        centroid = Vector((0.0, 0.0, 0.0))
        for i in members:
            centroid += verts[i].co
        centroid /= len(members)
        for i in members:
            verts[i].co = centroid


def merge_by_distance(mesh, distance):
    """Weld coincident vertices and clean up the junk that welding leaves
    behind, so separately-generated sections that meet at a shared corner
    become one continuous mesh instead of overlapping planes.

    Runs once, on the finished mesh containing every selected edge's
    geometry - never per-segment - so sections generated from different
    edges get a chance to weld to each other.

    Four passes:
      1. Centroid snap: move each cluster of vertices within `distance` of
         each other onto their common average position. Blender's plain
         weld keeps one vertex of the pair and discards the other, which
         drags the seam onto one wall's surface_offset; averaging keeps the
         joint centred between the two walls. This is the equivalent of
         ticking "Centroid" on a manual Merge by Distance.
      2. Merge by Distance: weld the now-coincident vertices together.
      3. Dissolve degenerate: welding two corners of a quad onto each other
         leaves a zero-length edge / zero-area face behind. Remove those.
      4. Duplicate faces: after welding, two sections can end up with faces
         referencing the exact same vertices. Keep one, drop the rest.

    Safe to call after the UV/Color attributes have been written: the wings
    that meet at a shared corner carry matching alpha/UV values there (they
    represent the same conceptual point), so whichever vertex of a
    near-duplicate pair survives keeps correct data either way. Face
    normals are deliberately left untouched - they were already oriented
    per-wing at build time.
    """
    bm = bmesh.new()
    bm.from_mesh(mesh)

    _snap_clusters_to_centroid(bm, distance)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=distance)
    bmesh.ops.dissolve_degenerate(bm, dist=distance, edges=bm.edges)

    bm.verts.index_update()
    seen = set()
    duplicate_faces = []
    for face in bm.faces:
        key = frozenset(v.index for v in face.verts)
        if key in seen:
            duplicate_faces.append(face)
        else:
            seen.add(key)
    if duplicate_faces:
        bmesh.ops.delete(bm, geom=duplicate_faces, context='FACES')

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def shade_smooth(mesh):
    """Mark every face smooth.

    A flat-shaded strip shows a hard band at each quad boundary, which is the
    seam a decal strip exists to hide. Done through the data API (per-polygon
    use_smooth) rather than bpy.ops.object.shade_smooth, so it works from the
    live rebuild's property callback too, where calling an operator is not safe.

    Only the generated strip is ever touched; the source mesh is not shaded,
    moved or modified in any way.
    """
    if not mesh.polygons:
        return
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    mesh.update()


def normalise_uvs(mesh, size=1.5):
    """Fit the UV island into the 0..1 square, centred, keeping its aspect ratio.

    The authored UVs are in metres, so a long edge would otherwise sprawl far
    outside the square. Both axes are scaled by the SAME factor - never fitted
    independently - so a long thin shelf stays long and thin in UV space
    rather than being squashed into a square.

    `size` is the span of the longer axis once fitted.
    """
    uv_layer = mesh.uv_layers.active
    if uv_layer is None or len(uv_layer.data) == 0:
        return

    us = [loop.uv[0] for loop in uv_layer.data]
    vs = [loop.uv[1] for loop in uv_layer.data]
    min_u, max_u = min(us), max(us)
    min_v, max_v = min(vs), max(vs)

    longest = max(max_u - min_u, max_v - min_v)
    if longest < 1e-9:
        return
    scale = size / longest

    centre_u = (min_u + max_u) * 0.5
    centre_v = (min_v + max_v) * 0.5
    for loop in uv_layer.data:
        u, v = loop.uv
        # Rotated 90 degrees counter-clockwise, (u, v) -> (-v, u), so the island
        # stands upright in the 0..1 square: a long run reads as a tall strip,
        # not a wide one. A real rotation rather than swapping the two axes -
        # swapping would mirror the island as well, which flips the direction a
        # normal map or a directional gradient points in.
        loop.uv = (0.5 - (v - centre_v) * scale,
                   0.5 + (u - centre_u) * scale)
