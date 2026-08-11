# Edge Dirt

**Surface → Edge Dirt**

Dirt and grime streaked along an edge. It is
[Ambient Occlusion](ambient-occlusion.md)'s strip with a different texture on
it — the same geometry, the same live rebuild, the same fades — and it is a
separate tool for one reason: an AO shadow and a dirt streak are two strips on
the same wall, and they must be able to sit there at once without one
retexturing the other.

So Edge Dirt has its own settings, its own material, its own texture folder and
its own panel, while sharing the machinery that builds the strip.

## Making one

1. Select the object, enter **Edit Mode**, edge select, pick the edges.
2. Press **Create Edge Dirt**.

**Build From** offers *Selection* and *Ground Level*, exactly as Ambient
Occlusion does — see
[Build From](ambient-occlusion.md#build-from) for what Ground Level is for.

## The texture

Edge Dirt reads its own `textures/` folder inside the add-on and wires whatever
is there into the material automatically. The panel shows what it found.

There is no file picker on purpose: the texture travels with the add-on, so a
scene handed to someone else looks the same on their machine. Drop a different
file in that folder to change it.

## Selected Strip

Identical to [Ambient Occlusion's](ambient-occlusion.md#selected-strip): Width,
Surface Offset, Flip Direction, the across- and along-run fades, Position, and
Bevel. All live.

!!! info "Bevel Mesh works here now"

    Until recently Edge Dirt cut its source round into the mesh at creation,
    which works exactly once — the edge it rounded no longer existed
    afterwards, so the **Bevel Mesh** tick on the finished strip had nothing
    left to act on and did nothing at all.

    It drives the same live Bevel modifier the other three tools use now.
    Ticking it rounds the source, dragging Width follows, unticking removes the
    modifier and leaves the source exactly as it was found. The **Bevel
    target** dropdown that existed only to describe the old behaviour is gone.

## What it builds

- the same strip Ambient Occlusion builds
- `UVMap 0` and `Color 1`
- a `seto_edgedirt` material — separate from `seto_fakeao` on purpose, so
  retexturing the dirt cannot touch the AO
- filed into the `edge_dirt` collection, or the source's Drawable collection
