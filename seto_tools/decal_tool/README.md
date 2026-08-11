# Decal Tool

Part of **Seto Tools**, built on [Sollumz](https://docs.sollumz.org), for GTA V /
FiveM MLO work. Select faces, pick a decal from your library, press one button —
you get surface-aligned `decal.sps` decal planes, and your original mesh is never
touched.

Select Face → Choose Decal → Create Decal.

## Requirements

- Blender 4.2+
- Sollumz installed, enabled, with dependencies (szio) already set up.
- A decal library folder of your own PNG/TGA/DDS textures.

## Install

1. Install `seto_tools.zip` — this tool ships inside it.
2. Blender: **Edit > Preferences > Add-ons > Install from Disk** → pick the zip.
3. Enable it, then **restart Blender**.

It shares the **Seto Tools** N-panel tab with the other tools, under **Surface**,
but does not depend on any of them.

## Decal library

Point the addon at any folder. Each subfolder becomes a category:

```
Decals/
    Dirt/       dirt_01.png  dirt_02.png  dirt_03.png
    Cracks/     crack_01.png crack_02.png
    Leaks/      leak_01.png
    Graffiti/   graffiti_01.png
```

The folder is an **add-on preference**, not a scene setting — you pick it once and it
is remembered across new files, restarts and updates. (It can also be set in
**Edit > Preferences > Add-ons > Seto Decal Tool**; both fields are the same setting.)

**Category** is just the subfolder name. Images sitting directly in the library root
show up under a single `(root)` category, which works fine — categories only start
earning their keep when you want **Random Texture** to pick "any dirt" rather than
"anything in the library". Supported extensions: `.png`, `.tga`, `.dds`, `.jpg`,
`.jpeg`. Nothing is hard-coded — drop a new `dirt_07.png` in and press
**Refresh Library** to pick it up, no restart needed.

## Usage

1. Open **N-Panel > Seto Tools > Decal Tool**, set **Decal Library** (once), press
   **Refresh Library**.
2. Select your mesh, enter **Edit Mode**, select one or more faces.
3. Pick a **Category** and **Texture** — the thumbnail below shows exactly what you
   are about to place.
4. Press **CREATE DECAL**.

The panel keeps only that on screen. **Placement**, **Randomization** and
**Material** are collapsed sub-panels for the things you set once and leave alone.

One `seto_decal_<texture>` object is created per selected face, each with:

- a quad aligned to that face's surface — floors, walls, ceilings and slanted
  geometry all work, including on source objects with unapplied rotation and
  non-uniform scale,
- a **Surface Offset** lift along the face normal so it does not z-fight,
- a **border ring**: the decal is a 4×4 grid (16 vertices, 9 quads) whose outer
  ring starts at alpha 0, so it dissolves into the surface instead of ending on a
  hard rectangular outline. **Edge Fade** sets how wide that ring is, and
  **Border Alpha** lets you raise any of its four sides afterwards,
- a full 0–1 `UVMap 0` across the outer boundary — the texture covers the whole
  decal undistorted — and a `Color 1` attribute (Sollumz renders `decal.sps` as
  `Color 1 alpha × texture alpha`),
- a `decal.sps` material with your image in `DiffuseSampler`,
- its origin at the center of the decal,
- placement in **`decals/<category>`** — a `decals` collection with one child per
  library category, so the scene is sorted the same way the library on disk is
  (textures loose in the library root go straight into `decals`) — parented into the source object's
  Sollumz Drawable when it has one.

You stay in Edit Mode with your selection intact, so you can immediately pick another
texture and fire again.

## Adjusting a decal afterwards

Select a generated decal and the **Selected Decal** section appears under Decal Tool,
with its thumbnail so you can tell decals apart at a glance. Width, Height, Surface
Offset, Rotation, **Offset U / Offset V** and the four **Corner Alpha** values all
update the decal as you drag them — it slides, spins, resizes and fades *on its surface* and
cannot come off it, because the decal stores the surface frame it was placed on.

- **Rotation** spins in place; it never slides the decal.
- **Offset U / V** slide it across the surface. Push one past the edge of the face and
  the decal **walks onto the neighbouring face** — it re-orients to that face's normal
  and the leftover travel continues there, so it turns corners instead of hanging off
  into space. It can cross several faces in one drag, and dragging back retraces the
  path exactly. An open boundary edge (nothing on the other side) stops it at the edge.
- **Border Alpha** sets the alpha along each side of the border ring — bottom,
  right, top, left — all 0 by default. Raise one to keep that edge hard, for
  instance where a decal meets a floor, while the rest still fade out. Where two
  sides meet, the ring corner takes the **lower** of the two, so a faded side stays
  faded all the way into its corners instead of ending opaque.
- **Corner Alpha** sets the alpha on the four corners of the *inner* rectangle.
  One value per corner, laid
  out in the panel the way the decal sits (top row above bottom row). Blender
  interpolates between them, so four values give any linear gradient across the
  decal — top to bottom, side to side, or diagonal — while the quad stays four
  vertices. **Fade Down** and **All 1.0** are one-click shortcuts.
  `decal.sps` renders as `Color 1 α × texture α`, so **1.0 is as opaque as the
  texture allows** — decals are created fully opaque and you fade them from there.
  If one looks too faint at 1.0, the transparency is in the PNG itself, not here.
- **Center** puts it back at the middle of the face it came from.
- **Live Update** off + **Update** if you'd rather apply changes in one go.

Nothing is regenerated on a change — only four vertices, one colour attribute and the
object matrix change — so the UVs and the material survive untouched.

The decal stays a flat quad: crossing an edge moves it onto the next face, it does not
bend around the corner. A decal parked exactly on a corner will still overhang; slide
it a little further and it settles onto one side.

## Settings

- **Merge Coplanar** (on by default) — touching faces lying in the same plane count
  as one surface, so a wall split into two (or twenty) quads takes a **single** decal
  centred on the whole wall. Faces in different planes, and faces that do not touch,
  still get their own. Turn it off for one decal per selected face.
- **Width / Height** — decal size in metres, measured across the outer boundary.
- **Edge Fade** — width of the alpha-0 border ring. Capped at just under half the
  decal, so a fade wider than the decal blunts rather than turning the inner
  rectangle inside out. Live-editable per decal.
- **Surface Offset** — lift off the surface, avoids z-fighting. Default 0.003 m.
- **Rotation** — spin around the *face normal*, so 45° looks the same on a floor and
  on a wall.
- **Random Rotation / Scale / Texture / Position** — evaluated independently per
  selected face, so a multi-face selection gives you variation in one press.
- **Random Position** — drops each decal at a random spot *inside* the face instead
  of at its center. Turn this on when placing several decals on one large face,
  otherwise every press lands on top of the last one. A decal too big for its face
  stays centered rather than hanging over the edge.
- **Material** — reuse an existing decal material for the same texture file, or
  always create a new one.

Decals are always generated fully opaque; fading is done afterwards with **Corner
Alpha** in Selected Decal, where you can see the result as you drag.

Decals on walls and slanted surfaces are oriented visually upright (world Z projected
onto the face); floors and ceilings, where "upright" means nothing, fall back to the
face's own edge tangent.

## Troubleshooting

- **"Sollumz not available"** — enable Sollumz and install its dependencies first.
- **"No textures found in this category"** — press **Refresh Library**.
- **Decal is invisible** — check `Color 1` alpha is 255; `decal.sps` multiplies it by
  the texture alpha.
- **A texture failed** — the decal for it is not created at all (no orphan planes are
  left behind); the report names the file.
