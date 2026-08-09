# Changelog

All notable changes to Seto Tools.

## 1.1.1

### Fixed — Sollumz was not detected when installed from the repository

Every tool reported **"Sollumz not available"** on machines that plainly had it.
The detection required the add-on's module name to end in exactly `sollumz`,
which is true for an extension and for a folder called `Sollumz` — and false
for the most ordinary way there is to install it. GitHub names its archive
after the branch or tag, so downloading Sollumz from its repository installs as
`Sollumz-main`, `Sollumz-master` or `Sollumz-2.9.0`, and none of those matched.

The name test is now a loose *candidate* filter — anything starting with
`sollumz` — and the decision is made by importing a module only Sollumz has.
Guessing which separators are legitimate is what caused this in the first
place; verifying is what settles it, and it also means an unrelated add-on
called `sollumz_extras` is rejected for being the wrong thing rather than for
being spelled unexpectedly. Extension names are split at the `bl_ext.<repo>.`
prefix rather than the last dot, so a version number in a folder name no longer
turns `Sollumz-2.9.0` into `0`.

When nothing is found at all, the message now says the add-on must also be
*enabled* — `preferences.addons` only lists enabled ones, so installed-but-
unticked was reported as "not installed", which sends people to reinstall
something they already have.

### Fixed — Surface Painter did not say when Sollumz was missing

The other four tools each showed a "Sollumz not available" box; Surface Painter
was the one that never got the paste, so it drew its whole UI and looked like
the tool that worked without Sollumz — until Start Paint, which needs a
`decal.sps` material that only Sollumz can build. Failing in the panel, with
the reason, beats failing at the button.

That block now lives once in `shared/ui_common.py` and all five tools use it,
along with the label-wrapping helper that had been copy-pasted five times.

### Changed

- **"No textures found" now says what to do.** With nothing bundled, an empty
  library is the normal first run, not a fault, so the panel points at Library
  Folder instead of showing an error icon.

### Added

- `tests/panels.py` drives **every** Seto panel's `draw()` against a validating
  stub layout, with Sollumz both available and missing — 261 checks. Blender
  only calls `draw()` from the UI thread, so every other test here can pass
  while a panel explodes on first redraw; that had happened three times before
  this existed, and each time a user found it rather than the suite.

## 1.1.0

### Added — Surface Painter

Brush dirt, grime and graffiti straight onto a surface, without the surface
ever being modified. **Start Paint** spawns a separate *paint mesh* over it — a
copy of the surface, packed with extra vertices, floated a few millimetres off
it, wearing a `decal.sps` material — and painting happens on that. Delete it and
the dirt is gone and the wall is exactly as it was. Same trick GTA uses for
grime.

`decal.sps` reads `Color 1`'s alpha as its blend factor, which is Sollumz's own
node wiring, so painting alpha is painting visibility: the brush works in
`ADD_ALPHA` / `ERASE_ALPHA` and the mesh carries only what Sollumz exports —
`Color 1`, `UVMap 0`, and nothing else in either list.

- **Layers.** One per texture, per wall. Picking a different texture and
  pressing Start Paint again adds a layer over the first rather than
  retexturing what you already painted.
- **Its own UVs.** The paint mesh is given one planar projection across the
  whole surface instead of inheriting the wall's unwrap. A wall's layout is
  built for its tiling texture, so it is usually several islands stacked in
  0–1 — a wall with one loop cut is two of them — and inheriting that drew the
  decal once per island. A projection cannot overlap itself.
- **Place On Surface.** Drags the texture with the mouse, and the point you
  grabbed stays under the pointer at any Width, Height or Rotation. It keeps
  tracking past the edge of the surface, by falling back to the projection
  plane, so a decal can be pushed into a corner or half off an edge. The wheel
  resizes around the pointer, `X`/`Y` lock an axis.
- **Lossless placement.** Opacity, Width, Height, Offset and Rotation all
  recompute from a pristine copy of the UVs and strokes, so dragging a slider
  back where it was gives back exactly what you had.
- **Preview Texture.** The whole texture shown semi-transparent over the
  surface, Substance-projection style, as an object-level override on a copy —
  the material that exports is never touched.
- **Optimize**, which never touches the texture: unpainted faces are cropped
  away so the layer ends up the size of the decal rather than the wall, the
  staircase left around the patch is welded down, and inside it the vertices a
  stroke does not need are dissolved. Then the origin moves to the middle of
  what is left. Measured: **1024 triangles down to 91**, UVs bit-identical.
- **Texture library** with categories, an in-panel browser and disk-backed
  thumbnails, so browsing loads nothing into your file. No textures are
  bundled — the category folders ship empty, each with a README saying what
  goes there. Dirt sheets are large enough to have been most of the download,
  and anyone doing this work already has a library: point **Custom Library**
  at it.

Baking was built, worked, and was removed. A baked texture is flattened from a
tiling one and can never be sharper than what it sampled, which on a wall is a
lot worse — so the optimisation removes geometry instead, and the pixels are
untouched.

### Changed — the N-panel

- **The tab is grouped by what a tool works on.** The three that build a strip
  along selected edges come first — Fake AO, Fake Damage, **Smooth Edge** —
  then the two that put texture on a surface: Decal Tool and Surface Painter.
  Smooth Edge used to sit below the Decal Tool, splitting the strip tools in
  half, and the ordering had a hole in it.
- **Surface Painter's section is split into child panels** the way the Decal
  Tool's is. It has the most controls of the five, and as one column it was
  long enough that Start Paint scrolled off the bottom while you were choosing
  a texture. What is left in the main section is the workflow — layers,
  texture, paint — with **Brush**, **Placement**, **Normal Map**, **Paint
  Mesh** and **Library Folder** below it. Placement and Normal Map only appear
  once a layer exists.
- **Explanations moved out of the panel and into tooltips**, where Blender
  meant them to live. Several three-line paragraphs of `label()` were spending
  permanent vertical space on things you read once.
- **Buttons are Title Case**, matching the other four tools. Surface Painter
  was the only one shouting `START PAINT`.

### Verified

`tests/surface_painter.py`, headless against Sollumz on Blender 5.2.0 LTS. The
two checks worth keeping: that the paint mesh's UVs are one **affine** function
of position — an island or a repeat breaks that fit and nothing else does — and
that a drag leaves the texture point you grabbed under the pointer at every
Width, Height and Rotation, which catches a wrong sign, a missing divide by the
size and a missing rotation as three separate failures.

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
