# Surface Painter

Part of **Seto Tools**, built on [Sollumz](https://docs.sollumz.org). Brush
dirt, grime and graffiti straight onto a surface. Your mesh is never touched —
not on the first stroke, not on the hundredth.

That is the whole design, and it is the same trick GTA itself uses for grime.
**Start Paint** spawns a separate *paint mesh* over the wall: a copy of its
surface, packed with extra vertices, floated a few millimetres off it, wearing
a `decal.sps` material. Painting happens on that. Delete it and the dirt is
gone and the wall is exactly as it was.

```
Wall (never modified)
  └── Dirt_Concrete_01     decal.sps    Color 1 alpha = the mask
  └── cd_blood_04_dec      decal.sps    ← different texture = its own layer
```

`decal.sps` reads `Color 1`'s **alpha** as its blend factor — that is Sollumz's
own node wiring, not ours — so painting alpha is painting visibility:

| alpha | what you see |
| --- | --- |
| 0.0 | nothing, clean wall |
| 1.0 | the dirt texture at full strength |

The brush paints with `ADD_ALPHA` / `ERASE_ALPHA`, and everything the paint mesh
carries is data Sollumz exports: `Color 1`, `UVMap 0`, a `decal.sps` material,
and nothing else in either list.

## Layers

One layer per texture, per wall. Pick a different texture and press Start Paint
again and you get a **new layer** stacked over the first, painted independently
— concrete grime and a blood pass over it are two meshes, not one mesh whose
texture keeps changing under your strokes. An existing layer is never
retextured behind your back.

## Placing the dirt

The paint mesh gets its **own UVs**: one planar projection across the whole
surface, not the wall's unwrap. That matters more than it sounds. A wall's own
layout is built for its tiling texture, so it is usually several islands
sitting on top of each other in 0–1 — a wall with a single loop cut across it
is two of them, both covering the whole tile. Inherit that and the decal is
drawn once per island: one graffiti, two copies. A projection cannot overlap
itself, so it appears exactly once however the wall was cut or unwrapped.

**Place On Surface** then drags it with the mouse. The texture follows the
pointer exactly — at any Width, Height or Rotation — and keeps following it
past the edge of the surface, so a decal can be pushed into a corner or half
off an edge on purpose. The wheel resizes around the pointer (Shift for fine
steps), `X` or `Y` locks to one axis, click keeps it, Escape puts it back.

Everything in **Dirt Adjust** is lossless and recomputed from a pristine copy
of the UVs, so dragging a slider back where it was gives back exactly what you
had:

| Setting | Does |
| --- | --- |
| Opacity | fades the whole layer; strokes are kept at full strength, so turning it back up restores every one of them |
| Width / Height | separate, so a streak stretches down a wall without also widening |
| Offset X / Y | slides the texture across the surface |
| Rotation | applied before the size, so a rotated pattern stretches along its own axes |
| Repeat | off by default — a stain is placed, not tiled |

**Preview Texture** shows the whole texture semi-transparent over the surface,
Substance-projection style, so it can be lined up before a single stroke. It is
an object-level material override on a copy, so the material that exports is
never touched by it.

## Optimize

One button, and it never touches the texture — that is the difference from
baking, which flattens a tiling texture into a unique one that can never be
sharper than what it sampled. This removes geometry that carries no
information instead:

1. **Crop.** Faces the brush never reached are deleted outright, so what is
   left is a patch the size of the decal rather than a sheet the size of the
   wall. A face survives if any corner carries paint, which keeps the ring
   where alpha falls to 0 — the fade stays exactly as painted.
2. **Weld.** The staircase of tiny faces the crop leaves around the patch is
   welded into a few big ones. Only vertices belonging to no painted face are
   ever moved, so every face with paint on it comes through untouched.
3. **Thin.** Inside the patch, a stroke's detail lives entirely in the gradient
   at its edge, so the flat middle of a blob collapses to a couple of faces.

Then the object's origin is moved to the middle of what is left — the mesh is
shifted the other way by the same amount, so the patch does not move in the
scene, only its pivot does.

Measured on a painted blob: **1024 triangles down to 91**, UVs bit-identical.
Ngons are fine and expected; triangles are what the game pays for, so triangles
are what the tool reports.

## The texture library

Point the tool at a folder and its subfolders become categories. The browser in
the panel lists the textures in the selected category with a large preview
under the list. Browsing loads nothing into your file — thumbnails are read
from disk — so only textures you actually paint with end up in the .blend.

## Install

1. Install `seto_tools.zip` — this tool ships inside it.
2. Blender: **Edit > Preferences > Add-ons > Install from Disk** → pick the zip.
3. Enable it, then **restart Blender**.

## Usage

1. Select the wall.
2. Open **N-Panel > Seto Tools > Surface Painter**, pick a category and a
   texture.
3. Press **Start Paint**. A paint mesh appears over the wall and Blender drops
   into Vertex Paint.
4. Paint. Left-drag adds dirt, and the Erase toggle takes it away again.
5. Place it with **Place On Surface** or the Dirt Adjust sliders.
6. **Stop Paint** when you are done, and **Optimize** to make it cheap.

To remove a layer, delete its object — or press **Remove Paint Mesh**. The wall
underneath is untouched either way.
