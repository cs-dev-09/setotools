# Density Check

**Analysis → Density Check**

The first of the three read-only tools. It builds nothing: **Analyze** grades
every mesh in scope against a triangle budget and shows the verdict as the
object's viewport colour, and **Finish Analysis** puts every colour back.

## Using it

1. Set **Scope** — *Visible* (every visible mesh in the view layer) or
   *Selected*.
2. Press **Analyze**.
3. Read the scene by colour, and click any object for its numbers.
4. **Finish Analysis** when you are done.

## What the colours mean

The scale is per **square metre of surface**, not per object, because a
triangle count only means something against the size of the thing spending it.

| Band | Meaning |
| --- | --- |
| < 0.25× | walls, glass, big surfaces |
| 0.25–1× | normal props — vanilla spend |
| 1–2× | detailed props |
| 2–4× | rich detail — hero territory |
| > 4× | hero props, or room to optimise |

**1× is what vanilla GTA spends on a mesh this size.** The scale is measured
from Franklin's house: of its 261 meshes, three quarters sit under 1× and only
hero props pass 4×.

!!! note "Red is a flag, not a mistake"

    A hero prop the player walks up to *should* be dense. The tool tells you
    where the money went, not what to delete. What it is good at is the
    opposite case: the background crate nobody looks at, quietly sitting at 6×.

## Settings

| Setting | Does |
| --- | --- |
| **Budget** | triangles a mesh may spend per square metre. 1000 by default — this is the 1× line |
| **Scope** | which objects Analyze measures |

## Per-object readout

Select an analyzed object and the panel gives its triangle count, its density
in tris/m², its multiple of the budget, and a line of advice.

An object with no measurable surface says so rather than reporting a
meaningless ratio — a mesh of loose edges has triangles and no area to divide
them by.
