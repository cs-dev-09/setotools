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

- **Width** — how far the decal extends onto the wall.
- **Surface Offset** — lift off the wall, avoids z-fighting.
- **Alpha Center / Alpha Outer** — Color 1 alpha fade, corner → edge.
- **Invert Fade** — swap which side gets which alpha.
- **Flip Direction** — flips a single-wall wing to the other side.
- **Material** — reuse an existing `decal.sps` material, or always create new.

All of these stay editable on the created strip, not just at creation time.

Texture is left empty on purpose — assign your own normal/diffuse map manually.

## Troubleshooting

- **"Sollumz not available"**: enable Sollumz and install its dependencies first.
- **Edge skipped**: it needs at least one adjacent face.
- **Wing extends the wrong way**: toggle Flip Direction.
