"""Pure mesh-generation logic for the Smooth Edge strip.

This module has no knowledge of Sollumz. It only knows how to turn a set of
selected BMesh edges (in the source object's local space) into a lightweight
strip mesh, with a per-vertex UV and alpha value already computed. All
Sollumz-specific attribute naming/creation happens in sollumz_integration.py.

The selection is first grouped into continuous EDGE CHAINS, then a single
unbroken ribbon is extruded along each chain. Doing it chain-first rather than
edge-by-edge is what makes the two headline behaviours possible:

  * The strip reads as one continuous run of chipped plaster along a wall
    edge, because consecutive cross-sections literally share vertices instead
    of being generated apart and welded back together afterwards.
  * The texture can run ALONG the chain, which needs a cumulative arc-length U
    coordinate - only available once the edges are known to be in order.

The ribbon is 2 quads wide per segment: one wing lying flat on each adjacent
wall, meeting at a shared inner vertex line that sits on the corner itself.

UVs are built straight by construction, in real world units:

    U   distance travelled along the chain
    V   distance across the cross-section - 0 at wing 0's outer edge, `width`
        at the corner, `2 * width` at wing 1's outer edge

Laying them out from the geometry rather than unwrapping is what guarantees a
straight rectangular island no matter how the selected edges curve: an arc,
a 90-degree turn and a straight run all produce the same clean strip in UV
space. normalise_uvs() then fits that rectangle into the 0..1 square with its
aspect ratio intact, which is numerically the same result a Conformal unwrap
gives on a strip like this - just without the wobble a solver introduces on
curved input, and without needing an operator, so the live rebuild can
produce final UVs too.
"""

from dataclasses import dataclass, field

import bpy
import bmesh
from mathutils import Matrix, Vector

_EPS = 1e-8

# A miter at a very sharp turn mathematically shoots off to infinity. Cap the
# resulting vector so a near-180-degree fold produces a blunt joint instead of
# a spike that reaches across the whole model.
_MITER_LIMIT = 4.0

# Cross-section V positions as multiples of `width`: wing 0's outer edge, the
# shared corner, wing 1's outer edge. Scaled by the real width at build time so
# U and V share one unit and the island keeps true proportions.
_V_INNER_FACTOR = 1.0
_V_OUTER_FACTORS = (0.0, 2.0)


@dataclass
class StripMeshData:
    verts: list = field(default_factory=list)          # list[Vector], local space
    faces: list = field(default_factory=list)           # list[tuple[int, int, int, int]]
    vertex_uv: list = field(default_factory=list)        # list[tuple[float, float]], aligned with verts
    vertex_alpha: list = field(default_factory=list)     # list[float], aligned with verts


@dataclass
class DamageEdge:
    """One selected edge, stored by vertex index so edges can be chained.

    `normals`/`face_centers` hold up to 2 entries - one per adjacent face,
    i.e. one per wall the strip will wrap onto. A boundary edge (door frame,
    open border) has only 1 and produces a single wing.
    """
    va: int
    vb: int
    normals: list
    face_centers: list


@dataclass
class _Side:
    """One wall an edge borders: the wall's normal plus the in-plane direction
    the wing extends toward (away from the corner, onto that wall)."""
    normal: Vector
    tangent: Vector


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


def gather_selected_edges(bm):
    """Read the selected edges out of an edit-mode BMesh.

    For each selected edge, collects up to 2 adjacent faces (sorted by a
    deterministic key - lowest face.index - so the same pair of walls always
    resolves in the same order across every edge that borders them, e.g. a
    subdivided corner edge). Edges with no linked face at all, or of zero
    length, are skipped and counted.

    All values are copied out as plain Vectors so the result stays valid after
    the BMesh/edit-mode goes away.

    Returns (edges, coords, skipped):
      edges   list[DamageEdge]
      coords  dict[vertex index -> Vector], local space
      skipped count of selected edges that could not be used
    """
    bm.verts.index_update()
    bm.faces.index_update()

    edges = []
    coords = {}
    skipped = 0

    for edge in bm.edges:
        if not edge.select:
            continue

        faces = sorted(edge.link_faces, key=lambda f: f.index)[:2]
        if not faces:
            skipped += 1
            continue

        v0, v1 = edge.verts
        if (v1.co - v0.co).length < _EPS:
            skipped += 1
            continue

        coords[v0.index] = v0.co.copy()
        coords[v1.index] = v1.co.copy()
        edges.append(DamageEdge(
            va=v0.index,
            vb=v1.index,
            normals=[f.normal.copy() for f in faces],
            face_centers=[f.calc_center_median() for f in faces],
        ))

    return edges, coords, skipped


def build_edge_chains(edges):
    """Group the selected edges into ordered, continuous chains.

    A chain is walked vertex to vertex through shared vertices and ends at:
      * a loose end (vertex with only one selected edge),
      * a junction (vertex with 3+ selected edges - there is no single correct
        way to continue, so the chain is cut and the pieces are left for the
        merge pass to weld positionally), or
      * its own start vertex (a closed loop, e.g. a full window surround).

    Chains starting from loose ends are emitted first so an open run is always
    walked end to end rather than from some arbitrary middle vertex.

    Returns list[(vertex_sequence, edge_index_sequence)] where
    len(vertex_sequence) == len(edge_index_sequence) + 1. For a closed loop the
    first and last vertex are the same index.
    """
    adjacency = {}
    for i, edge in enumerate(edges):
        adjacency.setdefault(edge.va, []).append(i)
        adjacency.setdefault(edge.vb, []).append(i)

    used = set()

    def walk(start):
        vseq = [start]
        eseq = []
        current = start
        while True:
            # Stop before continuing THROUGH a junction, and stop once the
            # walk has come back around to where it started.
            if eseq and (len(adjacency[current]) > 2 or current == start):
                break
            next_edge = next((i for i in adjacency[current] if i not in used), None)
            if next_edge is None:
                break
            used.add(next_edge)
            edge = edges[next_edge]
            other = edge.vb if edge.va == current else edge.va
            eseq.append(next_edge)
            vseq.append(other)
            current = other
        return vseq, eseq

    chains = []
    ordered_verts = sorted(adjacency)

    for v in ordered_verts:
        if len(adjacency[v]) == 1 and adjacency[v][0] not in used:
            chains.append(walk(v))

    # Whatever is left is either a closed loop or a spoke radiating from a
    # junction; both are walked from any remaining unused edge at that vertex.
    for v in ordered_verts:
        while any(i not in used for i in adjacency[v]):
            chains.append(walk(v))

    return [chain for chain in chains if chain[1]]


def _edge_sides(edge, point_a, point_b, flip_direction):
    """Resolve an edge's adjacent walls into _Side entries.

    The tangent is pointed toward the interior of its own wall (i.e. onto the
    surface, away from the corner) using the face centre, so it is correct
    regardless of which way round the chain happens to traverse this edge.
    """
    direction = point_b - point_a
    length = direction.length
    if length < _EPS:
        return []
    direction = direction / length
    midpoint = (point_a + point_b) * 0.5

    sides = []
    for normal, face_center in zip(edge.normals, edge.face_centers):
        if normal.length < _EPS:
            continue
        n = normal.normalized()
        tangent = n.cross(direction)
        if tangent.length < _EPS:
            # Edge parallel to the face normal (degenerate face).
            continue
        tangent.normalize()
        if tangent.dot(face_center - midpoint) < 0.0:
            tangent.negate()
        if flip_direction:
            tangent.negate()
        sides.append(_Side(normal=n, tangent=tangent))
    return sides


def _assign_slots(chain_sides):
    """Decide, per edge, which wall is "wing 0" and which is "wing 1".

    Sorting by face.index is stable across a subdivided edge but says nothing
    useful once the chain bends onto a different pair of walls - and if the
    slots swap mid-chain, the ribbon turns inside out and the texture flips.
    So slots are propagated by normal continuity instead: the wall most
    closely aligned with the previous edge's wing 0 stays wing 0.

    Returns list (aligned with chain_sides) of [slot0, slot1], each entry a
    _Side or None.
    """
    slots = []
    refs = [None, None]

    for sides in chain_sides:
        slot = [None, None]

        if not sides:
            slots.append(slot)
            continue

        if refs[0] is None and refs[1] is None:
            for i, side in enumerate(sides[:2]):
                slot[i] = side
        elif len(sides) == 1:
            side = sides[0]
            d0 = side.normal.dot(refs[0]) if refs[0] is not None else -2.0
            d1 = side.normal.dot(refs[1]) if refs[1] is not None else -2.0
            slot[0 if d0 >= d1 else 1] = side
        else:
            first, second = sides[0], sides[1]

            def score(for_slot0, for_slot1):
                total = 0.0
                if refs[0] is not None:
                    total += for_slot0.normal.dot(refs[0])
                if refs[1] is not None:
                    total += for_slot1.normal.dot(refs[1])
                return total

            if score(first, second) >= score(second, first):
                slot[0], slot[1] = first, second
            else:
                slot[0], slot[1] = second, first

        for i in (0, 1):
            if slot[i] is not None:
                refs[i] = slot[i].normal
        slots.append(slot)

    return slots


def _cross_sections(points, slots, width, surface_offset, closed=False):
    """Build the inner/outer ring of points at every vertex along one chain.

    The inner point is shared by both wings and is lifted off the surface
    along the AVERAGE of every adjacent wall normal - i.e. along the corner
    bisector. That keeps the seam centred in the corner instead of pushing it
    onto one wall's face, and means the two wings genuinely share a vertex
    rather than needing to be welded later.

    At an interior vertex the outer point is mitered against both incident
    edges, so a bend in the chain produces a clean picture-frame joint at a
    constant `width` from the edge rather than two overlapping rectangles.

    On a CLOSED chain the first and last entries describe the same vertex, and
    each would otherwise see only one of its two edges - leaving the seam
    corner unmitered while every other corner is clean. `closed` wraps the
    incident lookup around so both ends are mitered against the same pair of
    edges and therefore land on identical positions. They stay separate
    vertices on purpose: the merge pass welds them positionally, but the two
    ends carry different U values (0 and the full chain length), and that UV
    seam is exactly what a looping texture needs.

    Returns (inner, outer):
      inner  list[Vector|None] per chain vertex
      outer  [list[Vector|None], list[Vector|None]] - one list per wing
    """
    count = len(points)
    inner = []
    outer = [[None] * count, [None] * count]

    for j in range(count):
        incident = []
        if j > 0:
            incident.append(slots[j - 1])
        elif closed:
            incident.append(slots[-1])
        if j < count - 1:
            incident.append(slots[j])
        elif closed:
            incident.append(slots[0])

        normals = [side.normal for slot in incident for side in slot if side is not None]
        if not normals:
            inner.append(None)
            continue

        average = Vector((0.0, 0.0, 0.0))
        for normal in normals:
            average += normal
        average = average.normalized() if average.length > _EPS else normals[0].copy()

        inner_point = points[j] + average * surface_offset
        inner.append(inner_point)

        for wing in (0, 1):
            present = [slot[wing] for slot in incident if slot[wing] is not None]
            if not present:
                continue

            if len(present) == 1:
                offset = present[0].tangent * width
            else:
                a, b = present[0], present[1]
                plane_normal = a.normal + b.normal
                plane_normal = (plane_normal.normalized()
                                if plane_normal.length > _EPS else a.normal)
                offset = _miter_vector(a.tangent, b.tangent, plane_normal, width)
                if offset is None:
                    # Collinear edges - the wings continue straight through.
                    offset = a.tangent * width
                elif offset.length > width * _MITER_LIMIT:
                    offset = offset.normalized() * (width * _MITER_LIMIT)

            outer[wing][j] = inner_point + offset

    return inner, outer


def build_damage_mesh_data(edges, chains, coords, width, surface_offset,
                           alpha_center, alpha_outer, invert_fade, flip_direction):
    """Generate the full Smooth Edge ribbon for every chain.

    Geometry within a chain is continuous by construction: consecutive
    segments reference the same cross-section vertices, so there is nothing to
    weld and nothing to overlap. Only the joints BETWEEN chains (junctions,
    loop seams) rely on the merge pass afterwards.
    """
    data = StripMeshData()

    inner_alpha = alpha_outer if invert_fade else alpha_center
    outer_alpha = alpha_center if invert_fade else alpha_outer

    for vseq, eseq in chains:
        points = [coords[v] for v in vseq]

        chain_sides = [
            _edge_sides(edges[edge_index], points[k], points[k + 1], flip_direction)
            for k, edge_index in enumerate(eseq)
        ]
        slots = _assign_slots(chain_sides)
        # build_edge_chains marks a closed loop by repeating the start vertex.
        closed = len(vseq) > 2 and vseq[0] == vseq[-1]
        inner, outer = _cross_sections(points, slots, width, surface_offset, closed)

        # Fallback U: the real distance travelled along the chain, so even
        # without the unwrap the texture keeps a constant density through
        # bends and never restarts or rotates between connected segments.
        distance = [0.0] * len(points)
        for j in range(1, len(points)):
            distance[j] = distance[j - 1] + (points[j] - points[j - 1]).length

        inner_index = [None] * len(points)
        outer_index = [[None] * len(points), [None] * len(points)]

        for j, inner_point in enumerate(inner):
            if inner_point is None:
                continue
            u = distance[j]

            inner_index[j] = len(data.verts)
            data.verts.append(inner_point)
            data.vertex_uv.append((u, _V_INNER_FACTOR * width))
            data.vertex_alpha.append(inner_alpha)

            for wing in (0, 1):
                outer_point = outer[wing][j]
                if outer_point is None:
                    continue
                outer_index[wing][j] = len(data.verts)
                data.verts.append(outer_point)
                data.vertex_uv.append((u, _V_OUTER_FACTORS[wing] * width))
                data.vertex_alpha.append(outer_alpha)

        for k in range(len(eseq)):
            j0, j1 = k, k + 1
            if inner_index[j0] is None or inner_index[j1] is None:
                continue

            for wing in (0, 1):
                side = slots[k][wing]
                if side is None:
                    continue
                a = outer_index[wing][j0]
                b = outer_index[wing][j1]
                if a is None or b is None:
                    continue

                data.faces.append(_oriented_quad_indices(
                    (outer[wing][j0], a),
                    (inner[j0], inner_index[j0]),
                    (inner[j1], inner_index[j1]),
                    (outer[wing][j1], b),
                    side.normal,
                ))

    return data


def create_mesh_from_strip_data(name, strip_data):
    """Create a new bpy.types.Mesh (position/face data only) from StripMeshData."""
    mesh = bpy.data.meshes.new(name)
    verts = [tuple(v) for v in strip_data.verts]
    mesh.from_pydata(verts, [], strip_data.faces)
    mesh.update()
    shade_smooth(mesh)
    return mesh


def shade_smooth(mesh):
    """Mark every face smooth - the point of this tool.

    A flat-shaded strip shows a hard band at each quad boundary, which is
    exactly the seam a smooth-edge decal exists to hide. Done through the data
    API (per-polygon use_smooth) rather than bpy.ops.object.shade_smooth, so it
    works from the live rebuild's property callback too, where calling an
    operator is not safe.

    Only the generated strip is ever touched; the source mesh is not shaded,
    moved or modified in any way.
    """
    if not mesh.polygons:
        return
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    mesh.update()


def compute_loop_uv_and_alpha(mesh, strip_data, color_rgb=(1.0, 1.0, 1.0)):
    """Expand the per-vertex UV/alpha values out to per-loop (face-corner) arrays,
    matching Blender's CORNER-domain attribute layout.

    `color_rgb` is constant across every vertex (corner and outer alike) -
    only alpha varies, per Sollumz's Color 1 fade design.
    """
    r, g, b = color_rgb
    loop_uv = [(0.0, 0.0)] * len(mesh.loops)
    loop_rgba = [(r, g, b, 1.0)] * len(mesh.loops)

    for loop in mesh.loops:
        vidx = loop.vertex_index
        loop_uv[loop.index] = strip_data.vertex_uv[vidx]
        loop_rgba[loop.index] = (r, g, b, strip_data.vertex_alpha[vidx])

    return loop_uv, loop_rgba


def normalise_uvs(mesh, size=1.5):
    """Fit the UV island into the 0..1 square, centred, keeping its aspect ratio.

    The authored UVs are in metres, so a long run would otherwise sprawl far
    outside the square. Both axes are scaled by the SAME factor - never fitted
    independently - so the strip keeps its true proportions: a 2 m run 0.05 m
    wide stays 20:1 in UV space rather than being squashed into a square.

    `size` is the span of the longer axis once fitted; 1.5 matches what the
    tool has always produced.
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
    behind, so separately-generated chains that meet at a shared corner become
    one continuous mesh instead of overlapping planes.

    Runs once, on the finished mesh containing every chain's geometry - never
    per chain - so sections generated from different chains get a chance to
    weld to each other. Geometry inside a single chain is already continuous
    and has nothing to merge.

    Four passes:
      1. Centroid snap: move each cluster of vertices within `distance` of
         each other onto their common average position. Blender's plain weld
         keeps one vertex of the pair and discards the other, which drags the
         seam onto one wall's surface_offset; averaging keeps the joint
         centred. Equivalent to ticking "Centroid" on a manual Merge by
         Distance.
      2. Merge by Distance: weld the now-coincident vertices together.
      3. Dissolve degenerate: welding two corners of a quad onto each other
         leaves a zero-length edge / zero-area face behind. Remove those.
      4. Duplicate faces: after welding, two sections can end up with faces
         referencing the exact same vertices. Keep one, drop the rest.

    Safe to call after the UV/Color attributes have been written: chains that
    meet at a shared corner carry matching alpha values there, so whichever
    vertex of a near-duplicate pair survives keeps sane data either way. Face
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
