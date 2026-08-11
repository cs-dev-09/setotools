# Edge Wear

**Geometry → Edge Wear**

Chipped, worn edges — the paint knocked off a kerb, plaster broken away from a
corner. Select the edges, press Create, and a narrow strip is built along them
carrying a damage texture.

Edge Wear and [Smooth Edge](smooth-edge.md) build the **same strip** and differ
only in the texture on it. That is why they share their shape settings, drawn
once in the **Geometry** section header rather than twice: having both list the
same seven rows was reported as the same panel appearing twice.

## Making one

1. Select the object, enter **Edit Mode**, edge select, pick the edges.
2. Set the strip's shape in the **Geometry** section, if you want something
   other than the defaults.
3. Press **Create Edge Wear**.

## Selected Strip

### Shape

| Setting | Does |
| --- | --- |
| **Width** | how far the strip reaches onto each face — 0.04 m by default, a narrow band rather than Ambient Occlusion's shelf |
| **Surface Offset** | lift off the surface, avoiding z-fight |
| **Merge Distance** | how close two vertices have to be before they are welded |
| **Flip Direction** | which side of the edge the strip is built on |

### Fade

**Alpha Center** / **Alpha Outer** across the strip, **Invert Fade** to swap
them, then **Alpha Bottom** / **Alpha Top** along the run. See
[Ambient Occlusion's fade](ambient-occlusion.md#fade) — it is the same code and
the same reasoning.

### Texture Placement

**UV Scale** and **UV Offset**, for tiling the damage texture along the run.

!!! warning "These want re-tuning"

    The shipped defaults (3.5 and +0.3906) were dialled in against a texture
    that has since been replaced. If the wear looks stretched or badly placed
    on the current texture, these two are the reason — and reporting what
    values work is genuinely useful.

### Position and Bevel

Shared with the other strip tools — see
[the tab](../the-tab.md#position-and-pinning).

## What it builds

- a narrow strip along the selected edges, welded at the corners
- `UVMap 0` and `Color 1`, the shared green with the alpha fade
- a `seto_fakedamage` material — the same shader Smooth Edge uses, which is
  exactly why materials are matched by name and not by shader
- filed into the `fake_dmg` collection, or the source's Drawable collection
