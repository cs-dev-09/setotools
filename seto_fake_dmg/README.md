# Seto Fake Damage

Blender addon (built on [Sollumz](https://docs.sollumz.org)) that generates
chipped-edge damage decals for GTA V / FiveM assets. Select the sharp edges,
press a button, get a ready-to-export damage strip — your original mesh is
never touched.

Standalone: it does not require, and does not talk to, the Seto Fake AO addon.
Both can be installed at the same time — they share one **Seto Tools** N-panel
tab, each appearing as its own collapsible section, but neither depends on the
other and either works installed on its own.

## Requirements

- Blender 4.2+
- Sollumz installed, enabled, with dependencies already set up.
- A damage normal map on hand to assign afterward — the generated material's
  texture slots are left empty on purpose, so the decal will look blank in the
  viewport until you assign one yourself. Recommended:
  **`gz_v_ml_wallnormal_n.dds`** (see Material below).

## Install

1. Download `seto_fake_dmg.zip` (don't unzip).
2. Blender: **Edit > Preferences > Add-ons > Install from Disk** → pick the zip.
3. Enable it, then **restart Blender**.

## Usage

1. Select your mesh, enter **Edit Mode**, select one or more sharp edges.
2. Open **N-Panel > Seto Tools > Fake Damage**, adjust settings if needed.
3. Press **Create Fake Damage**.

A new `fake_dmg_00N` object is created: a strip that wraps the edge onto
both adjacent walls (or lies flat on one wall for a boundary edge like a door
frame), with UVs, a `decal_normal_only.sps` material, `Color 1` alpha for
export, and its origin at its own centre — all automatically.

## Live settings

The strip you create keeps its own settings. Select it and the **Selected
Strip** section appears under Fake Damage: drag **Damage Width** and the mesh
regenerates as you drag, the same feel as a Geometry Nodes modifier — except
the result is real mesh data, so nothing has to be applied before export.

It works because the strip remembers what it was made from: the source object,
the source-mesh vertex-index pairs of the edges that were selected, and the
settings that were used. Changing a setting re-reads those edges and rebuilds.

- **Live Update** — off freezes the strip; use **Rebuild Now** when you are done.
- The rebuild produces **final UVs**, not a placeholder — see UVs below.
- Editing the **source** mesh's topology invalidates the stored edges. The
  panel says so rather than rebuilding something wrong.
- Right after creating, the settings are also in Blender's **Adjust Last
  Operation** (F9) panel.

## How the geometry works

- **Edge chains.** The selection is first grouped into continuous chains, then
  one unbroken ribbon is extruded along each. Connected edges share their
  cross-section vertices instead of being generated separately and welded, so
  bends and 90° turns come out as clean mitered joints and nothing is
  disconnected mid-run. A chain is cut only at a loose end, a junction (3+
  selected edges meeting at one vertex), or where it closes on itself.
- **Cleanup runs last.** Once every chain is generated, the whole mesh gets a
  centroid-averaged Merge by Distance, degenerate dissolve and duplicate-face
  removal in one pass — so chains that meet at a junction join up, and nothing
  unrelated is merged.
- **Never touches the source.** The strip is built in the source object's local
  space and placed by copying its world matrix, so it lands correctly whatever
  the source object's transform.
- **Sollumz aware.** If the source object is inside a Drawable hierarchy, the
  strip is parented into it and registered as a Drawable Model. If not, it is
  left as an independent object.

## UVs

Fully automatic and **straight by construction** — no unwrap, no manual Edit
Mode step, nothing to straighten afterwards. The UVs are laid out from the
geometry itself, in metres:

- `U` = distance travelled along the edge chain
- `V` = distance across the cross-section (0 at one wing's outer edge, `width`
  at the corner, `2 x width` at the other wing's outer edge)

Then the island is fitted into the 0..1 square with **both axes scaled by the
same factor**, so a 2 m run 0.05 m wide stays 20:1 in UV space rather than
being squashed into a square. The long axis ends up spanning 1.5.

This is why an arc, a 90° turn and a straight run all give the same clean
rectangle: nothing is being solved, so there is no wobble to straighten. On a
16-segment curved rim the island measures **0.0 deviation** from a perfect
axis-aligned grid. It is also why the live rebuild can produce final UVs — no
operator is involved, so it is safe to run from a property callback.

## Material

`decal_normal_only.sps`, render bucket 2 (Decal):

| Parameter | Value |
| --- | --- |
| `useTessellation` | disabled |
| `bumpiness` | 1.00 |
| `specularIntensityMult` | 0.00 |
| `specularFalloffMult` | 40.00 |
| `specularFresnel` | 0.75 |

### Texture

**DiffuseSampler** and **BumpSampler** are left **empty** — you assign the
texture yourself. No placeholder image is generated, because a generated one
would silently export as a real (blank) normal map.

Recommended texture, in **both** slots:

| | |
| --- | --- |
| Texture | `gz_v_ml_wallnormal_n.dds` |
| Color Space | **Non-Color** |
| Embedded | unchecked |

`gz_v_ml_wallnormal_n.dds` is a normal map, so its Color Space **must** be set
to `Non-Color`. Left on `sRGB`, Blender gamma-corrects the normal vectors and
the damage reads as flat or lit from the wrong direction in the viewport.

Set the same texture in both slots: `decal_normal_only.sps` samples
`DiffuseSampler` for the alpha/shape of the chipping and `BumpSampler` for its
surface normals.

Material reuse is restricted to materials this tool created (named
`seto_fakedamage`), and a reused material is never rewritten, so hand-tweaked
values survive.

## Settings

- **Damage Width** — how far the strip extends onto each wall.
- **Surface Offset** — lift off the surface along the corner bisector, avoids z-fighting.
- **Merge Distance** — welds chains that meet at a junction into one mesh.
  Keep it above Surface Offset and well below Damage Width.
- **Alpha Center / Alpha Outer** — Color 1 alpha fade, corner → outer edge.
- **Invert Fade** — swap which side gets which alpha.
- **Flip Direction** — flips a single-wall wing to the other side.
- **Material** — reuse the Fake Damage material this tool made earlier, or always create new.

## Troubleshooting

- **"Sollumz not available"**: enable Sollumz and install its dependencies first.
- **Edge skipped**: it needs at least one adjacent face (and non-zero length).
- **Wing extends the wrong way**: toggle Flip Direction.
- **Sections look disconnected**: they were cut at a junction — raise Merge
  Distance, or select the run without the branching edge.
- **Decal looks blank**: the texture slots are empty by design — assign
  `gz_v_ml_wallnormal_n.dds` in the material properties.
- **Damage looks flat / lit from the wrong side**: the texture's Color Space is
  on `sRGB`. Set it to `Non-Color`.
