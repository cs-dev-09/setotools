# Seto Tools

Blender add-ons for GTA V / FiveM asset authoring, built on
[Sollumz](https://docs.sollumz.org). Both generate decal geometry from an edge
selection and never touch your original mesh.

| Add-on | What it makes |
| --- | --- |
| [`seto_fake_ao_decals`](seto_fake_ao_decals) | Fake ambient-occlusion corner decals |
| [`seto_fake_dmg`](seto_fake_dmg) | Chipped-edge damage decals |

They are **separate add-ons** — install either on its own, or both. Installed
together they share a single **Seto Tools** N-panel tab, each appearing as its
own collapsible section, the way Sollumz Tools is laid out.

## Install

Grab the zips from the latest [release](../../releases) (don't unzip), then in
Blender: **Edit > Preferences > Add-ons > Install from Disk** → pick a zip →
enable it → restart Blender.

Requires Blender 4.2+ and Sollumz with its dependencies installed. Verified in
Blender 5.2.0 LTS.

## What they have in common

- **Select edges, press a button.** A separate decal object is created; the
  source mesh is never modified.
- **Live settings.** The generated strip remembers its source object, the
  edges it was built along and the settings used, so dragging a value in the
  **Selected Strip** section regenerates it as you drag — the feel of a
  Geometry Nodes modifier, except the result is real mesh data that needs no
  applying before export.
- **Straight UVs by construction.** UVs are laid out from the geometry in
  metres, then fitted into the 0..1 square with both axes scaled by the same
  factor. Nothing is solved, so an arc, a 90° turn and a straight run all give
  the same clean rectangle — no unwrap, no straightening afterwards.
- **Sollumz aware.** Correct `UVMap 0` / `Color 1` attributes, a real Sollumz
  shader material, and the strip parented into the Drawable hierarchy when the
  source belongs to one.

Each add-on's own README has the details.
