# Ambient Occlusion

**Surface → Ambient Occlusion**

The soft dark line where two surfaces meet. Select the corner edges, press
Create, and a strip is built along them carrying an AO gradient that fades from
the corner out onto each wall.

It is one strip with a **wing on each wall**: at a true architectural corner
the edge is shared by two faces, so the strip wraps onto both. An edge with
only one adjacent face — a door frame, an open boundary — gets a single wing.

## Making one

1. Select the object, enter **Edit Mode**, switch to edge select, and select
   the corner edges.
2. Back in the tool panel, leave **Build From** on *Selection*.
3. Press **Create Ambient Occlusion**.

Everything else is tuned afterwards, on the strip itself.

## Build From

**Selection** — the strip runs along the edges you selected.

**Ground Level** — the strip runs along the contour where the mesh crosses a
**world height**, with no Edit Mode and no selection at all. This is the answer
for an object sunk into the floor, where the line you want is not an edge in
the mesh: a wall that continues below the floor has no edge at floor level to
select.

Ground Level is live on the finished strip too, so the height is a slider you
can drag and watch. It is also the simplest way to lift a strip vertically,
since it survives every rebuild by construction.

!!! note "Nothing crosses that height"

    An object standing *on* the height rather than sunk through it is coplanar
    with it, and coplanar surfaces never cross. The tool lifts the plane by a
    2 mm contact tolerance, takes the footprint, and drops the result back down
    by the same amount — so a resting object gives its exact footprint. If it
    still finds nothing, the panel says which of the three cases it is: the
    object is entirely below the height, entirely above it, or flat at it.

## Selected Strip

Every row here rebuilds the strip as you drag it.

### Shape

| Setting | Does |
| --- | --- |
| **Width** | how far the AO reaches out onto each wall. This is the shelf the gradient fades across — 0.25 m by default, much wider than the other strip tools |
| **Surface Offset** | lift off the wall, so the decal does not z-fight. Capped at 0.05 m |
| **Flip Direction** | which side of the edge the strip is built on |
| **Ground Level** | only on a Ground Level strip: the height the contour is cut at |

### Fade

**Across** the shelf first — **Alpha Center** at the corner, **Alpha Outer**
where it meets the wall, and **Invert Fade** to swap them.

**Along** the run second — **Alpha Bottom** and **Alpha Top**, so a corner that
runs floor to ceiling does not have to arrive at either at full strength. Both
at 1.0 is a no-op, not a flattening.

Bottom and top mean the bottom and top of the *building*, not of the object's
axes: a wall whose object happens to be rotated still fades toward the actual
floor. A run with no height — a wall-to-floor edge, all at one level — has
nothing to fade between and is left alone rather than having its shelf faded.

!!! tip "The fade is linear, and that is a geometry limit"

    A run built from **one** selected edge has two vertices along its length,
    and two vertices cannot describe a curve. Subdivide the source edge for a
    tighter falloff — the same as everywhere else in these tools.

### Position and Bevel

Shared with the other strip tools — see
[the tab](../the-tab.md#position-and-pinning).

## What it builds

- a strip mesh with a wing per adjacent wall, mitred where wings from different
  edges meet on the same wall
- `UVMap 0` fitted to the 0–1 square, upright, and `Color 1` carrying the fade
- a `seto_fakeao` material on `decal.sps`, reused per texture unless you ask
  for a new one
- filed into the `fake_ao` collection, or the source's Drawable collection when
  it has one
