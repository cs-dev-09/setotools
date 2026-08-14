# Vertex Color Bake

**Surface → Vertex Color Bake**

Procedural wear baked straight into `Color 1`: ambient occlusion, dirt in the
concave edges, grime on the up-facing surfaces, wear on the exposed corners,
noise, a gradient, and a fake directional shadow — stacked, each with its own
strength.

This is the cheapest wear there is. It costs no texture, no extra object and no
draw call: the colour rides on vertices the mesh already has.

!!! warning "This one writes to your mesh"

    Every other tool here builds a separate object and leaves your source
    untouched. This one cannot: baked vertex colour **is** mesh data, so it
    creates and fills a `Color 1` layer on the object you selected.

    It is one undo away, and deleting the `Color 1` attribute in the Object Data
    properties removes it entirely. But it is the one tool in the add-on that
    changes the thing you point it at, and it is worth knowing that before you
    press it on an asset you have not saved.

## Using it

1. Select one or more mesh objects.
2. Tick the layers you want and set their strengths.
3. Press **Generate Vertex Color**.

Every object in the selection is baked, not just the active one.

## The layers

| Layer | What it darkens or lightens | Default |
| --- | --- | --- |
| **AO** | raytraced ambient occlusion — the creases and the undersides | on, 0.8 |
| **Edge Dirt** | concave edges, where dirt actually collects | on, 0.1 |
| **Floor Grime** | up-facing surfaces, by how flat and how high they are | on, 0.2 |
| **Edge Wear** | convex edges, where paint gets knocked off | on, 0.1 |
| **Random** | per-vertex noise, so nothing reads as machine-flat | on, 0.1 |
| **Fake Shadow** | a directional shadow at an angle and altitude you set | off |
| **Linear Gradient** | top to bottom, for a general falloff | off |

**Base Color** is what all of it multiplies down from — white unless you want
the whole object tinted.

## Why it is fast

The expensive parts — the AO raycasts and the edge-angle pass — are **cached on
the mesh**. Dragging a strength slider only re-blends what was already
measured, so the sliders stay responsive on a dense mesh instead of
re-raytracing the object on every mouse move.

The cache is per object. Change the geometry and the next Generate measures it
again.

## Where it fits

`Color 1` is the same attribute the strip tools write, and the same one
`decal.sps` reads its blend factor from. On an ordinary GTA material the RGB
here is what shades the mesh; on a decal shader the alpha is what matters. This
tool targets the RGB and blends the alpha rather than overwriting it, so an
object that already carries a decal setup is not flattened by a bake.

## Credit

Contributed by [@cs-dev-09](https://github.com/cs-dev-09) — see
[Thanks](../thanks.md).
