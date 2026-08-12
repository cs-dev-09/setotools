# Seto Tools

One Blender add-on for GTA V / FiveM asset authoring, built on
[Sollumz](https://docs.sollumz.org).

Every authoring tool builds **separate** geometry and never modifies the mesh
you point it at. The analysis tools only read. Delete what a tool made and your
asset is exactly as it was — that is the one rule with no exceptions anywhere
in this add-on.

[Install it](installation.md){ .md-button .md-button--primary }
[Browse the tools](the-tab.md){ .md-button }

## The ten tools

| Tool | What it makes | Built from |
| --- | --- | --- |
| [Edge Wear](tools/edge-wear.md) | Chipped-edge damage strips | selected edges |
| [Smooth Edge](tools/smooth-edge.md) | Normal-map strips that make a hard edge read as rounded | selected edges |
| [Ambient Occlusion](tools/ambient-occlusion.md) | Ambient-occlusion corner decals | selected edges, or a world height |
| [Decal Tool](tools/decal-tool.md) | Surface-aligned decal planes from your own library | selected faces |
| [Surface Painter](tools/surface-painter.md) | Dirt, grime and graffiti brushed onto a surface | a paint mesh over the object |
| [Edge Dirt](tools/edge-dirt.md) | The same strip as Ambient Occlusion, carrying a dirt texture | selected edges |
| [Density Check](tools/density-check.md) | A triangle-budget heatmap graded against vanilla GTA | the scene, read-only |
| [Texture Budget](tools/texture-budget.md) | The same heatmap for texture resolution, plus VRAM cost | the scene, read-only |
| [Pre-Flight](tools/pre-flight.md) | The export test you would otherwise run in game | the scene, read-only |
| [Material Maker](tools/material-maker.md) | Height, normal and specular maps | one diffuse image |

## Why it is shaped like this

GTA's own assets get their wear from **decals**, not from geometry: a chipped
kerb is a plane with a chipped-edge texture on it, floating a few millimetres
off a perfectly clean kerb. That is what these tools build. It keeps the source
mesh clean and re-editable, it keeps the triangle count where the budget wants
it, and it is what the engine is built to render.

Three things follow from that, and they run through everything here:

**Your mesh is never modified.** Not on the first press, not on the hundredth.
Where a tool has to affect the source — rounding a corner so a strip can sit on
it — it uses a Bevel *modifier*, which is reversible and which Sollumz bakes
into the export anyway.

**What you generate stays live.** A finished strip remembers the object and the
edges it was built from and every setting used, so dragging a value in
**Selected Strip** rebuilds it as you drag. It feels like a Geometry Nodes
modifier, except the result is real mesh data that needs no applying before
export.

**It is Sollumz-native.** Correct `UVMap 0` and `Color 1` attributes, real
Sollumz shader materials, and generated objects parented into the Drawable when
the source belongs to one.

## Requirements

- **Blender 4.2+** — verified against 5.0.1 and 5.2.0 LTS
- **[Sollumz](https://docs.sollumz.org)**, enabled, with its dependencies
  installed

Every panel says so plainly, and refuses to draw its buttons, when Sollumz is
not there.

## Getting help

- [Troubleshooting](troubleshooting.md) covers what usually goes wrong first
- **Support → Report a Bug** at the foot of the tab fills in a GitHub issue
  from where the problem happened — read
  [what it sends](troubleshooting.md#reporting-a-bug) before you press it
- [Issues on GitHub](https://github.com/seto3d/setotools/issues)

## Free, and better for the people who turn up

Seto Tools costs nothing and stays that way. It is improved by pull requests,
by bug reports with a .blend attached, and by the people who fund the time —
see [Thanks](thanks.md).
