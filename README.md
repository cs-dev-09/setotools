# Seto Tools

One Blender add-on for GTA V / FiveM asset authoring, built on
[Sollumz](https://docs.sollumz.org). It generates decal geometry from a
selection and never touches your original mesh.

| Tool | What it makes | Built from |
| --- | --- | --- |
| [Fake AO](seto_tools/fake_ao) | Fake ambient-occlusion corner decals | selected edges |
| [Fake Damage](seto_tools/fake_damage) | Chipped-edge damage decals | selected edges |
| [Decal Tool](seto_tools/decal_tool) | Surface-aligned decal planes from your own decal library | selected faces |

All three live in the **Seto Tools** N-panel tab, each as its own collapsible
section, the way Sollumz Tools is laid out.

## Install

Grab `seto_tools.zip` from the latest [release](../../releases) (don't unzip),
then in Blender: **Edit > Preferences > Add-ons > Install from Disk** → pick the
zip → enable it → restart Blender.

Requires Blender 4.2+ and Sollumz with its dependencies installed. Verified in
Blender 5.0.1 and 5.2.0 LTS.

> These used to be three separate add-ons (`seto_fake_ao`, `seto_fake_dmg`,
> `seto_decal_tool`). If you have any of them installed, **disable and remove
> them first** — they register the same operators and panels as this one.

## Layout

```
seto_tools/
    __init__.py      registers the three tools, in panel order
    shared/          code every tool uses - notably all Sollumz integration
    fake_ao/
    fake_damage/
    decal_tool/
```

Each tool stays self-contained: its own settings, operators and panel, exactly
as when they shipped separately. The only thing they share is
`shared/sollumz_integration.py`, which each of them used to carry an identical
copy of.

## What they have in common

- **Select, press a button.** A separate decal object is created; the source
  mesh is never modified.
- **Sorted output.** Each tool files what it generates in its own collection,
  created on first use: `fake_ao`, `fake_dmg`, and `decals` with one child per
  decal-library category.
- **Live settings** (Fake AO / Fake Damage). The generated strip remembers its source object, the
  edges it was built along and the settings used, so dragging a value in the
  **Selected Strip** section regenerates it as you drag — the feel of a
  Geometry Nodes modifier, except the result is real mesh data that needs no
  applying before export.
- **Straight UVs by construction.** UVs are laid out from the geometry in
  metres, then fitted into the 0..1 square with both axes scaled by the same
  factor. Nothing is solved, so an arc, a 90° turn and a straight run all give
  the same clean rectangle — no unwrap, no straightening afterwards. Decal Tool
  authors its quad UVs as a plain full 0–1 layout for the same reason.
- **Sollumz aware.** Correct `UVMap 0` / `Color 1` attributes, a real Sollumz
  shader material, and the strip parented into the Drawable hierarchy when the
  source belongs to one.

Each tool's own README has the details.
