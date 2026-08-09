# Fake AO

Part of **Seto Tools**, built on [Sollumz](https://docs.sollumz.org). Generates
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
seto_tools/fake_ao/textures/
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

1. Install `seto_tools.zip` — this tool ships inside it.
2. Blender: **Edit > Preferences > Add-ons > Install from Disk** → pick the zip.
3. Enable it, then **restart Blender**.

## Usage

1. Select your mesh, enter **Edit Mode**, select one or more corner edges.
2. Open **N-Panel > Seto Tools > Fake AO**, adjust settings if needed.
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
- **Alpha Center / Alpha Outer** — Color 1 alpha fade, corner → edge.
- **Invert Fade** — swap which side gets which alpha.
- **Flip Direction** — flips a single-wall wing to the other side.
- **Material** — reuse an existing `decal.sps` material, or always create new.

All of these stay editable on the created strip, not just at creation time.

## Bevel

A sharp corner still reads as sharp under the best AO there is, so the **Bevel**
block rounds it off for you. It is **on by default**, at **Width 0.0833 m, 4
segments, profile 0.5** — Blender's own bevel settings, under their own names.

**Target** decides what gets rounded:

- **Source + Strip** (default) — rounds the selected edge on **your** mesh, and
  builds the strip so it follows that round with the same Width and Segments.
  Both meshes end up the same shape, which is the only way the decal sits *on*
  the rounded corner instead of flat across it. The strip's round is generated
  by beveling the strip's own seam with the same settings rather than by
  approximating the source's, so the two match by construction — the strip
  lands exactly Surface Offset outside the source.
- **Strip Only** — rounds off the strip's own seam and leaves the source sharp.
  The round hides the sharp corner underneath it, and nothing you started from
  is modified. A wing with no partner (a boundary edge like a door frame) has
  no seam and is left as it is.
- **Source Only** — rounds the source and runs a *flat* strip along the
  chamfer's rim onto each wall, leaving the round itself bare. The short cap
  edges at either end of a run are skipped, so nothing decals the end of the
  chamfer.

**Width matters here.** The round eats into the shelf, and what is left is what
the AO has to fade out across — which is why the default Width is 0.25 m, not
the 0.1 m it used to be. The panel warns when Bevel Width is no longer below
Width.

**The source bevel runs once, at creation.** Live rebuilds only re-apply the
strip's; re-running the source one on every slider drag would round the round.
So the strip's own panel offers a plain Bevel toggle with no target to pick, and
a strip created with Source Only starts with it off.

A **Source + Strip** strip cannot store its corner as vertex indices — the edge
it was built from was beveled away — so it stores the corner geometry itself and
rebuilds from that. It still follows the source object being moved, rotated or
scaled; what it cannot follow is the source's vertices being edited, which is
the same limit the index path has.

Bevel Width is clamped the way Blender's own **Clamp Overlap** clamps it, so an
oversized value cannot eat the strip.

### The round keeps the wall's material

The bevel is asked to inherit each new face's material from the wall it came
from — `material=-1`, exactly what Blender's own Bevel does with its Material
Index. `bmesh.ops.bevel` defaults that to **0** instead, which puts the whole
chamfer on material slot 0 whatever that happens to be: on a wall whose brick
lives in another slot, a corner's worth of the wrong material, in a stripe.

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
