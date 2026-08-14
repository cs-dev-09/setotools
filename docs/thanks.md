# Thanks

Void Tools is free, and it stays free. It is also built in the open, which
means it gets better when people turn up — with a pull request, with a bug
report carrying a .blend, or by funding the time it takes.

This page is where that is recorded.

## Contributors

People whose code is in the add-on you installed.

### [@cs-dev-09](https://github.com/cs-dev-09)

**The Vertex Colour picker** —
[#1](https://github.com/seto3d/void-tools/pull/1)

Every tool used to write one fixed green into `Color 1`. Changing it meant
going into Vertex Paint and doing it by hand, which quietly destroyed the alpha
channel unless you remembered to untick **Affect Alpha** — and the alpha is the
part the decal shaders actually blend by, so the damage was invisible until you
looked for it.

It is a preset list on the finished object now — Green, Red, White, Blue,
Yellow, or Custom with a swatch — and picking a colour cannot touch the alpha.
See [choosing the colour](concepts.md#choosing-the-colour).

The PR arrived tested, followed the project's conventions closely, and passed
the whole suite on both supported Blender versions on the first run. That is
rarer than it should be, and it is why it went in the same day.

**[Vertex Color Bake](tools/vertex-color-bake.md)** was theirs too — procedural
AO, dirt, grime and wear baked into `Color 1`, with the expensive raycasting
cached on the mesh so the sliders stay live. It is the one tool in the add-on
that writes to the object you select, which is not a slip: baked vertex colour
is mesh data and has nowhere else to live.

### [@gecu3d](https://github.com/gecu3d)

**[Material Maker](tools/material-maker.md)** — height, normal and specular
maps from a single diffuse image.

Written as a standalone add-on, with its own numpy image pipeline, its four
panels and a settings page deep enough to have a guide inside it, and handed
over whole. It came in as its own thing and became the **Materials** section:
the one tool here that makes a texture rather than putting one onto geometry.

The algorithms are ported from Bounding Box Software's Materialize, which is
why this add-on is GPL-3.


## Sponsors

### [@Zydrec](https://github.com/Zydrec)

The first person to fund this work through
[GitHub Sponsors](https://github.com/sponsors/seto3d).

A tool that is free either way is not owed that. It pays for the unglamorous
half — the day spent finding out that two tools' bevels were quietly rounding
each other's edges, the test suite that now catches it, this documentation.
Thank you.

## Being listed here

Sponsors are listed only if they are **public** on
[the sponsors page](https://github.com/sponsors/seto3d); a private sponsorship
stays private and is thanked privately.

Contributors are listed once their pull request is merged, since the commit is
public either way.

Either way: if you would rather not appear here, say so on
[the issues](https://github.com/seto3d/void-tools/issues) and you will be
removed, no reason needed.

## Standing on

Void Tools would not exist without [Sollumz](https://docs.sollumz.org), which
does the hard part — the shaders, the export, the whole GTA V pipeline inside
Blender. Everything here builds on top of it.
