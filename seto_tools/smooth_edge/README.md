# Smooth Edge

Part of **Seto Tools**, built on [Sollumz](https://docs.sollumz.org). Lays a
normal-map strip along a hard edge so it reads as rounded in game, without
adding a bevel to the mesh. Select the edges, press a button — your original
mesh is never touched.

Structurally it is Fake Damage: the same chain walking, the same ribbon
generation, the same live settings. It differs in two things it does for you:

- **Shade smooth**, automatically. A flat-shaded strip bands at every quad
  boundary, which is the seam this tool exists to hide. Applied to the
  generated strip only — never to your source mesh — and re-applied on every
  live rebuild.
- **Its texture is bundled.** The normal map lives in `textures/` inside the
  add-on and is wired into `BumpSampler` and `DiffuseSampler` for you, as
  Non-Color and not embedded. No picking a file per strip, and a scene handed
  to someone else looks the same on their machine.

## The texture

Drop a normal map into:

```
seto_tools/smooth_edge/textures/
```

The first usable image is used, `.dds` preferred; a file named `smooth_edge.*`
wins over anything else in the folder if you want to pin one while keeping
others around. The file is only ever read.

**The file name matters.** Sollumz exports the texture name from it, so
`mh_v_flatnormal_n.dds` becomes the `mh_v_flatnormal_n` reference in the `.ydr`
— which then has to exist in the asset's TXD. Leaving the folder empty is not
an error: the strip and its material are still built, and the tool reports that
the slot was left for you.

## Install

1. Install `seto_tools.zip` — this tool ships inside it.
2. Blender: **Edit > Preferences > Add-ons > Install from Disk** → pick the zip.
3. Enable it, then **restart Blender**.

## Usage

1. Select your mesh, enter **Edit Mode**, select the edges you want rounded.
2. Open **N-Panel > Seto Tools > Smooth Edge**, adjust settings if needed.
3. Press **Create Smooth Edge**.

A `smooth_edge_00N` object is created in a **`smooth_edge`** collection: shaded
smooth, with UVs, a `decal_normal_only.sps` material carrying the bundled
normal map, `Color 1` alpha for export, and its origin at its own centre.

Settings stay live afterwards in **Selected Edge** — drag Width and the strip
regenerates as you drag, keeping its smooth shading and its UVs.
