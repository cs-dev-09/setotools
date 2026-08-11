# Texture Budget

**Analysis → Texture Budget**

The same idea as [Density Check](density-check.md), for textures. **Analyze**
colours every mesh by the texture resolution it carries **for its physical
size**, and totals what the scene costs in texture memory. **Finish Analysis**
puts the colours back.

Resolution on its own says nothing. A 2048² map is extravagant on a door handle
and thin on a warehouse wall — what matters is texels per metre of surface, and
that is what this grades.

## Using it

1. Set **Target** and **Scope**.
2. Press **Analyze**.
3. Read the scene by colour; select an object for its numbers.
4. **Finish Analysis**.

## Settings

| Setting | Does |
| --- | --- |
| **Texels / Metre** | texture pixels a metre of surface should carry. 1024 by default |
| **Scope** | *Visible* or *Selected* |

!!! info "What vanilla actually spends"

    GTA tops out at 1024, and most of it is 256. Franklin's house comes to
    roughly **55 MB** of texture: 592 of its 601 textures are 512² or smaller,
    the other nine reach 1024, and none go past it.

    If your prop needs 2048 to look right, the question is usually whether the
    prop is too big for one texture rather than whether the texture is too
    small.

## Per-object readout

For the selected object: its effective texture size over its surface area, the
texels/metre that works out to, the multiple of your target, and a line of
advice. When it is over, the panel also names **the square texture size that
would hit the target** — so the fix is a number, not a guess.

Objects carrying no texture say so instead of being graded.

## Scene total

The panel reports the number of textures, the total memory, and the largest
single texture by name.

The total is an estimate at **1 byte per pixel including mips** — that is what
block-compressed DDS with a full mip chain costs in practice. It is meant for
comparing your scene against the vanilla figure above, not for predicting
exactly what the engine allocates.
