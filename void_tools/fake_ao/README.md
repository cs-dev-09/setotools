# Fake AO

Part of **Void Tools**, built on [Sollumz](https://docs.sollumz.org). Generates
fake ambient-occlusion decals for GTA V / FiveM assets. Select an edge, press a
button, get a ready-to-export corner decal — your original mesh is never touched.

Tools included:

- **Fake AO** — fake ambient-occlusion corner decals.

## Requirements

- Blender 4.2+
- Sollumz installed, enabled, with dependencies already set up.
- Any texture on hand to assign afterward (even a plain black one) — the
  generated material's texture slot is left empty on purpose, so the decal
  will look black/blank in the viewport until you assign one yourself.

## The texture

Drop an ambient-occlusion texture into:

```
void_tools/fake_ao/textures/
```

It is wired into `DiffuseSampler` for you, as sRGB (a colour texture, not a
normal map) and not embedded. The first usable image is used, `.dds` preferred;
a file named `fake_ao.*` wins if you want to pin one while keeping others
around.

**The file name matters.** Sollumz exports the texture name from it, so
`tl_v_office_shadow.dds` becomes the `tl_v_office_shadow` reference in the
`.ydr` — which then has to exist in the asset's TXD. Leaving the folder empty is
not an error: the strip and its material are still built, and the tool reports
that the slot was left for you.

## Install

1. Install `void-tools.zip` — this tool ships inside it.
2. Blender: **Edit > Preferences > Add-ons > Install from Disk** → pick the zip.
3. Enable it, then **restart Blender**.

## Usage

1. Select your mesh, enter **Edit Mode**, select one or more corner edges.
2. Open **N-Panel > Void Tools > Fake AO**, adjust settings if needed.
3. Press **Create Fake AO**.

A new `fake_ao_00N` object is created: wraps the corner (or lies flat
on one wall for a boundary edge like a door frame), gets UVs, a `decal.sps`
material, correct `Color 1` alpha for export, and its origin set to its
center — all automatically. Every strip is filed in a **`fake_ao`** collection,
created on first use, so they stay easy to hide, select and export as a group.

## Live settings

The strip keeps its own settings. Select it and the **Selected Strip** section
appears under Fake AO: drag **Width** and the mesh regenerates as you drag,
the feel of a Geometry Nodes modifier — except the result is real mesh data,
so nothing has to be applied before export.

It works because the strip remembers what it was made from: the source object,
the source-mesh vertex-index pairs of the selected edges, and the settings that
were used. Changing a setting re-reads those edges and rebuilds.

- **Live Update** — off freezes the strip; use **Rebuild Now** when you are done.
- Editing the **source** mesh's topology invalidates the stored edges. The
  panel says so rather than rebuilding something wrong.
- Right after creating, the settings are also in Blender's **Adjust Last
  Operation** (F9) panel.

The rebuild uses no operators at all — origin-to-geometry is done through the
data API — because Blender is not safe to call operators in from a property
callback mid-drag.

## UVs

**Straight by construction** — no Cube Projection, no unwrap, nothing to
straighten afterwards. Each wing's UVs are laid out from the wing itself, in
metres: `U` runs along the selected edge, `V` across the shelf. The island is
then fitted into the 0..1 square with **both axes scaled by the same factor**,
so a long thin shelf stays long and thin in UV space instead of being squashed
into a square; the long axis spans 1.5.

An arc, a 90° turn and a straight run therefore all give the same clean
rectangle — on a 16-segment curved rim the island measures **0.0 deviation**
from a perfect axis-aligned grid.

## Settings

- **Width** — how far the decal extends onto the wall. Keep it clear of Bevel
  Width; see below.
- **Surface Offset** — lift off the wall, avoids z-fighting. Capped at 0.05 m;
  past that the strip is not on the wall any more.
- **Alpha Center / Alpha Outer** — Color 1 alpha fade *across* the shelf,
  corner → edge.
- **Alpha Bottom / Alpha Top** — Color 1 alpha fade *along* the run, so a
  corner does not have to arrive at the floor or the ceiling at full strength.
  1.0 at both ends leaves the strip exactly as it was; anything lower scales
  what the across-fade produced, ramping back to full at the other end.

  Bottom and top are the **building's**, read out of the source's world matrix,
  so a wall whose object happens to be rotated still fades toward the real
  floor. Each vertex is placed by the selected-edge end it came from rather
  than by where it itself ended up — a wall-to-floor edge is all one height but
  its strip climbs the wall, and measuring the vertices would fade the top of
  the shelf and call it the top of the run. Such a run has no bottom or top to
  fade between and is left alone.

  The ramp is linear, because that is what the geometry can carry: a run built
  from one selected edge has two vertices along its length, and two vertices
  cannot describe a curve. Subdivide the source edge for a tighter falloff.
- **Invert Fade** — swap which side gets which alpha.
- **Flip Direction** — flips a single-wall wing to the other side.
- **Material** — reuse an existing `decal.sps` material, or always create new.

All of these stay editable on the created strip, not just at creation time.

## Bevel

A sharp corner still reads as sharp under the best AO there is, so **Bevel**
rounds it off for you — the strip's own seam *and* the source's corner, from one
set of controls, kept the same shape. Width, Segments and Profile Shape are
Blender's own bevel settings under their own names, and it is on by default at
**0.0833 m, 4 segments, profile 0.5**.

**It lives on the finished strip, not on the create panel.** There is nothing to
decide in advance: create the strip, then drag Width and watch both meshes
follow. Switching it off takes the round off both again.

Two different mechanisms, because the two meshes are different things:

- **The strip's seam** is beveled into its mesh, and rebuilt from scratch every
  time a setting changes — the strip is generated, so regenerating it is free.
- **The source's corner** is a **Bevel modifier** (`Seto AO Bevel`), limited by
  edge weight, with the weight set on the strip's own edges. Nothing about the
  source mesh is edited. That is what makes it live and reversible, and it is
  why the strip can go on pointing at the corner by vertex index — cutting the
  bevel in used to destroy the very edge the strip was built from.

  Sollumz exports the **evaluated** object (`ydrexport.py` → `get_evaluated_obj`
  → `to_mesh()`), so the round is baked into the YDR exactly as if it had been
  applied by hand.

The two rounds match by construction: the strip's is generated with the same
Width and Segments rather than by approximating the source's, and it lands
exactly Surface Offset outside it.

**One modifier per source object**, shared by every AO strip on it — which is
what a corner treatment is, a property of the wall rather than of the decal
running along it. Per-strip widths still work: with weight limiting the
modifier's width is scaled by each edge's own weight, so the modifier carries
the widest strip's width and every other strip's edges are weighted down to
their share. Segments and Profile Shape have no per-edge equivalent, so those
really are shared — the strip you last touched sets them.

Only edges belonging to a strip are ever written to. A bevel weight set by hand
anywhere else on the mesh is left alone.

**Width matters here.** The round eats into the shelf, and what is left is what
the AO has to fade out across — which is why the default Width is 0.25 m, not
the 0.1 m it used to be. The panel warns when Bevel Width is no longer below
Width.

A **Ground Level** strip has no Bevel: the line it runs along is not in the mesh,
so there is no edge to round on either side.

Bevel Width is clamped the way Blender's own **Clamp Overlap** clamps it, so an
oversized value cannot eat the strip.

### The round keeps the wall's material

The modifier inherits each new face's material from the wall it came from, which
is its default. Worth knowing because the version of this that cut the bevel in
did not: `bmesh.ops.bevel` defaults `material` to **0** where Blender's own
Bevel defaults Material Index to **-1**, and slot 0 on a wall whose brick lives
in another slot is a corner's worth of the wrong material, in a stripe.

The UVs are left to Blender's own interpolation, the same as beveling by hand.
It blends between the two rims, so the chamfer can only land inside the span
the walls already occupied — it cannot run off the end of the wall's island,
even when the wall is one cell of an atlas.

## Merge Distance is not a setting

Sections generated from neighbouring edges are welded together so they form one
continuous mesh. The distance used to be a slider with exactly one correct
answer: large enough to close the seam where two wings meet — they are lifted
off their own walls, so at a right angle their inner edges sit
`Surface Offset × √2` apart, and further on a shallower corner — and far enough
below Width not to collapse the strip. It is now `Surface Offset × 4`, floored,
and capped at a quarter of Width.

Texture is left empty on purpose — assign your own normal/diffuse map manually.

## Troubleshooting

- **"Sollumz not available"**: enable Sollumz and install its dependencies first.
- **Edge skipped**: it needs at least one adjacent face.
- **Wing extends the wrong way**: toggle Flip Direction.
