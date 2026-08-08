# Seto Fake AO & Decals

Blender addon (built on [Sollumz](https://docs.sollumz.org)) that generates
decals for GTA V / FiveM assets. Select an edge, press a button, get a
ready-to-export corner decal — your original mesh is never touched.

Tools included:

- **Fake AO** — fake ambient-occlusion corner decals.

## Requirements

- Blender 4.2+
- Sollumz installed, enabled, with dependencies already set up.
- Any texture on hand to assign afterward (even a plain black one) — the
  generated material's texture slot is left empty on purpose, so the decal
  will look black/blank in the viewport until you assign one yourself.

## Install

1. Download `seto_fake_ao_decals.zip` (don't unzip).
2. Blender: **Edit > Preferences > Add-ons > Install from Disk** → pick the zip.
3. Enable it, then **restart Blender**.

## Usage

1. Select your mesh, enter **Edit Mode**, select one or more corner edges.
2. Open **N-Panel > Seto Fake AO & Decals**, adjust settings if needed.
3. Press **Create Fake AO**.

A new `seto_fakeao_00N` object is created: wraps the corner (or lies flat
on one wall for a boundary edge like a door frame), gets UVs (Cube
Projection), a `decal.sps` material, correct `Color 1` alpha for export,
and its origin set to its center — all automatically.

## Settings

- **Width** — how far the decal extends onto the wall.
- **Surface Offset** — lift off the wall, avoids z-fighting.
- **Alpha Center / Alpha Outer** — Color 1 alpha fade, corner → edge.
- **Invert Fade** — swap which side gets which alpha.
- **Flip Direction** — flips a single-wall wing to the other side.
- **Material** — reuse an existing `decal.sps` material, or always create new.

Texture is left empty on purpose — assign your own normal/diffuse map manually.

## Troubleshooting

- **"Sollumz not available"**: enable Sollumz and install its dependencies first.
- **Edge skipped**: it needs at least one adjacent face.
- **Wing extends the wrong way**: toggle Flip Direction.
