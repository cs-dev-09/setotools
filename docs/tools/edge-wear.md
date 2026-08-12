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

### Material

**Strength** — how loudly the wear reads in game. One slider driving the two
shader values that decide it:

| Strength | `bumpiness` | `specularIntensityMult` | |
| --- | --- | --- | --- |
| 1.0 | 0.50 | 0.125 | what GTA's own damage strips use |
| 2.0 | 1.00 | 0.250 | |
| **4.0** | **2.00** | **0.500** | **the shipped default** |

Both values are printed under the slider, so they can be compared against a
vanilla material or quoted in a bug report.

**The default is 4.0, not GTA's 1.0.** At the reference values a strip reads
too faintly on a softly lit interior wall, which is where this tool is mostly
used — so it ships louder, and 1.0 is one drag away for anything meant to sit
exactly where vanilla sits.

`specularIntensityMult` is the one that matters. `decal_normal_only` carries no
colour of its own — it only bends the surface normal — so the crease is visible
only through the light's specular answer to that bend. Set it to `0` and the
strip is very nearly invisible on a softly lit interior wall, however strong the
normal map is and however high `bumpiness` goes. That is the single commonest
cause of "the damage does not show up in game".

The other three shader values stay where GTA has them (`specularFalloffMult`
100, `specularFresnel` 0.97, `useTessellation` off). Strength is the effect's
volume, not its character.

Dragging Strength writes straight to the material and does **not** rebuild the
mesh — there is nothing in the geometry to regenerate.

!!! warning "It is a material value, not a strip value"

    Strips reuse one `seto_fakedamage` material by default, so a drag changes
    every strip wearing it — the panel says how many. And because a reused
    material is never rewritten, a new strip that adopts one shows *that
    material's* Strength rather than the panel's, and says so when it is
    created. Set **Material** to **Create** in the Geometry section for a strip
    with a Strength of its own.

The **Material** panel under Edge Wear holds the same slider for the *next*
strip; on an existing strip, use this one.

### Position and Bevel

Shared with the other strip tools — see
[the tab](../the-tab.md#position-and-pinning).

## What it builds

- a narrow strip along the selected edges, welded at the corners
- `UVMap 0` and `Color 1`, the shared green with the alpha fade
- a `seto_fakedamage` material — the same shader Smooth Edge uses, which is
  exactly why materials are matched by name and not by shader
- filed into the `fake_dmg` collection, or the source's Drawable collection
