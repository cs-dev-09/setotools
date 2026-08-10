# Edge Dirt

Part of **Seto Tools**, built on [Sollumz](https://docs.sollumz.org).

Ambient Occlusion with dirt on it. Select an edge, press a button, get a
ready-to-export strip carrying **your** dirt texture — your original mesh is
never touched (the Bevel target is the one exception, and it says so).

Everything about the strip itself — Width, Surface Offset, the alphas, Bevel,
Build From: Ground Level, the live rebuild on the finished strip — works
exactly as it does in Ambient Occlusion, because it *is* Ambient Occlusion's
code. See [../fake_ao/README.md](../fake_ao/README.md) for how the geometry,
the UVs and the bevel behave.

## The texture

Drop an image into:

```
seto_tools/edge_dirt/textures/
```

It is wired into `DiffuseSampler` for you, as **sRGB** (a colour texture, not a
normal map) and not embedded. The first usable image is used, `.dds` preferred;
a file named `edge_dirt.*` wins if you want to pin one while keeping others
around. The panel shows the name of the file it found.

**The file name matters.** Sollumz exports the texture name from it, so
`decal_dirt_01.dds` becomes the `decal_dirt_01` reference in the `.ydr` — which
then has to exist in the asset's TXD.

Leaving the folder empty is not an error: the strip and its material are still
built, and the tool reports that the slot was left for you.

Restart Blender after adding a texture to a **zipped, installed** add-on; a
texture dropped into the installed folder is picked up on the next Create.

## Usage

1. Select your mesh, enter **Edit Mode**, select the edges the dirt runs along.
2. Open **N-Panel > Seto Tools > Surface > Edge Dirt**.
3. Press **Create Edge Dirt**.

A new `edge_dirt_00N` object is created, with UVs, a `decal.sps` material,
`Color 1` alpha for export and its origin at its centre. Strips are filed in an
**`edge_dirt`** collection, created on first use — or, when the source belongs
to a Sollumz Drawable, beside the rest of that asset.

For a wall that meets the floor with no edge to select, switch **Build From**
to **Ground Level** and give it the floor's world Z. No Edit Mode needed.

## Why it is a separate tool and not a texture picker on Ambient Occlusion

Because the two are used together. An AO shadow in the corner and a dirt streak
down the same corner are two strips on one wall, and a single tool with a
texture field would make the second one retexture the first. So Edge Dirt keeps:

- its own Scene settings — dialling a dirt streak in at 0.08 m cannot move the
  AO shadow's 0.25 m shelf,
- its own per-object data (`seto_edge_dirt_data`) — each strip's panel shows
  its own settings,
- its own material name (`seto_edgedirt`) — reuse never crosses over, even
  though both are `decal.sps`.

What it does **not** keep is a second copy of the code. `geometry.py` and the
live rebuild are imported from `fake_ao/`; the rebuild takes the per-object
settings group as an argument so both tools can drive it. A bug fixed in one
corner case is fixed in both.
