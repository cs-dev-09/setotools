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

A new `Fake_Damage_00N` object is created: a strip that wraps the edge onto
both adjacent walls (or lies flat on one wall for a boundary edge like a door
frame), with UVs, a `decal_normal_only.sps` material, `Color 1` alpha for
export, and its origin at its own centre — all automatically.

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

Fully automatic — no manual Edit Mode step. On create, the finished object gets
a **Conformal unwrap**, then its UVs are **scaled by 1.5**. Conformal preserves
the strip's aspect ratio, so a long thin run stays long and thin in UV space
instead of being squashed into a square.

Before the unwrap, arc-length UVs are authored along the chain (`U` = distance
travelled, `V` = 0.0 / 0.5 / 1.0 across the wrap). Those are a fallback: they
only survive if the unwrap fails, and you get a warning if that happens.

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
