"""Turning a piece of lettering into a halo, as pure maths.

The chain is short and worth stating once, because none of the steps is
obvious from the code alone:

  1. **Pick a plane to look at the letters from.** The sign faces somewhere;
     the halo has to be square-on to that. The average face normal says which
     way, and the source object's own axes say how it is rolled - taking the
     basis from the object rather than inventing one is what makes the glow
     plane inherit the sign's rotation instead of arriving level in a world
     where nothing else is.
  2. **Rasterise the silhouette** into a mask: 1 where a letter covers the
     plane, 0 where it does not. Barycentric, per triangle, over that
     triangle's own bounding box only.
  3. **Blur it twice at two radii and add them.** A single blur is either a
     tight outline or a soft cloud; a real sign halo is both - a bright rim
     right at the letters and a wide bloom behind them. Three box passes
     approximate a Gaussian closely enough that nothing in the result betrays
     the difference, and a box blur is O(n) per pass where a true Gaussian is
     not: at 1024x1024 that is the difference between a live slider and a
     progress bar.

Nothing here touches `bpy.data` or Sollumz - it takes triangles and numbers and
returns arrays, which is what lets `tests/sign_glow.py` check the shape of the
halo without building anything.
"""

import numpy as np
from mathutils import Vector


def _box1d(values, radius, axis):
    """One box-blur pass along `axis`, via a cumulative sum (O(n), not O(n*r))."""
    if radius <= 0:
        return values
    length = values.shape[axis]
    padding = [(0, 0)] * values.ndim
    padding[axis] = (radius + 1, radius)
    # Edge padding, not zero padding: zeros would darken the border of the
    # image, and the border of this image is where the halo lives.
    running = np.cumsum(np.pad(values, padding, mode='edge'),
                        axis=axis, dtype=np.float64)
    high = [slice(None)] * values.ndim
    low = [slice(None)] * values.ndim
    high[axis] = slice(2 * radius + 1, 2 * radius + 1 + length)
    low[axis] = slice(0, length)
    window = 2 * radius + 1
    return ((running[tuple(high)] - running[tuple(low)]) / window).astype(np.float32)


def blur(values, radius):
    """Three box passes in each direction - a Gaussian, near enough."""
    for _ in range(3):
        values = _box1d(_box1d(values, radius, 0), radius, 1)
    return values


def projection_basis(normal_accumulator, source_matrix=None):
    """Return (forward, u, v): the frame the silhouette is projected onto.

    `normal_accumulator` is the area-weighted sum of the source's world normals -
    weighted because a sign is mostly its face, and counting a bevel's forty
    tiny side polygons equally with it would tilt the frame off the face.

    With a `source_matrix`, the frame is snapped to that object's own axes: the
    axis nearest the average normal becomes forward, the other two become u and
    v. The plane then carries the sign's exact rotation, and its transform gizmo
    lines up with the lettering - which is the difference between nudging the
    glow along the wall and nudging it diagonally through it.
    """
    normal = (normal_accumulator.normalized()
              if normal_accumulator.length > 1e-6 else Vector((0.0, -1.0, 0.0)))

    if source_matrix is not None:
        rotation = source_matrix.to_3x3().normalized()
        axes = [(rotation @ Vector((1.0, 0.0, 0.0))).normalized(),
                (rotation @ Vector((0.0, 1.0, 0.0))).normalized(),
                (rotation @ Vector((0.0, 0.0, 1.0))).normalized()]
        dots = [axis.dot(normal) for axis in axes]
        index = max(range(3), key=lambda k: abs(dots[k]))
        forward = axes[index] if dots[index] >= 0 else -axes[index]
        u = axes[(index + 1) % 3]
        v = axes[(index + 2) % 3]
        # Keep the frame right-handed, or the texture comes out mirrored.
        if u.cross(v).dot(forward) < 0:
            u = -u
        return forward, u, v

    up = Vector((0.0, 0.0, 1.0))
    if abs(normal.dot(up)) > 0.9:
        up = Vector((0.0, 1.0, 0.0))
    u = up.cross(normal).normalized()
    v = normal.cross(u).normalized()
    return normal, u, v


def rasterize(triangles, u, v, forward, resolution, padding_fraction):
    """Project world triangles onto (u, v) and fill the silhouette.

    Returns `(mask, bounds, nearest_depth)`:
      * `mask` - HxW float array, 1.0 inside the lettering,
      * `bounds` - (u0, v0, u1, v1), the padded extent in world units, which is
        how big the plane has to be,
      * `nearest_depth` - how far along `forward` the frontmost vertex sits, so
        the plane can be put *behind* the letters rather than through them.

    The long side gets `resolution` pixels and the short side is scaled to
    match, so the texture's pixels stay square whatever shape the sign is - a
    stretched pixel is a stretched halo.
    """
    projected = []
    nearest_depth = float('inf')
    for triangle in triangles:
        corners = []
        for point in triangle:
            corners.append((point.dot(u), point.dot(v)))
            nearest_depth = min(nearest_depth, point.dot(forward))
        projected.append(corners)

    xs = [c[0] for tri in projected for c in tri]
    ys = [c[1] for tri in projected for c in tri]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    # The pad is a fraction of the *larger* side, so a wide sign and a tall one
    # get the same margin in world units rather than the same proportion.
    pad = max(max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)) * padding_fraction
    x0 -= pad
    x1 += pad
    y0 -= pad
    y1 += pad
    width_span = x1 - x0
    height_span = y1 - y0

    if width_span >= height_span:
        width = int(resolution)
        height = max(8, int(round(resolution * height_span / width_span)))
    else:
        height = int(resolution)
        width = max(8, int(round(resolution * width_span / height_span)))

    mask = np.zeros((height, width), np.float32)
    scale_x = (width - 1) / width_span
    scale_y = (height - 1) / height_span

    for corners in projected:
        pixels = [((c[0] - x0) * scale_x, (c[1] - y0) * scale_y) for c in corners]
        bx0 = max(0, int(min(p[0] for p in pixels)))
        bx1 = min(width - 1, int(max(p[0] for p in pixels)) + 1)
        by0 = max(0, int(min(p[1] for p in pixels)))
        by1 = min(height - 1, int(max(p[1] for p in pixels)) + 1)
        if bx1 <= bx0 or by1 <= by0:
            continue
        grid_y, grid_x = np.mgrid[by0:by1 + 1, bx0:bx1 + 1]
        (ax, ay), (bx, by), (cx, cy) = pixels
        denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(denominator) < 1e-9:
            continue                      # degenerate on this plane: no area
        l1 = ((by - cy) * (grid_x - cx) + (cx - bx) * (grid_y - cy)) / denominator
        l2 = ((cy - ay) * (grid_x - cx) + (ax - cx) * (grid_y - cy)) / denominator
        l3 = 1.0 - l1 - l2
        # A hair of slack on the edges, or neighbouring triangles leave a
        # one-pixel seam between them that the blur then turns into a crease.
        inside = (l1 >= -1e-4) & (l2 >= -1e-4) & (l3 >= -1e-4)
        region = mask[by0:by1 + 1, bx0:bx1 + 1]
        region[inside] = 1.0

    return mask, (x0, y0, x1, y1), nearest_depth


def halo_from_mask(mask, core_size, core_intensity, halo_size, halo_intensity,
                   opacity, colour):
    """Blur the silhouette into an RGBA halo.

    The two sizes are fractions of the image's long side rather than pixels, so
    the halo looks the same at 256 as at 1024 - resolution stays a quality
    setting instead of secretly being a shape setting.

    Colour goes into RGB *and* the same value into alpha: the Sollumz emissive
    shaders read alpha as coverage, and the preview material blends by it, so
    the two have to agree or the viewport lies about what will be in game.
    """
    base = max(mask.shape)
    core_radius = max(1, int(base * core_size))
    halo_radius = max(2, int(base * halo_size))
    core = blur(mask, core_radius) * core_intensity
    wide = blur(mask, halo_radius) * halo_intensity
    value = np.clip(core + wide, 0.0, 1.0) * opacity
    rgb = value[..., None] * np.array(colour[:3], np.float32)[None, None, :]
    return np.concatenate([rgb, value[..., None]], axis=2).astype(np.float32)
