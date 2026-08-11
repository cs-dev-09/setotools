# Surface Painter

**Surface → Surface Painter**

Brush dirt, grime and graffiti straight onto a surface. Your mesh is never
touched — not on the first stroke, not on the hundredth.

That is the whole design, and it is the same trick GTA itself uses for grime.
**Start Paint** spawns a separate *paint mesh* over the wall: a copy of its
surface, packed with extra vertices, floated a few millimetres off it, wearing
a `decal.sps` material. Painting happens on that.

```
Wall (never modified)
  └── Dirt_Concrete_01     decal.sps    Color 1 alpha = the mask
  └── cd_blood_04_dec      decal.sps    ← different texture = its own layer
```

`decal.sps` reads `Color 1`'s **alpha** as its blend factor — that is Sollumz's
own node wiring — so painting alpha is painting visibility: 0.0 is a clean
wall, 1.0 is the dirt at full strength. The brush paints with `ADD_ALPHA` and
`ERASE_ALPHA`, and everything the paint mesh carries is data Sollumz exports.

## Using it

1. Select the wall.
2. Pick a category and a texture.
3. **Start Paint** — a paint mesh appears and Blender drops into Vertex Paint.
4. Paint. Left-drag adds dirt; the **Erase** toggle takes it away again.
5. Place it with **Place On Surface** or the Dirt Adjust sliders.
6. **Stop Paint** when done, then **Optimize** to make it cheap.

To remove a layer, delete its object — or press **Remove Paint Mesh**. The wall
underneath is untouched either way.

## Layers

**One layer per texture, per wall.** Pick a different texture and press Start
Paint again and you get a new layer stacked over the first, painted
independently — concrete grime and a blood pass over it are two meshes, not one
mesh whose texture keeps changing under your strokes.

An existing layer is never retextured behind your back.

## Placing the dirt

The paint mesh gets **its own UVs**: one planar projection across the whole
surface, not the wall's unwrap.

That matters more than it sounds. A wall's own layout is built for its tiling
texture, so it is usually several islands sitting on top of each other in 0–1 —
a wall with a single loop cut across it is two of them, both covering the whole
tile. Inherit that and the decal is drawn once per island: one graffiti, two
copies. A projection cannot overlap itself, so it appears exactly once however
the wall was cut or unwrapped.

**Place On Surface** then drags it with the mouse. The texture follows the
pointer exactly — at any Width, Height or Rotation — and keeps following it
past the edge of the surface, so a decal can be pushed into a corner or half
off an edge on purpose.

| Key | Does |
| --- | --- |
| Wheel | resize around the pointer |
| Shift + wheel | fine steps |
| `X` / `Y` | lock to one axis |
| Click | keep it |
| Escape | put it back |

### Dirt Adjust

Everything here is **lossless** and recomputed from a pristine copy of the UVs,
so dragging a slider back where it was gives back exactly what you had.

| Setting | Does |
| --- | --- |
| **Opacity** | fades the whole layer. Strokes are kept at full strength, so turning it back up restores every one of them |
| **Width / Height** | separate, so a streak stretches down a wall without also widening |
| **Offset X / Y** | slides the texture across the surface |
| **Rotation** | applied before the size, so a rotated pattern stretches along its own axes |
| **Repeat** | off by default — a stain is placed, not tiled |

**Preview Texture** shows the whole texture semi-transparent over the surface,
Substance-projection style, so it can be lined up before a single stroke. It is
an object-level override on a copy, so the material that exports is never
touched by it.

## Optimize

One button, and it never touches the texture — that is the difference from
baking, which flattens a tiling texture into a unique one that can never be
sharper than what it sampled. This removes geometry that carries no information
instead:

1. **Crop.** Faces the brush never reached are deleted outright, so what is
   left is a patch the size of the decal rather than a sheet the size of the
   wall. A face survives if any corner carries paint, which keeps the ring
   where alpha falls to 0 — the fade stays exactly as painted.
2. **Weld.** The staircase of tiny faces the crop leaves around the patch is
   welded into a few big ones. Only vertices belonging to no painted face are
   ever moved, so every face with paint on it comes through untouched.
3. **Thin.** Inside the patch, a stroke's detail lives entirely in the gradient
   at its edge, so the flat middle of a blob collapses to a couple of faces.

Then the origin is moved to the middle of what is left, with the mesh shifted
the other way by the same amount, so the patch does not move in the scene —
only its pivot does.

Measured on a painted blob: **1024 triangles down to 91**, UVs bit-identical.
Ngons are fine and expected; triangles are what the game pays for, so triangles
are what the tool reports.

## The texture library

**No textures are bundled.** The add-on ships the category folders empty, with
a README in each saying what goes there — dirt sheets are large enough that
they would be most of the download, and anyone doing this work already has a
library.

Set **Library Folder → Custom Library** to yours and press Refresh. Its
subfolders become the categories; a folder name the add-on does not know still
works and gets a title-cased label.

Browsing loads nothing into your file — thumbnails are read from disk — so only
textures you actually paint with end up in the .blend.
