"""Pure geometry: reading the face selection and building decal quads.

No Sollumz and no bpy.data knowledge lives here - the operator feeds this module
a source object's matrix and a BMesh, and gets back placements and mesh data.

The one subtlety worth reading before touching this file is the two different
transforms used in surface_basis()/sample_faces(): a NORMAL must go through the
inverse-transpose normal matrix, a TANGENT must go through the plain linear part
of the world matrix. Swapping them looks fine under uniform scale and silently
tilts every decal off the surface under non-uniform scale.
"""

from mathutils import Matrix, Vector

from ..shared import vertex_color

# Faces smaller than this are skipped: their normal and tangent are numerically
# meaningless, so they would produce a garbage basis.
MIN_FACE_AREA = 1e-9

# How parallel to world Z a face normal has to be before "upright" stops being a
# meaningful concept and we fall back to the face's own edge tangent. 0.999 is
# about 2.5 degrees.
UP_PARALLEL_THRESHOLD = 0.999

# How close two touching faces have to be before they count as one flat surface.
# ~1.8 degrees of normal difference, and a hair of thickness, which is enough to
# absorb the float error in a wall that was split with a loop cut but tight
# enough that a deliberate bevel or a shallow ramp still reads as its own face.
COPLANAR_NORMAL_TOLERANCE = 0.9995
COPLANAR_DISTANCE_TOLERANCE = 1e-4

WORLD_UP = Vector((0.0, 0.0, 1.0))

_EPS = 1e-6

# Corner order, counter-clockwise seen from +Z, so the generated face normal
# equals the surface normal and the decal faces out of the wall, not into it.
_CORNER_SIGNS = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))

# Full 0-1 layout in the same corner order: the texture fills the whole quad and
# the user never has to unwrap anything.
QUAD_UVS = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


class FaceSample:
    """Everything read out of one selected face, in world space.

    Deliberately plain Vectors/floats rather than BMesh references, so the data
    stays valid after the BMesh goes away and the source mesh is never held onto.
    """

    __slots__ = ("center", "normal", "tangent", "verts", "index")

    def __init__(self, center, normal, tangent, verts, index):
        self.center = center
        self.normal = normal
        self.tangent = tangent
        self.verts = verts
        self.index = index


class DecalPlacement:
    """One decal to build.

    Carries the surface frame it was placed on (center/normal/base axes) rather
    than just a finished matrix, because the generated object stores that frame
    and recomposes its matrix from it every time a setting is dragged - see
    object_settings.rebuild(). compose_matrix() is the single place that turns a
    frame plus settings into a world matrix, shared by creation and rebuild.
    """

    __slots__ = ("center", "normal", "base_x", "base_y", "rotation",
                 "offset_u", "offset_v", "surface_offset", "extent", "face_index",
                 "width", "height", "texture_stem", "texture_path")

    def __init__(self, center, normal, base_x, base_y, rotation, offset_u, offset_v,
                 surface_offset, extent, face_index, width, height,
                 texture_stem, texture_path):
        self.face_index = face_index
        self.center = center
        self.normal = normal
        self.base_x = base_x
        self.base_y = base_y
        self.rotation = rotation
        self.offset_u = offset_u
        self.offset_v = offset_v
        self.surface_offset = surface_offset
        self.extent = extent
        self.width = width
        self.height = height
        self.texture_stem = texture_stem
        self.texture_path = texture_path

    @property
    def matrix(self):
        return compose_matrix(self.center, self.normal, self.base_x, self.base_y,
                              self.rotation, self.offset_u, self.offset_v,
                              self.surface_offset)


def fallback_axis(normal):
    """An arbitrary unit vector perpendicular to `normal`, for the cases where
    the preferred reference direction collapses. Never returns a zero vector."""
    for reference in (Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0))):
        axis = normal.cross(reference)
        if axis.length > _EPS:
            return axis.normalized()
    return Vector((1.0, 0.0, 0.0))


def _are_coplanar(a, b):
    """True if two faces lie in the same plane, facing the same way.

    Tested in local space on purpose: an affine transform maps planes to planes,
    so coplanarity survives translation, rotation and scale - there is nothing to
    gain by transforming first.
    """
    if a.normal.dot(b.normal) < COPLANAR_NORMAL_TOLERANCE:
        return False
    offset = b.calc_center_median() - a.calc_center_median()
    return abs(offset.dot(a.normal)) < COPLANAR_DISTANCE_TOLERANCE


def group_coplanar_faces(faces):
    """Group `faces` into islands of touching, coplanar faces.

    A wall split into several quads reads as one flat surface to the eye, so it
    should take one decal rather than one per quad. Faces only join when they
    actually share an edge - two separate walls that happen to be in the same
    plane stay separate.

    Returns a list of face lists, each in the input order.
    """
    remaining = set(faces)
    islands = []

    for face in faces:
        if face not in remaining:
            continue
        remaining.discard(face)
        island = [face]
        queue = [face]
        while queue:
            current = queue.pop()
            for edge in current.edges:
                for neighbour in edge.link_faces:
                    if neighbour in remaining and _are_coplanar(current, neighbour):
                        remaining.discard(neighbour)
                        island.append(neighbour)
                        queue.append(neighbour)
        islands.append(island)

    return islands


def sample_faces(bm, matrix_world, merge_coplanar=True):
    """Read the selected faces of `bm` into world-space FaceSamples.

    With `merge_coplanar`, touching faces in the same plane are treated as one
    surface and produce a single sample - so selecting the two halves of a split
    wall gives one decal centred on the whole wall, not one per half.

    Read-only: no bmesh element is modified and bmesh.update_edit_mesh() is
    never called, so the source mesh cannot be touched by this tool.

    Returns (samples, skipped_degenerate).
    """
    linear = matrix_world.to_3x3()                              # direction vectors
    normal_matrix = matrix_world.inverted_safe().transposed().to_3x3()   # normals

    selected = []
    skipped = 0
    for face in bm.faces:
        if not face.select:
            continue
        if face.calc_area() < MIN_FACE_AREA:
            skipped += 1
            continue
        selected.append(face)

    islands = group_coplanar_faces(selected) if merge_coplanar else [[f] for f in selected]

    samples = []
    for island in islands:
        # Area-weighted, so a surface split into uneven pieces still centres on
        # the middle of the whole thing rather than drifting towards wherever
        # the small pieces are.
        total_area = 0.0
        local_center = Vector((0.0, 0.0, 0.0))
        local_normal = Vector((0.0, 0.0, 0.0))
        for face in island:
            area = face.calc_area()
            total_area += area
            local_center += face.calc_center_median() * area
            local_normal += face.normal * area

        if total_area <= MIN_FACE_AREA:
            skipped += len(island)
            continue
        local_center /= total_area

        normal = normal_matrix @ local_normal
        if normal.length <= _EPS:
            skipped += len(island)
            continue
        normal.normalize()

        center = matrix_world @ local_center

        # The representative face: the one the island's centre actually falls
        # in, as far as picking by proximity gets us. It is what the live
        # surface walk starts from, and what supplies the edge tangent.
        anchor = min(island, key=lambda f: (f.calc_center_median() - local_center).length_squared)
        # calc_tangent_edge_pair is a direction lying in the face, so it goes
        # through the linear part - NOT the normal matrix.
        tangent = linear @ anchor.calc_tangent_edge_pair()

        # Every corner of the island, so Random Position can use the whole
        # merged surface rather than just one of its pieces.
        seen = set()
        verts = []
        for face in island:
            for vert in face.verts:
                if vert.index not in seen:
                    seen.add(vert.index)
                    verts.append(matrix_world @ vert.co.copy())

        samples.append(FaceSample(center, normal, tangent, verts, anchor.index))

    return samples, skipped


def surface_basis(normal, tangent):
    """Build a right-handed orthonormal basis (x, y, normal) lying on the surface.

    `y` (the decal's local "up") follows world Z projected onto the face plane, so
    wall and slanted decals look visually upright. Only when the face is within
    ~2.5 degrees of horizontal - a floor or ceiling, where "upright" means nothing -
    does it fall back to the face's own edge tangent.

    This is the *base* frame, with no Rotation applied. Rotation is applied in
    compose_matrix() instead, so that Offset U/V stay measured in a frame that
    does not move when the user drags Rotation - otherwise spinning a decal would
    also slide it across the surface.
    """
    if abs(normal.dot(WORLD_UP)) > UP_PARALLEL_THRESHOLD:
        # Project the world-space tangent back onto the plane perpendicular to
        # the normal: under non-uniform scale the transformed tangent is no
        # longer exactly in the face plane.
        y = tangent - normal * tangent.dot(normal)
        y = y.normalized() if y.length > _EPS else fallback_axis(normal)
    else:
        y = WORLD_UP - normal * normal.dot(WORLD_UP)
        y = y.normalized() if y.length > _EPS else fallback_axis(normal)

    x = y.cross(normal)
    x = x.normalized() if x.length > _EPS else fallback_axis(normal)
    # Re-derive y from the final x so the basis is exactly orthonormal even if
    # the projection above left a little drift.
    y = normal.cross(x).normalized()

    return x, y


def compose_matrix(center, normal, base_x, base_y, rotation, offset_u, offset_v,
                   surface_offset):
    """World matrix for a decal, from its surface frame plus its settings.

    The single source of truth for decal placement: both the create operator and
    the live rebuild call this, so a decal that is dragged in the panel lands
    exactly where creating it with the same values would have put it.

      * Offset U/V slide it across the surface, in the unrotated base frame.
      * Rotation spins it in place around the surface normal.
      * Surface Offset lifts it off the surface along that normal.
    """
    origin = center + base_x * offset_u + base_y * offset_v + normal * surface_offset

    if rotation:
        spin = Matrix.Rotation(rotation, 3, normal)
        x = (spin @ base_x).normalized()
        y = (spin @ base_y).normalized()
    else:
        x, y = base_x, base_y

    basis = Matrix((x, y, normal)).transposed().to_4x4()
    basis.translation = origin
    return basis


def face_extent(verts, center, base_x, base_y):
    """How far the face reaches from its center along the base axes.

    Returns (min_u, max_u, min_v, max_v), all relative to the face center, so
    (0, 0) is the center itself.
    """
    if not verts:
        return (0.0, 0.0, 0.0, 0.0)
    us = [(v - center).dot(base_x) for v in verts]
    vs = [(v - center).dot(base_y) for v in verts]
    return (min(us), max(us), min(vs), max(vs))


def random_offset(rng, extent, width, height):
    """A random spot on the face that still fits the whole decal inside it.

    The range is inset by half the decal size on each side. When the face is too
    small for that on an axis, the decal is centered on that axis instead of
    being pushed over the edge.
    """
    min_u, max_u, min_v, max_v = extent

    lo_u, hi_u = min_u + width * 0.5, max_u - width * 0.5
    lo_v, hi_v = min_v + height * 0.5, max_v - height * 0.5

    u = rng.uniform(lo_u, hi_u) if hi_u > lo_u else 0.0
    v = rng.uniform(lo_v, hi_v) if hi_v > lo_v else 0.0
    return u, v


def build_placement(sample, width, height, surface_offset, rotation,
                    texture_stem, texture_path, offset_u=0.0, offset_v=0.0,
                    rng=None, randomize_position=False):
    base_x, base_y = surface_basis(sample.normal, sample.tangent)
    extent = face_extent(sample.verts, sample.center, base_x, base_y)

    if randomize_position and rng is not None:
        offset_u, offset_v = random_offset(rng, extent, width, height)

    return DecalPlacement(
        center=sample.center,
        normal=sample.normal,
        base_x=base_x,
        base_y=base_y,
        rotation=rotation,
        offset_u=offset_u,
        offset_v=offset_v,
        surface_offset=surface_offset,
        extent=extent,
        face_index=sample.index,
        width=width,
        height=height,
        texture_stem=texture_stem,
        texture_path=texture_path,
    )


# The decal is a 4x4 grid of vertices - 9 quads - rather than a single one: an
# inner rectangle carrying the corner alphas, ringed by a border inset by
# `edge_fade` whose vertices are all alpha 0. That border is what dissolves the
# decal's rectangular outline into the wall; without it the quad ends on a hard
# straight edge no matter what the texture does.
_GRID = 4
_INNER_CORNERS = ((1, 1), (1, 2), (2, 2), (2, 1))   # BL, BR, TR, TL - matches CORNER_NAMES

# The border can never eat more than this fraction of the decal, so a fade wider
# than the decal itself blunts instead of turning the inner rectangle inside out.
_MAX_FADE_FRACTION = 0.49


def _grid_index(row, col):
    return row * _GRID + col


# Vertex counts and indices of the finished grid, so callers (and tests) can
# talk about "the inner corners" without re-deriving the layout.
GRID_VERTEX_COUNT = _GRID * _GRID
GRID_FACE_COUNT = (_GRID - 1) ** 2
INNER_CORNER_VERTS = tuple(_grid_index(row, col) for row, col in _INNER_CORNERS)


def decal_grid(width, height, edge_fade):
    """Vertices, faces, UVs and an is-border flag for one decal.

    Everything is in local space, centred on the origin - which is what puts the
    object origin at the centre of the decal for free, and lets the object keep a
    clean (1, 1, 1) scale even when random scaling is on.

    UVs run 0..1 across the *outer* boundary, so the texture is laid over the
    whole decal undistorted and the border simply fades the edge of it out.
    """
    half_w = width * 0.5
    half_h = height * 0.5
    fade_x = min(max(edge_fade, 0.0), width * _MAX_FADE_FRACTION)
    fade_y = min(max(edge_fade, 0.0), height * _MAX_FADE_FRACTION)

    xs = (-half_w, -half_w + fade_x, half_w - fade_x, half_w)
    ys = (-half_h, -half_h + fade_y, half_h - fade_y, half_h)

    verts, uvs, is_border = [], [], []
    for row in range(_GRID):
        for col in range(_GRID):
            x, y = xs[col], ys[row]
            verts.append((x, y, 0.0))
            uvs.append(((x + half_w) / width, (y + half_h) / height))
            is_border.append(row in (0, _GRID - 1) or col in (0, _GRID - 1))

    faces = []
    for row in range(_GRID - 1):
        for col in range(_GRID - 1):
            # Counter-clockwise seen from +Z, so every face normal points out of
            # the wall, same as the single quad this replaced.
            faces.append((
                _grid_index(row, col),
                _grid_index(row, col + 1),
                _grid_index(row + 1, col + 1),
                _grid_index(row + 1, col),
            ))

    return verts, faces, uvs, is_border


DEFAULT_BORDER_ALPHA = (0.0, 0.0, 0.0, 0.0)


def _side_alphas_for(row, col, border_alphas):
    """The border values that apply to one ring vertex.

    A vertex on the ring belongs to one side, or to two if it is a corner of the
    ring.
    """
    applicable = []
    if row == 0:
        applicable.append(border_alphas[0])              # bottom
    if col == _GRID - 1:
        applicable.append(border_alphas[1])              # right
    if row == _GRID - 1:
        applicable.append(border_alphas[2])              # top
    if col == 0:
        applicable.append(border_alphas[3])              # left
    return applicable


def vertex_alphas(is_border, corner_alphas, border_alphas=DEFAULT_BORDER_ALPHA):
    """Alpha per vertex: the corner values on the inner rectangle, the per-side
    values around the border ring.

    Where two sides meet, the ring corner takes the LOWER of the two. That way a
    side set to 0 is genuinely transparent along its whole length - if the corner
    took the higher value instead, a faded side sitting next to a hard one would
    stay opaque at its ends and the fade would look broken.
    """
    if isinstance(corner_alphas, (int, float)):
        corner_alphas = (float(corner_alphas),) * 4
    if isinstance(border_alphas, (int, float)):
        border_alphas = (float(border_alphas),) * 4

    alphas = [1.0] * len(is_border)
    for row in range(_GRID):
        for col in range(_GRID):
            index = _grid_index(row, col)
            if not is_border[index]:
                continue
            sides = _side_alphas_for(row, col, border_alphas)
            alphas[index] = min(sides) if sides else 0.0

    for index, (row, col) in enumerate(_INNER_CORNERS):
        alphas[_grid_index(row, col)] = corner_alphas[index]
    return alphas


def per_loop(faces, per_vertex):
    """Expand per-vertex values to per-loop, in the loop order from_pydata
    produces (faces in order, corners in the order they were given)."""
    return [per_vertex[index] for face in faces for index in face]


def build_decal_mesh(name, width, height, edge_fade):
    """The decal mesh: 16 vertices, 9 quads, shaded smooth."""
    import bpy

    verts, faces, _uvs, _is_border = decal_grid(width, height, edge_fade)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    mesh.update()
    return mesh


# ---------------------------------------------------------------- surface walk

# How many edges one drag may cross in a single update. A decal dragged fast
# across a detailed wall can cross several; the cap only exists so a pathological
# mesh cannot spin this forever.
MAX_WALK_STEPS = 24


def plane_axes(verts, normal):
    """An arbitrary orthonormal 2D frame lying in a face's plane."""
    ex = None
    for i in range(1, len(verts)):
        candidate = verts[i] - verts[0]
        candidate = candidate - normal * candidate.dot(normal)
        if candidate.length > _EPS:
            ex = candidate.normalized()
            break
    if ex is None:
        ex = fallback_axis(normal)
    return ex, normal.cross(ex).normalized()


def point_inside_polygon(polygon_2d, point):
    """Even-odd ray cast. `polygon_2d` is a list of 2D Vectors, in order."""
    inside = False
    count = len(polygon_2d)
    for i in range(count):
        a = polygon_2d[i]
        b = polygon_2d[(i + 1) % count]
        if (a.y > point.y) != (b.y > point.y):
            span = b.y - a.y
            if abs(span) > 1e-12:
                x = a.x + (point.y - a.y) / span * (b.x - a.x)
                if x > point.x:
                    inside = not inside
    return inside


def _segment_hit(origin, target, a, b):
    """Parameter t in (0, 1] where segment origin->target crosses segment a->b."""
    d = target - origin
    e = b - a
    denominator = d.x * e.y - d.y * e.x
    if abs(denominator) < 1e-12:
        return None                      # parallel
    diff = a - origin
    t = (diff.x * e.y - diff.y * e.x) / denominator
    u = (diff.x * d.y - diff.y * d.x) / denominator
    if t <= 1e-6 or t > 1.0 + 1e-9:
        return None                      # behind us, or past the target
    if u < -1e-6 or u > 1.0 + 1e-6:
        return None                      # misses the edge segment itself
    return t


def walk_across_faces(bm, matrix_world, face_index, target, max_steps=MAX_WALK_STEPS):
    """Slide from a face's center to `target`, stepping onto neighbouring faces.

    This is what stops a decal from hanging off into space when it is dragged
    past an edge: the travel that would leave the face is unfolded around that
    edge onto the neighbour, repeatedly, so the decal walks over the surface and
    turns corners instead of flying off them.

    Everything is in world space. Returns (face_index, world_point), or None if
    `face_index` is not in this mesh (the source was edited since).

    An open boundary edge stops the walk at the edge rather than continuing -
    there is no neighbour to step onto.
    """
    bm.faces.ensure_lookup_table()
    if face_index < 0 or face_index >= len(bm.faces):
        return None

    normal_matrix = matrix_world.inverted_safe().transposed().to_3x3()
    face = bm.faces[face_index]
    origin = matrix_world @ face.calc_center_median()

    for _ in range(max_steps):
        normal = (normal_matrix @ face.normal).normalized()
        verts = [matrix_world @ v.co.copy() for v in face.verts]
        center = matrix_world @ face.calc_center_median()
        ex, ey = plane_axes(verts, normal)

        def flatten(point):
            delta = point - center
            return Vector((delta.dot(ex), delta.dot(ey)))

        polygon = [flatten(v) for v in verts]
        target_2d = flatten(target)

        if point_inside_polygon(polygon, target_2d):
            return face.index, target

        origin_2d = flatten(origin)
        best_t = None
        best_loop = None
        count = len(polygon)
        for i, loop in enumerate(face.loops):
            t = _segment_hit(origin_2d, target_2d, polygon[i], polygon[(i + 1) % count])
            if t is not None and (best_t is None or t < best_t):
                best_t = t
                best_loop = loop

        if best_loop is None:
            # Numerically the target is neither inside nor past an edge (it can
            # sit exactly on one). Leaving it where it is beats guessing.
            return face.index, target

        crossing = origin + (target - origin) * best_t
        neighbour = next((f for f in best_loop.edge.link_faces if f is not face), None)
        if neighbour is None:
            return face.index, crossing

        next_normal = (normal_matrix @ neighbour.normal).normalized()
        # Unfold the rest of the travel around the shared edge. The minimal
        # rotation between two adjacent faces' normals turns about that shared
        # edge, which is exactly the fold we want.
        remainder = normal.rotation_difference(next_normal) @ (target - crossing)

        origin = crossing
        target = crossing + remainder
        face = neighbour

    return face.index, target


def face_frame(bm, matrix_world, face_index):
    """(center, normal, base_x, base_y, extent) for one face of `bm`, in world
    space - the same frame sample_faces()/build_placement() would produce."""
    bm.faces.ensure_lookup_table()
    if face_index < 0 or face_index >= len(bm.faces):
        return None

    linear = matrix_world.to_3x3()
    normal_matrix = matrix_world.inverted_safe().transposed().to_3x3()

    face = bm.faces[face_index]
    normal = (normal_matrix @ face.normal)
    if normal.length <= _EPS:
        return None
    normal.normalize()

    center = matrix_world @ face.calc_center_median()
    tangent = linear @ face.calc_tangent_edge_pair()
    base_x, base_y = surface_basis(normal, tangent)
    verts = [matrix_world @ v.co.copy() for v in face.verts]
    return center, normal, base_x, base_y, face_extent(verts, center, base_x, base_y)


def set_decal_size(mesh, width, height, edge_fade, uv_attr_name=None):
    """Resize an existing decal in place, border and all.

    Moves sixteen vertices and, because the border inset moves with them,
    rewrites the UVs to match - the mesh keeps its Color 1 attribute and its
    material, so nothing has to be rebuilt or reassigned and no live edit can
    leave a decal without a texture. Returns False if `mesh` is not one of ours.
    """
    verts, faces, uvs, _is_border = decal_grid(width, height, edge_fade)
    if len(mesh.vertices) != len(verts):
        return False

    for vertex, position in zip(mesh.vertices, verts):
        vertex.co = position

    if uv_attr_name:
        attr = mesh.attributes.get(uv_attr_name)
        if attr is not None and len(attr.data) == len(faces) * 4:
            for element, uv in zip(attr.data, per_loop(faces, uvs)):
                element.vector = uv

    mesh.update()
    return True


def decal_loop_uv(width, height, edge_fade):
    """Per-loop UVs for build_decal_mesh's grid, in loop order."""
    _verts, faces, uvs, _is_border = decal_grid(width, height, edge_fade)
    return [list(uv) for uv in per_loop(faces, uvs)]


# One alpha per corner, in the same order as _CORNER_SIGNS and QUAD_UVS - which
# is also the loop order of the single quad build_quad_mesh() produces.
CORNER_NAMES = ("Bottom Left", "Bottom Right", "Top Right", "Top Left")

# Border ring sides, in the same counter-clockwise order the corners use.
SIDE_NAMES = ("Bottom", "Right", "Top", "Left")

UNIFORM_ALPHA = (vertex_color.DEFAULT_ALPHA_CENTER,) * 4


def decal_loop_color(width, height, edge_fade, alphas=UNIFORM_ALPHA,
                     border_alphas=DEFAULT_BORDER_ALPHA,
                     rgb=vertex_color.DEFAULT_RGB):
    """Per-loop Color 1 values, one alpha per corner.

    Sollumz wires decal.sps as `alpha = Color 1 alpha * texture alpha`, so these
    are multipliers on top of the texture's own transparency: 1.0 is as opaque as
    the texture allows, and lower values fade that corner out. Because Blender
    interpolates the colour attribute across the face, four corner values give
    any linear gradient across the decal - top to bottom, side to side, or
    diagonally - while the quad stays four vertices.

    Accepts a single float too, for a flat alpha across the whole decal.
    """
    _verts, faces, _uvs, is_border = decal_grid(width, height, edge_fade)
    per_vertex = vertex_alphas(is_border, alphas, border_alphas)
    return [[rgb[0], rgb[1], rgb[2], a] for a in per_loop(faces, per_vertex)]


def set_decal_alpha(mesh, width, height, edge_fade, alphas, color_attr_name,
                    border_alphas=DEFAULT_BORDER_ALPHA):
    """Rewrite a decal's per-vertex alpha in place.

    The inner rectangle takes the four corner values and the border ring takes the
    four per-side values, so both sets are always rewritten together and neither
    can drift. No mesh rebuild: the UVs, the material and the geometry are
    untouched. Returns False if the attribute is missing, not the expected type,
    or the mesh is not the grid these values are indexed against.
    """
    attr = mesh.attributes.get(color_attr_name)
    if attr is None or attr.data_type != 'BYTE_COLOR':
        return False

    _verts, faces, _uvs, is_border = decal_grid(width, height, edge_fade)
    loop_alphas = per_loop(faces, vertex_alphas(is_border, alphas, border_alphas))
    if len(attr.data) != len(loop_alphas):
        return False

    for element, alpha in zip(attr.data, loop_alphas):
        colour = list(element.color_srgb)
        colour[3] = alpha
        element.color_srgb = colour
    mesh.update()
    return True


def random_rotation(rng, minimum, maximum):
    lo, hi = (minimum, maximum) if minimum <= maximum else (maximum, minimum)
    return rng.uniform(lo, hi)


def random_scale(rng, minimum, maximum):
    lo, hi = (minimum, maximum) if minimum <= maximum else (maximum, minimum)
    return rng.uniform(lo, hi)


def is_orthonormal(matrix, tolerance=1e-5):
    """True if the matrix's 3x3 part is a right-handed orthonormal basis.

    Only used by the test/verification pass, but kept next to the math it checks.
    """
    m = matrix.to_3x3()
    x, y, z = m.col[0], m.col[1], m.col[2]
    for axis in (x, y, z):
        if abs(axis.length - 1.0) > tolerance:
            return False
    if abs(x.dot(y)) > tolerance or abs(x.dot(z)) > tolerance or abs(y.dot(z)) > tolerance:
        return False
    return abs(m.determinant() - 1.0) <= tolerance
