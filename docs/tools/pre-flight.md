# Pre-Flight

**Analysis → Pre-Flight**

The export test you would otherwise run in game. It checks every mesh in scope
for the handful of things that pass quietly in Blender and fail after export,
lists what it found with a button to jump to each object, and **fixes nothing
on its own** — what to do about an unapplied scale is your call.

## Using it

1. Set **Scope** — *Visible* or *Selected*.
2. Press **Analyze**.
3. Work down the findings. Each one has **How to fix**, and some have a **Fix**
   button.
4. **Clear** when you are done.

Findings are grouped — Scale issues, Material issues, Geometry issues — and the
panel says how many of them **would not draw correctly in game**, which is the
line worth caring about.

## What it checks

| Check | Why it matters |
| --- | --- |
| **No UV map** | the texture has nowhere to land |
| **Scale not applied** | normals go through the inverse-transpose of the matrix, so a non-uniform scale that was never applied lights wrongly after export |
| **Texture format** | GTA streams DDS: mip-mapped and block-compressed. A PNG has neither, so it costs more memory and shimmers at distance |
| **Empty material slots** | faces assigned to a material index that is not there |
| **Zero-area faces** | they cost a triangle each and draw nothing |
| **Loose vertices** | vertices in no face at all — they export, and draw nothing |

## Fixing

Some findings have a **Fix** button, and a **Fix all** on the group header.
Others deliberately do not:

**Texture format** has no Fix, because Blender cannot write DDS — the
conversion happens outside it.

**Scale** warns before it acts when the mesh is shared with other objects.
Applying scale writes to the mesh, so every object using it moves. If the
instancing is deliberate, cancel.

Where a fix was offered and not applied, the finding says **Not fixed** and
why, rather than quietly disappearing.

!!! tip "Run it before every export, not after the first bug report"

    Every one of these is silent in Blender. The whole point of the tool is
    that the feedback loop for them is otherwise: export, build, load the
    server, walk to the prop, notice it looks wrong.
