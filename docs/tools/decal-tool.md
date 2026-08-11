# Decal Tool

**Surface → Decal Tool**

Select faces, pick a decal from your library, press one button: you get
surface-aligned `decal.sps` planes, and your mesh is never touched.

**Select face → choose decal → Create Decal.**

## The decal library

Point the add-on at any folder. Each subfolder becomes a category:

```
Decals/
    Dirt/       dirt_01.png  dirt_02.png  dirt_03.png
    Cracks/     crack_01.png crack_02.png
    Leaks/      leak_01.png
    Graffiti/   graffiti_01.png
```

The folder is an **add-on preference**, not a scene setting — you pick it once
and it is remembered across new files, restarts and updates.

Supported: `.png`, `.tga`, `.dds`, `.jpg`, `.jpeg`. Images sitting directly in
the library root show up under a single `(root)` category, which works fine —
categories only start earning their keep when you want **Random Texture** to
pick "any dirt" rather than "anything in the library".

Nothing is hard-coded. Drop a new file in and press **Refresh Library**; no
restart needed.

## Placing a decal

1. Set **Decal Library** once, press **Refresh Library**.
2. Select the mesh, enter **Edit Mode**, select one or more faces.
3. Pick a **Category** and **Texture** — the preview shows exactly what you are
   about to place.
4. Press **Create Decal**.

You stay in Edit Mode with your selection intact, so you can pick another
texture and fire again immediately.

One object is created per selected face — or per *surface*, see Merge Coplanar
below — each with a quad aligned to that face, a border ring that dissolves
into the surface, a full 0–1 UV layout, and a `decal.sps` material carrying
your image.

Decals on walls and slanted surfaces are oriented visually upright (world Z
projected onto the face). On floors and ceilings, where "upright" means
nothing, they fall back to the face's own edge tangent.

## Placement settings

| Setting | Does |
| --- | --- |
| **Merge Coplanar** | on by default: touching faces in the same plane count as one surface, so a wall split into twenty quads takes a **single** decal centred on the whole wall. Off gives one decal per selected face |
| **Width / Height** | decal size in metres, measured across the outer boundary |
| **Edge Fade** | width of the alpha-0 border ring. Capped at just under half the decal, so a fade wider than the decal blunts rather than turning inside out |
| **Surface Offset** | lift off the surface. 0.003 m by default |
| **Rotation** | spin around the *face normal*, so 45° looks the same on a floor and on a wall |

## Randomization

**Random Rotation**, **Scale**, **Texture** and **Position** are evaluated
independently per selected face, so a multi-face selection gives variation in
one press.

**Random Position** drops each decal at a random spot *inside* its face instead
of at the centre. Turn it on when placing several decals on one large face —
otherwise every press lands on top of the last one. A decal too big for its
face stays centred rather than hanging over the edge.

## Selected Decal

Select a generated decal and its panel appears, with its thumbnail so you can
tell decals apart at a glance. Everything here updates as you drag.

**Nothing is regenerated on a change** — four vertices, one colour attribute
and the object matrix — so the UVs and the material come through untouched.

### Sliding across the surface

**Offset U / V** slide the decal across the surface. Push one past the edge of
the face and the decal **walks onto the neighbouring face**: it re-orients to
that face's normal and the leftover travel continues there, so it turns corners
instead of hanging off into space. It can cross several faces in one drag, and
dragging back retraces the path exactly. An open boundary edge stops it.

**Rotation** spins in place and never slides it. **Center** puts it back at the
middle of the face it came from.

The decal stays a **flat quad**: crossing an edge moves it onto the next face,
it does not bend around the corner. One parked exactly on a corner will
overhang; slide it a little further and it settles onto one side.

### Fading

**Border Alpha** sets the alpha along each side of the border ring — bottom,
right, top, left — all 0 by default. Raise one to keep that edge hard, for
instance where a decal meets a floor, while the rest still fade out. Where two
sides meet, the ring corner takes the **lower** of the two, so a faded side
stays faded all the way into its corners.

**Corner Alpha** sets the alpha on the four corners of the *inner* rectangle,
laid out in the panel the way the decal sits. Blender interpolates between
them, so four values give any linear gradient — top to bottom, side to side or
diagonal — while the quad stays four vertices. **Fade Down** and **All 1.0**
are one-click shortcuts.

!!! note "1.0 is as opaque as the texture allows"

    `decal.sps` renders `Color 1 α × texture α`. Decals are created fully
    opaque and you fade them from there. If one looks too faint at 1.0, the
    transparency is in the PNG itself.

## What it builds

- one `seto_decal_<texture>` object per face or merged surface
- a 4×4 grid (16 vertices, 9 quads) whose outer ring starts at alpha 0
- a full 0–1 `UVMap 0` across the outer boundary, and `Color 1`
- a `decal.sps` material with your image in `DiffuseSampler`
- origin at the centre of the decal
- filed into `decals/<category>`, mirroring your library folder, or into the
  source's Drawable collection
