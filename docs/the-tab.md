# The tab

Everything lives in one N-panel tab, **Void Tools**, split into five sections
by what a tool works on. Twelve tools side by side would be a wall of
collapsible headers with no hint of which one to reach for; the sections are
the hint.

```
Void Tools
│
├── Updates                    only when there is one
│
├── Geometry                   builds new mesh along selected edges
│     ├── Edge Wear
│     └── Smooth Edge
│
├── Surface                    puts texture on a surface that already exists
│     ├── Ambient Occlusion
│     ├── Decal Tool
│     ├── Surface Painter
│     ├── Edge Dirt
│     └── Vertex Color Bake
│
├── Analysis                   reads the scene, changes nothing
│     ├── Density Check
│     ├── Texture Budget
│     └── Pre-Flight
│
├── Materials                  makes the texture, not the geometry
│     ├── Material Maker
│     └── Sign Glow
│
├── Dressing                   populates the room, rather than building it
│     └── Trash Scatter
│
└── Support                    report a bug, or fund the next tool
```

Ambient Occlusion sits under **Surface** rather than with the two Geometry
tools even though it builds the same kind of strip, because what it is *for* is
shading a surface — which is how you reach for it.

## Inside a tool

Every tool panel has the same shape, and it is worth knowing because it tells
you where to look:

**The tool's own panel** holds what has to be decided *before* there is
anything to look at — where the strip runs, which texture, which material — and
then the Create button. Nothing else.

**Child panels**, collapsed by default, hold what you set once and stop
thinking about.

**Selected …**, at the bottom, appears only when one of that tool's own objects
is active. This is where the finished thing is edited, and **every row in it is
live**: change it and the object rebuilds as you drag.

!!! tip "Two identical-looking blocks are not two live ones"

    Early versions listed every shape and fade setting twice — once in the
    create panel, once on the finished strip — and only the second copy did
    anything. The duplicates are gone. If a setting is in a create panel now,
    it is the default for the *next* thing you create; if it is under
    **Selected …**, it is live on the thing in front of you.

## Selected … in detail

Common to all four strip tools:

| Block | What it does |
| --- | --- |
| The header box | name, quad count, the source object, and any reason the last rebuild could not run |
| **Live Update** | off freezes the strip; **Rebuild Now** then applies changes in one go. Worth turning off on very heavy selections |
| **Shape** | width, surface offset, direction |
| **Fade** | across the strip, then along its run |
| **Position** | where the strip sits relative to where the tool puts it — see below |
| **Vertex Colour** | the RGB written to `Color 1` — a preset or your own swatch. See [choosing the colour](concepts.md#choosing-the-colour) |
| **Bevel** | rounds the source corner, the strip's own seam, or both |

### Position, and pinning

A strip is rebuilt from its source every time you touch a setting, and that
rebuild re-derives where it sits. Move a finished strip by hand and the next
rebuild used to snap it straight back.

**Pin Position** is how you stop that. Move the strip where you want it, press
the button, and every rebuild from then on puts it back there. **Clear Offset**
drops the pin and returns it to where the tool generates it. The Offset field
can also be typed into directly — it moves the strip without rebuilding its
mesh.

The pin means *"this far off my source"*, not *"at these coordinates"*. A
setting that legitimately moves the strip — a wider shelf re-centres its
origin — still moves it, carrying your offset along. That is deliberate:
otherwise widening a strip would bury it in the wall it runs along.

There is a button rather than the tool silently noticing you dragged the
object, because a rebuild moves the object legitimately several times per
slider drag, and there is no telling one from the other without a moment that
says *from here on, this one is mine*.

### Bevel

Two ticks, sharing Width, Segments and Profile Shape, both off by default:

- **Bevel Mesh** rounds the *source* object's corner with a live Bevel
  modifier. Nothing is destroyed — untick it and the modifier is removed and
  the source is exactly as it was found. Sollumz exports the evaluated object,
  so the round still reaches the YDR.
- **Bevel &lt;tool&gt;** rounds the strip's own seam, so the decal follows the
  round instead of cutting across it.

One modifier per source object serves every strip on it, at each strip's own
width: the modifier carries the widest, and every other strip's edges are
weighted down to their share. Each tool uses its own edge attribute, so an
Ambient Occlusion strip and an Edge Wear strip on one wall round their own
edges and not each other's.

Deleting a strip takes its modifier and its weights with it.

!!! note "Bevel needs a selected edge"

    A strip built from **Ground Level** runs along a contour that is not in the
    mesh, so there is no edge there to round — on either mesh. The panel says
    so instead of offering a tick that could not work.
