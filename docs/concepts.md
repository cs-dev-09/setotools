# What every tool shares

The things that are true of all of them, so the tool pages do not have to
repeat them.

## Your mesh is never modified

Select, press a button, and a **separate object** is created. Surface Painter
reaches the same end differently — it spawns a paint mesh over the surface and
you brush on that — but the promise is identical: delete what the tool made and
the original is exactly as it was.

The one place a tool affects the source is **Bevel Mesh**, and it does it with
a modifier rather than by cutting the mesh, precisely so it stays reversible.
The analysis tools change the viewport colour of the objects they grade, and
**Finish Analysis** puts every one of them back.

## What you generate stays live

A generated object stores what it was built from — the source, the edges or the
face, and every setting — so changing a value in its **Selected …** panel
regenerates it in place.

It is the feel of dragging a value on a modifier, with one important
difference: the result is **real mesh data**. Nothing needs applying before
export, and nothing is procedural at export time.

The strip tools re-read their source edges on every rebuild, so editing the
wall moves the strip with it. A decal instead carries the surface frame it was
placed on, which is what lets it slide across a face and walk onto the
neighbouring one.

## Sorted output

Inside a Sollumz Drawable, what a tool generates lands in the **Drawable's own
collection**, beside the rest of the asset, and is parented into the hierarchy.

Outside one, each tool files into its own collection, created on first use:
`fake_ao`, `edge_dirt`, `fake_dmg`, `smooth_edge`, and `decals` with one child
per decal-library category.

Generated objects are named after the tool that made them —
`ambient_occlusion_003`, `edge_wear_003` — with collections to match.

## One vertex colour

Every tool writes `Color 1`: RGB `#00B200` by default, alpha 1.0 at the centre
of a strip fading to 0.0 at its outer edge.

**The alpha is the blend factor.** Sollumz renders `decal.sps` as
`Color 1 alpha × texture alpha`, so alpha 0 is invisible and 1.0 is as opaque
as the texture itself allows. If something looks too faint at 1.0, the
transparency is in the image, not in the tool.

### Choosing the colour

**Selected … → Vertex Colour** picks the RGB per object: Green, Red, White,
Blue, Yellow, or Custom with a swatch. The default stays green, so existing
work is unaffected.

Setting it here rather than by hand matters for one specific reason: changing a
vertex colour in Vertex Paint mode destroys the alpha unless you remember to
untick **Affect Alpha** — and the alpha is the part that does the work. Going
through the panel cannot touch it.

!!! note "What the colour is good for"

    The value is exported and survives the round trip — a strip exported to YDR
    and opened in CodeWalker shows the colour it was given. Whether the game's
    own shader tints the decal by it has not been confirmed here, so treat it
    as a way of colour-coding your own generated geometry, and check in game
    before relying on it for anything visible.

!!! note

    `Color 1` is a byte colour: values quantise to 1/255. Two alphas that
    should match can differ by one byte and be correct.

## UVs by construction, not by unwrapping

The strip tools lay their UVs out from the geometry in metres, then fit the
island into the 0–1 square with both axes scaled by the same factor. Nothing is
solved, so an arc, a 90° turn and a straight run all give the same clean
rectangle — no unwrap step, no straightening afterwards, and a live rebuild
produces final UVs rather than a placeholder.

Islands are fitted standing vertically, so every generated strip unwraps the
same way round.

## Shaded smooth

Everything generated is set smooth, so a strip shows no hard band at its quad
boundaries. It is applied to the generated object only, through the data API,
so it survives a live rebuild.

## Material reuse

Materials are reused per tool and per texture — `seto_fakeao`,
`seto_fakedamage`, `seto_smoothedge`, `seto_edgedirt`,
`seto_decal_mat_<texture>`. Edge Wear and Smooth Edge share a shader, so
matching on the shader instead of the name would make them fight over each
other's materials.

**A reused material is never rewritten.** Hand tweaks survive.

Every tool offers a **Material** choice between reusing an existing material
for that texture and always creating a new one.

## Bundled textures, where they are small

Ambient Occlusion, Edge Dirt, Edge Wear and Smooth Edge each ship their one
texture in the tool's own folder and wire it in automatically — drop a file
there and it is picked up.

The Decal Tool and Surface Painter instead read a **library folder you point
them at**. Their textures are whole sheets: they would be most of the download,
and anyone doing this work already has a library of their own.

## Nothing leaves your machine

The only code in the add-on that can reach the network is the updater, which
asks GitHub for the latest release. The test suite enforces that. The bug
report form fills in a GitHub issue page and opens it in your browser — it
never sends anything itself, and you see the whole report before it travels.
