# Material Maker

**Materials → Material Maker**

Height, normal and specular maps from **one diffuse image**. Point it at a
texture you already have, press Generate, and you get the three maps a GTA
material wants — without leaving Blender and without a second application.

This is the step before every other tool here: the rest of the add-on puts
textures onto geometry, and this is where a texture that needs more than a
diffuse comes from.

!!! info "It does not need Sollumz"

    The whole thing is numpy. That is deliberate — a machine with no working
    Sollumz can still author a texture, so this tool draws its panels either
    way, exactly like the Analysis section.

## Using it

1. Pick a **diffuse image** at the top of the panel — `Open` loads one from
   disk.
2. Press **Generate All**.
3. Tune what you got under **Settings**, and preview any map with the image
   icon.
4. **Output** and **Export** hand the maps to a material or write them to disk.

The panel reports the source image's size, and warns when **Auto Update** plus
a large texture at full resolution would rebuild on every slider move. Drop
**Processing Size** to Half or Quarter while you dial it in, then back to Full.

## Simple and Advanced

The mode switch changes **only how many controls are shown** — never the
result. Settings hidden in Simple keep working at their current values, and the
two modes produce bit-identical output.

| Tab | Simple shows |
| --- | --- |
| Height | Look presets, Final Contrast, Final Bias, Normalize, Invert |
| Normal | Slope From, Strength, Look presets, Final Contrast, Flip Y |
| Specular | Blur Size, Final Contrast, Final Bias, Channel Packing |

**Advanced** adds the frequency equalizers, colour samples, shape recognition,
angularity, per-channel packing and bit depth. Every setting carries a tooltip
explaining what it does.

## The frequency equalizer

The heart of the height map. Luminance is blurred repeatedly, each level twice
as coarse as the last, and the levels are mixed by weight. Fine levels carry
grain and cracks; coarse levels carry the overall form.

**What the levels do**, under Settings in Advanced mode, lists each level with
the pixel radius it actually covers for your image — the radii scale with the
source, so the same weights mean different things on a 512 and a 4K texture.

## Reset

The **↺** button next to Generate returns Height, Normal and Specular to their
defaults and rebuilds all three. It asks first, since hand-tuned settings are
lost.

It works through `property_unset`, so each setting returns to the default in
its own definition rather than to a value typed in twice. The source image and
the export settings are left alone.

## Credit and licence

The algorithms are ported from
[Materialize](https://github.com/BoundingBoxSoftware/Materialize) by Bounding
Box Software, which is GPL-3. This tool is therefore GPL-3, and so is the
add-on that contains it — see
[LICENSE](https://github.com/seto3d/void-tools/blob/main/LICENSE).

It was contributed as a standalone add-on and folded in here; see
[Thanks](../thanks.md).
