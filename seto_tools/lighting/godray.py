"""Opening analysis and the frame maths behind a god ray.

Pure mathutils/bmesh: nothing here touches bpy.data, bpy.ops or Sollumz, which
is what makes it testable headless and reusable by Multi Ray mode later.

The job of this module is to turn "some selected faces" into an OpeningFrame -
an orthonormal description of the hole light comes through - and then to derive
from that frame the two things the rest of the tool needs:

  * a world matrix for the spot light, aimed through the opening
  * the four corners, direction and centre of a light shaft, in the archetype
    asset's local space

COORDINATE SPACES, because getting these wrong is the whole difficulty:

  source local   the mesh being read (bmesh vertex coordinates)
  world          everything OpeningFrame stores
  asset local    what a light shaft extension stores (corners, direction,
                 offset_position), relative to archetype.asset

No global-axis assumption is made anywhere - a window rotated arbitrarily in
world space produces the same quality of frame as an axis-aligned one. The only
place a world axis appears is picking which in-plane direction counts as "up",
and that has an explicit degenerate-case fallback for horizontal openings such
as a hole in a ceiling.

LIGHT SHAFT CORNER CONVENTION, read from Sollumz rather than guessed. Its gizmo
(ytyp/gizmos/extensions.py) computes `width = (B - A).length` and
`height = (D - A).length`, and seeds a new shaft with
A=(-s,0,+s) B=(+s,0,+s) C=(+s,0,-s) D=(-s,0,-s). So:

    A ---- B      A->B spans the width, A->D spans the height,
    |      |      and the quad winds A B C D around the opening.
    D ---- C

The shaft body extends along `direction` for `length`; the gizmo maps that with
direction.to_track_quat("Y", "Z"), i.e. the shaft's own forward axis is +Y.
"""

from dataclasses import dataclass

from mathutils import Matrix, Vector

# Below this, a vector is treated as having no usable direction.
EPSILON = 1e-6

# An opening whose plane is within this of horizontal has no meaningful "up"
# derived from world Z, so a fallback axis is used instead.
_UP_DEGENERATE = 1e-4


@dataclass
class OpeningFrame:
    """An opening (window, gap, doorway), described in WORLD space.

    `normal` points the way the light travels - out of the opening and into the
    room being lit. `right`/`up` span the opening plane and, with `normal`, form
    a right-handed orthonormal basis (right x up == normal).
    """

    center: Vector
    normal: Vector
    right: Vector
    up: Vector
    width: float
    height: float
    corners: tuple  # (A, B, C, D) world-space, see module docstring

    @property
    def basis(self):
        """3x3 rotation whose columns are (right, up, normal)."""
        mat = Matrix.Identity(3)
        mat.col[0] = self.right
        mat.col[1] = self.up
        mat.col[2] = self.normal
        return mat


class OpeningError(Exception):
    """The selection cannot be turned into an opening."""


def _pick_up_vector(normal):
    """An in-plane "up" for a plane with this normal.

    World Z projected onto the plane, which is what makes a window's height run
    vertically the way an artist expects. For a near-horizontal opening (ceiling
    hole, floor grate) that projection collapses, so world Y is projected
    instead - any consistent in-plane axis will do there, since "up" is
    meaningless for a horizontal hole.

    Only a reference for *orienting* the rectangle found by
    _min_area_rect_axes; it is not the rectangle's axis itself.
    """
    for axis in (Vector((0.0, 0.0, 1.0)), Vector((0.0, 1.0, 0.0))):
        up = axis - normal * axis.dot(normal)
        if up.length > _UP_DEGENERATE:
            return up.normalized()
    # Unreachable for a unit normal, but never return a zero vector.
    return Vector((0.0, 1.0, 0.0))


def _convex_hull_2d(points):
    """Convex hull of 2D points, counter-clockwise (Andrew's monotone chain)."""
    pts = sorted({(round(p.x, 9), round(p.y, 9)) for p in points})
    if len(pts) < 3:
        return [Vector(p) for p in pts]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [Vector(p) for p in lower[:-1] + upper[:-1]]


def _min_area_rect_axes(points2d):
    """In-plane axes of the smallest rectangle enclosing `points2d`.

    Returns (axis_x, axis_y) as 2D unit vectors, or None when the points are
    degenerate.

    This is what makes a *tilted* window measure correctly. Taking world Z as
    the rectangle's up axis would bound a rotated opening with an axis-aligned
    box, inflating both width and height and handing the light shaft corners
    that are visibly larger than the real gap - the beams would not line up with
    the boards they are supposed to come through.

    The minimum-area enclosing rectangle always has one side collinear with a
    hull edge, so testing every hull edge is exact rather than an approximation.
    Openings have a handful of vertices, so the cost is irrelevant.
    """
    hull = _convex_hull_2d(points2d)
    if len(hull) < 3:
        return None

    best = None
    for i in range(len(hull)):
        edge = hull[(i + 1) % len(hull)] - hull[i]
        if edge.length <= EPSILON:
            continue
        ex = edge.normalized()
        ey = Vector((-ex.y, ex.x))
        us = [p.dot(ex) for p in hull]
        vs = [p.dot(ey) for p in hull]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0] - EPSILON:
            best = (area, ex, ey)

    if best is None:
        return None
    return best[1], best[2]


def _normal_matrix(matrix_world):
    """The matrix that transforms normals, i.e. the inverse transpose.

    Using the object matrix directly would skew normals off the surface under
    non-uniform scale, which is exactly the case this tool must survive.
    """
    return matrix_world.inverted_safe().transposed().to_3x3()


def selected_faces(bm):
    return [f for f in bm.faces if f.select]


def face_islands(faces):
    """Split `faces` into groups that are connected through shared edges.

    This is what Multi Ray mode is built on: sunlight through a boarded-up
    window is not one opening but several narrow gaps between the boards, and
    each gap is its own island of selected faces. One island becomes one beam.

    Plain union-find over the faces' shared edges - no bmesh walking, so it
    behaves the same whatever order the selection was made in.
    """
    index_of = {face: i for i, face in enumerate(faces)}
    parent = list(range(len(faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for face in faces:
        for edge in face.edges:
            for other in edge.link_faces:
                if other is not face and other in index_of:
                    union(index_of[face], index_of[other])

    groups = {}
    for face in faces:
        groups.setdefault(find(index_of[face]), []).append(face)
    return list(groups.values())


def analyze_faces(bm, matrix_world, flip=False):
    """Build a single OpeningFrame from every selected face of `bm`."""
    faces = selected_faces(bm)
    if not faces:
        raise OpeningError("No faces selected. Select the window, gap or opening first.")
    return analyze_face_group(faces, matrix_world, flip=flip)


def analyze_islands(bm, matrix_world, flip=False):
    """One OpeningFrame per connected island of selected faces.

    Returns (frames, skipped) where `skipped` holds the reason each unusable
    island was dropped. An island that cannot describe an opening - a single
    degenerate face, say - must not abort the whole run when the other twelve
    gaps are fine.
    """
    faces = selected_faces(bm)
    if not faces:
        raise OpeningError("No faces selected. Select the window, gap or opening first.")

    frames, skipped = [], []
    for island in face_islands(faces):
        try:
            frames.append(analyze_face_group(island, matrix_world, flip=flip))
        except OpeningError as e:
            skipped.append(str(e))
    if not frames:
        raise OpeningError(
            "None of the selected islands describe a usable opening. "
            + (skipped[0] if skipped else "")
        )
    return frames, skipped


def analyze_face_group(faces, matrix_world, flip=False):
    """Build an OpeningFrame from an explicit list of faces.

    `matrix_world` is the source object's, so the result is in world space and
    stays valid after leaving Edit Mode. `flip` reverses the direction the light
    travels, for when the faces point away from the room to be lit.

    Raises OpeningError, with a message meant for the user, when the faces
    cannot describe an opening.
    """
    if not faces:
        raise OpeningError("No faces selected. Select the window, gap or opening first.")

    nmat = _normal_matrix(matrix_world)

    # Area-weighted so a few stray tiny faces cannot tilt the frame, and so a
    # multi-face opening is dominated by its main plane.
    normal = Vector((0.0, 0.0, 0.0))
    for face in faces:
        normal += (nmat @ face.normal) * face.calc_area()

    if normal.length <= EPSILON:
        raise OpeningError(
            "The selected faces cancel each other out - they face opposite ways, so there "
            "is no single direction for the light. Select faces on one side of the opening."
        )
    normal.normalize()
    if flip:
        normal = -normal

    verts = {v for face in faces for v in face.verts}
    if len(verts) < 3:
        raise OpeningError("The selection is too small to measure an opening.")

    points = [matrix_world @ v.co for v in verts]
    center = sum(points, Vector()) / len(points)

    # A provisional in-plane basis, used only to flatten the points to 2D and
    # to decide afterwards which of the rectangle's two axes counts as "up".
    ref_up = _pick_up_vector(normal)
    ref_right = ref_up.cross(normal)

    flat = [Vector(((p - center).dot(ref_right), (p - center).dot(ref_up))) for p in points]
    axes = _min_area_rect_axes(flat)
    if axes is None:
        right, up = ref_right, ref_up
    else:
        ax, ay = axes
        # Back to 3D.
        a3 = (ref_right * ax.x + ref_up * ax.y).normalized()
        b3 = (ref_right * ay.x + ref_up * ay.y).normalized()
        # Of the rectangle's two axes, the one closer to world up becomes "up",
        # so a window's height still runs vertically and the corner letters mean
        # what the Sollumz gizmo expects.
        if abs(b3.dot(ref_up)) >= abs(a3.dot(ref_up)):
            up = b3 if b3.dot(ref_up) >= 0.0 else -b3
        else:
            up = a3 if a3.dot(ref_up) >= 0.0 else -a3
        right = up.cross(normal)  # keeps right x up == normal (right-handed)

    # Extents measured from the centre, so the rectangle is the true in-plane
    # bounding box rather than something assumed to be centred.
    us = [(p - center).dot(right) for p in points]
    vs = [(p - center).dot(up) for p in points]
    umin, umax = min(us), max(us)
    vmin, vmax = min(vs), max(vs)

    width = umax - umin
    height = vmax - vmin
    if width <= EPSILON or height <= EPSILON:
        raise OpeningError(
            "The selected faces form a line rather than an area, so the opening has no "
            "width or height."
        )

    corners = (
        center + right * umin + up * vmax,  # A  top-left
        center + right * umax + up * vmax,  # B  top-right
        center + right * umax + up * vmin,  # C  bottom-right
        center + right * umin + up * vmin,  # D  bottom-left
    )

    return OpeningFrame(
        center=center,
        normal=normal,
        right=right,
        up=up,
        width=width,
        height=height,
        corners=corners,
    )


def suggest_flip(frame, reference_point):
    """True if `frame`'s normal points away from `reference_point`.

    Used to guess which side of a wall the room is on: the drawable's own centre
    is a decent stand-in for "inside", so a normal pointing away from it is
    pointing out of the building and should be flipped. Only ever a default -
    the operator exposes an explicit toggle, because a selection on an interior
    wall face legitimately points either way.
    """
    to_reference = reference_point - frame.center
    if to_reference.length <= EPSILON:
        return False
    return frame.normal.dot(to_reference) < 0.0


def light_matrix(frame, offset=0.0):
    """World matrix for a spot light shining through `frame`.

    Blender spot lights emit along their local -Z, and `frame.normal` is the
    direction the light travels, so -Z is put ON the normal (+Z on its
    opposite). Getting this backwards would leave the spot light and the light
    shaft pointing opposite ways - the light into the room, the shaft out of it.

    The roll follows the opening's own axes rather than being arbitrary, so an
    elliptical cone lines up with a rectangular window. -X is used for the local
    X axis to keep the basis right-handed once Z is negated: (-right) x up
    equals -normal.

    `offset` slides the light along the beam - positive further into the room,
    negative back outside the opening.
    """
    mat = Matrix.Identity(3)
    mat.col[0] = -frame.right
    mat.col[1] = frame.up
    mat.col[2] = -frame.normal
    mat = mat.to_4x4()
    mat.translation = frame.center + frame.normal * offset
    return mat


def aim_matrix(from_location, target, up_hint=None):
    """World matrix at `from_location` whose -Z axis points at `target`.

    Used by Aim At Selected. Roll is resolved with `to_track_quat`, so the
    result is stable and does not depend on the light's previous orientation.
    Returns None when the target coincides with the light, which would leave the
    aim undefined.
    """
    direction = target - from_location
    if direction.length <= EPSILON:
        return None
    # "-Z" tracks the aim; "Y" keeps the light's up as close to world up as the
    # aim allows, the same convention Blender's own Track To uses.
    quat = direction.to_track_quat("-Z", "Y")
    mat = quat.to_matrix().to_4x4()
    mat.translation = from_location
    return mat


# ------------------------------------------------------------------ asset space


def world_point_to_asset(asset_matrix_world, point):
    return asset_matrix_world.inverted_safe() @ point


def world_direction_to_asset(asset_matrix_world, direction):
    """Transform a direction into asset-local space and re-normalize.

    Directions use the inverse of the 3x3 part only, so the asset's translation
    is ignored; re-normalizing afterwards keeps the result unit-length under
    scaled assets.
    """
    local = asset_matrix_world.inverted_safe().to_3x3() @ direction
    if local.length <= EPSILON:
        return Vector((0.0, 1.0, 0.0))
    return local.normalized()


@dataclass
class ShaftPlacement:
    """Everything a light shaft extension needs, in ASSET-LOCAL space."""

    cornerA: Vector
    cornerB: Vector
    cornerC: Vector
    cornerD: Vector
    direction: Vector
    offset_position: Vector

    @property
    def corners(self):
        return (self.cornerA, self.cornerB, self.cornerC, self.cornerD)


def shaft_placement(frame, asset_matrix_world, direction_world=None):
    """Convert an OpeningFrame into asset-local light shaft placement.

    `direction_world` overrides the direction the shaft travels, which is how
    Sync Light Shaft feeds the spot light's actual aim back in after the artist
    has rotated it; by default the shaft follows the opening's own normal.

    offset_position is the mean of the four corners - the same value Sollumz's
    own "Calculate Center Offset location" operator produces - so a shaft built
    here and one built by hand in Sollumz agree.

    NOTE: Sollumz's own Update Lightshaft Direction operator computes its
    direction in world space and stores it without converting, which only
    matches the gizmo when the asset sits at the origin unrotated. This does the
    conversion, so a rotated or moved drawable stays correct.
    """
    inv = asset_matrix_world.inverted_safe()
    a, b, c, d = (inv @ corner for corner in frame.corners)
    direction = world_direction_to_asset(
        asset_matrix_world,
        frame.normal if direction_world is None else direction_world,
    )
    return ShaftPlacement(
        cornerA=a,
        cornerB=b,
        cornerC=c,
        cornerD=d,
        direction=direction,
        offset_position=(a + b + c + d) / 4.0,
    )


def dust_position(frame, asset_matrix_world, distance):
    """Asset-local position for the dust particle effect.

    Placed inside the room, along the beam, rather than in the plane of the
    opening: motes are only visible where the beam has something to travel
    through. Half the beam length is a reasonable middle of the visible shaft.
    """
    world = frame.center + frame.normal * distance
    return world_point_to_asset(asset_matrix_world, world)


def cone_angle_for_opening(frame, beam_length, minimum, maximum):
    """A cone half-angle that roughly covers the opening at `beam_length`.

    Derived from the opening's own size so a narrow gap between boards gets a
    narrow beam and a doorway gets a wide one, then clamped to the caller's
    range - Sollumz caps the GTA cone half-angle at 90 degrees, and this must
    never try to exceed it.
    """
    from math import atan2

    if beam_length <= EPSILON:
        return minimum
    half_extent = max(frame.width, frame.height) * 0.5
    angle = atan2(half_extent, beam_length)
    return max(minimum, min(maximum, angle))
