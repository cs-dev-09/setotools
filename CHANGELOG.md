# Changelog

All notable changes to Seto Tools.

## 1.0.0

### One add-on instead of three

Fake AO, Fake Damage and the new Decal Tool now ship as a single **Seto Tools**
add-on (`seto_tools/`) rather than three that had to be installed separately.
They already shared the Seto Tools N-panel tab; now they share a process and,
more usefully, one copy of the Sollumz integration.

The three copies were byte-identical apart from their docstrings and one material
builder each, so merging them changed no behaviour. The builders are simply named
apart now, each with its own material name and reuse rule so no tool can adopt —
and then retexture — another's material:

| Builder | Tool | Shader |
| --- | --- | --- |
| `find_or_create_fake_ao_material` | Fake AO | `decal.sps` |
| `find_or_create_damage_material` | Fake Damage | `decal_normal_only.sps` |
| `find_or_create_smooth_edge_material` | Smooth Edge | `decal_normal_only.sps` |
| `find_or_create_decal_material` | Decal Tool | `decal.sps` |

> **Upgrading:** disable and remove `seto_fake_ao`, `seto_fake_dmg` and
> `seto_decal_tool` before installing this. They register the same operators and
> panels, so having both loaded conflicts.

### Added — Decal Tool

Select faces, pick a decal from an external library, press one button. Per
selected surface it builds a plane aligned to that surface, offset along its
normal, with a `decal.sps` material carrying the chosen texture and its origin at
its own centre. The source mesh is only ever read.

- **Library folder** is an add-on preference, so it is picked once and survives
  new files and restarts. Categories are its subfolders. Scanned into a cache
  rather than on every redraw; **Refresh Library** rescans.
- **Texture thumbnails** in the panel — only the texture being looked at is
  loaded, once per session.
- **Merge Coplanar** — touching faces in the same plane count as one surface, so
  a wall split into N quads takes one decal, not N.
- **Randomization** — rotation, scale, texture and position, evaluated per
  surface.
- **Border ring** — the decal is a 4×4 grid (16 vertices, 9 quads) whose outer
  ring starts at alpha 0, so it dissolves into the surface instead of ending on a
  hard rectangular outline. **Edge Fade** sets its width.
- **Per-corner and per-side alpha** — four **Corner Alpha** values on the inner
  rectangle give any linear gradient across the decal; four **Border Alpha**
  values raise individual sides of the ring, for instance to keep the edge that
  meets a floor hard. Where two sides meet, the ring corner takes the lower of
  the two, so a faded side stays faded into its corners.
- **Live editing** — size, edge fade, surface offset, rotation, position on the
  surface and every alpha update as you drag. Sliding a decal past an edge
  **walks it onto the neighbouring face** instead of leaving it hanging in space;
  it can cross several faces in one drag and dragging back retraces the path.
- **No orphans on failure** — a texture that fails to load never leaves a decal
  behind. Materials are resolved before any geometry exists, so the common
  failure never creates an object at all.

### Added — Smooth Edge

Fake Damage's structure applied to a different job: a normal-map strip along a
hard edge so it reads as rounded in game, without adding a bevel. Two things it
does that Fake Damage did not:

- **Shade smooth**, automatically, on the generated strip only.
- **Its texture is bundled** in `smooth_edge/textures/` and wired into
  `BumpSampler` and `DiffuseSampler` as Non-Color, not embedded.

### Added — across the tools

- **Bundled textures.** Fake AO, Fake Damage and Smooth Edge each carry their
  texture in the tool's own `textures/` folder and wire it in automatically. Fake
  AO uses `decal.sps`, which has only `DiffuseSampler` and wants a colour
  texture, so its image goes in as **sRGB**; the other two are normal maps in
  both slots as **Non-Color**. An empty folder is not an error — the strip is
  still built and the tool reports that the slot was left for you.
- **Shade smooth** on everything generated, applied through the data API so it
  survives a live rebuild.
- **One vertex colour.** Every tool writes the same `Color 1`: RGB `#00B200`,
  alpha 1.0 at the centre fading to 0.0 at the outer edge. Defined once in
  `shared/vertex_color.py`.
- **Sorted output.** Inside a Sollumz Drawable, generated geometry lands in the
  Drawable's own collection, beside the rest of the asset — parenting alone left
  it greyed out in the outliner and out of reach of anything working on that
  collection. Outside one, each tool files into its own collection, created on
  first use: `fake_ao`, `fake_dmg`, `smooth_edge`, and `decals` with one child
  per library category.
- **Upright UVs.** The strip tools rotate their island 90° so it stands vertical
  in the 0..1 square. A real rotation, not an axis swap — swapping would mirror
  the island and flip the direction a normal map points in.

### Changed

- **Fake Damage shader values** now match GTA's own damage strips
  (`hn_apt_hall_blk_milo`): `bumpiness` 0.50, `specularIntensityMult` 0.125,
  `specularFalloffMult` 100, `specularFresnel` 0.97.

  `specularIntensityMult` was `0.00`, which is what made strips read as nearly
  invisible in game. `decal_normal_only` carries no colour of its own — it only
  perturbs the surface normal — so what makes a crease readable is the light's
  response to that normal, and most of that response is specular. Turning it off
  removed the effect however strong the normal map was.

  A **reused** material is never rewritten, so an existing `seto_fakedamage`
  keeps its old values — delete it, or use *Always Create New*, to pick these up.
  Smooth Edge keeps its own separate values.
- **Fake Damage UV placement.** New **UV Scale** and **UV Offset** settings place
  the fitted island on the part of the texture that holds the crease. Both are
  live-editable per strip.
- **"Damage Width" is now just "Width"** in Fake Damage and Smooth Edge.
- **Collections lost their `seto` prefix**: `fake_ao`, `fake_dmg`, `decals`.
  Generated strips are filed there instead of next to the source object.

### Fixed

- **Fake AO adopted other tools' materials.** Its reuse matched any `decal.sps`
  material, so it could pick up — and then use — one of the Decal Tool's
  per-texture materials. It now has its own name (`seto_fakeao`) and only
  recognises that.
- **Decal placement applied the offsets twice**, so a 0.2 m slide moved 0.4 m.
- **Surface tangents used the wrong matrix.** A normal must go through the
  inverse-transpose normal matrix; a tangent is an ordinary direction and must go
  through the plain linear part. Under non-uniform scale the two disagree.

### Removed

- The `seto_fake_ao/`, `seto_fake_dmg/` and `seto_decal_tool/` folders, and their
  separate zips, superseded by `seto_tools/`.

### Verified

Headless against **Sollumz 2.8.3 on Blender 5.0.1** and **Sollumz 2.9.0 on
Blender 5.2.0 LTS** — surface alignment under rotated and non-uniformly scaled
sources, Sollumz attributes and shader parameters, material reuse and separation,
bundled textures, collection placement, failure cleanup, and a clean YDR export.
