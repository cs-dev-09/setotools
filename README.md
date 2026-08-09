# Seto Tools

One Blender add-on for GTA V / FiveM asset authoring, built on
[Sollumz](https://docs.sollumz.org). It generates decal geometry from a
selection and never touches your original mesh.

| Tool | What it makes | Built from |
| --- | --- | --- |
| [Fake AO](seto_tools/fake_ao) | Fake ambient-occlusion corner decals | selected edges |
| [Fake Damage](seto_tools/fake_damage) | Chipped-edge damage decals | selected edges |
| [Decal Tool](seto_tools/decal_tool) | Surface-aligned decal planes from your own decal library | selected faces |
| [Smooth Edge](seto_tools/smooth_edge) | Normal-map strips that make a hard edge read as rounded | selected edges |

They all live in the **Seto Tools** N-panel tab, each as its own collapsible
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
    __init__.py      registers the tools, in panel order
    shared/          code every tool uses
        sollumz_integration.py   every call into Sollumz, and the material builders
        vertex_color.py          the Color 1 they all write
        bundled_textures.py      finding a tool's own textures/ folder
    fake_ao/
    fake_damage/
    decal_tool/
    smooth_edge/
```

Each tool stays self-contained — its own settings, operators and panel, exactly
as when they shipped separately. `shared/` holds only what genuinely belongs to
all of them; `sollumz_integration.py` in particular used to be copy-pasted into
each one.

Inside a tool the split is always the same:

| File | Holds |
| --- | --- |
| `geometry.py` | pure mesh maths — no Sollumz, no `bpy.data` |
| `properties.py` | Scene-level settings |
| `object_settings.py` | per-object settings that rebuild the result live |
| `operators.py` | the Create operator, tying it together |
| `ui.py` | the N-panel |

## What they have in common

- **Select, press a button.** A separate decal object is created; the source
  mesh is never modified.
- **Sorted output.** Inside a Sollumz Drawable, what a tool generates lands in
  the Drawable's own collection, beside the rest of the asset. Outside one, each
  tool files into its own collection, created on first use: `fake_ao`,
  `fake_dmg`, `smooth_edge`, and `decals` with one child per decal-library
  category.
- **Bundled textures.** Fake AO, Fake Damage and Smooth Edge each ship their
  texture in the tool's own `textures/` folder and wire it in automatically —
  drop a file there and it is picked up. The Decal Tool instead reads a library
  folder you point it at.
- **One vertex colour.** Every tool writes the same `Color 1`: RGB `#00B200`,
  alpha 1.0 at the centre of a strip fading to 0.0 at its outer edge. The alpha
  is what the decal shaders use as their blend factor; the RGB is not read by
  either `decal.sps` or `decal_normal_only.sps`, and is fixed so generated
  geometry is recognisable and consistent. It lives in
  [`shared/vertex_color.py`](seto_tools/shared/vertex_color.py) — change it
  there and all four follow.
- **Shaded smooth.** Everything these tools generate is set smooth, so a strip
  shows no hard band at its quad boundaries. Applied to the generated object
  only, through the data API, so it survives a live rebuild too.
- **Upright UVs.** The strip tools fit their island into the 0..1 square standing
  vertically, so every generated strip unwraps the same way round.
- **Live settings.** What you generate remembers how it was made, so dragging a
  value in the **Selected …** section updates it as you drag — the feel of a
  Geometry Nodes modifier, except the result is real mesh data that needs no
  applying before export. The strip tools re-read their source edges; a decal
  carries the surface frame it was placed on, so it can even walk onto a
  neighbouring face when you slide it past an edge.
- **Straight UVs by construction.** UVs are laid out from the geometry in
  metres, then fitted into the 0..1 square with both axes scaled by the same
  factor. Nothing is solved, so an arc, a 90° turn and a straight run all give
  the same clean rectangle — no unwrap, no straightening afterwards. Decal Tool
  authors its quad UVs as a plain full 0–1 layout for the same reason.
- **Sollumz aware.** Correct `UVMap 0` / `Color 1` attributes, a real Sollumz
  shader material, and the strip parented into the Drawable hierarchy when the
  source belongs to one.

Each tool's own README has the details, and [CHANGELOG.md](CHANGELOG.md) has
what changed and why.

## Development

Verification scripts live in [`tests/`](tests). They drive a real Blender in
background mode against a real Sollumz install — there is no mocking — and cover
surface alignment under awkward transforms, the Sollumz attributes and shader
parameters, material reuse and separation, collection placement, failure cleanup
and a YDR export.

```bash
blender -b --python tests/verify_decal_tool.py
```

Every script exits non-zero on failure and prints a `RESULT: n/n` line. Run them
against each Blender you support: Sollumz's own API differs between versions, and
so does its exporter.
