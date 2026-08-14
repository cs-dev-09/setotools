# Trash Scatter

**Dressing → Trash Scatter**

Select a floor, press one button, get a floor that looks lived on: vanilla
GTA litter scattered where litter really lands, and the grime underneath it.

It does two things at once, from one seed:

- **The litter.** Cigarette butts, paper, crushed cans, bottles, food
  wrappers — real GTA props, each registered as an **MLO entity** on your
  interior's archetype, so the game streams the actual prop and your
  interior's triangle count, texture memory and draw calls do not move.
- **The floor dirt.** A flat grime overlay across the same area — which is
  how vanilla does it. Of the game's 377 interiors, **176** carry
  hand-authored dirt sheets like `bkr_int01_cm3dirtfloor` or
  `ex_int_warem_stains`; almost none scatter grime props. Trash Scatter
  builds that sheet procedurally.

Your floor mesh is never touched.

## Watch it work

<video controls muted playsinline preload="none"
       poster="../../images/trash-scatter-blender-poster.jpg"
       style="width:100%;border-radius:.2rem">
  <source src="https://github.com/seto3d/void-tools/releases/download/media/trash-scatter-blender.mp4" type="video/mp4">
  <a href="https://github.com/seto3d/void-tools/releases/download/media/trash-scatter-blender.mp4">Download the video</a>
</video>

*Scattering a tiled interior floor: the litter, the grime under it, and the
sliders driving both.*

<video controls muted playsinline preload="none"
       poster="../../images/trash-scatter-interior-poster.jpg"
       style="width:100%;border-radius:.2rem">
  <source src="https://github.com/seto3d/void-tools/releases/download/media/trash-scatter-interior.mp4" type="video/mp4">
  <a href="https://github.com/seto3d/void-tools/releases/download/media/trash-scatter-interior.mp4">Download the video</a>
</video>

*The same tool on a warehouse floor — the one the in-game shots were taken
in.*

## Making one

1. Select the floor object and enter **Edit Mode**.
2. Select the faces you want dressed.
3. Press **Scatter**.

In Object Mode it uses every upward-facing face of the active object
instead. Faces that do not face up are dropped either way, so a selection
that runs up a wall will not put a beer bottle halfway up it.

Press **Scatter** again to replace the layout — it never stacks a second
run on top of the first. **Clear Scatter** removes the props, the dirt
sheet and the entity rows together: the active floor's, or every floor's
when the active object has none of its own.

## The prop library

The add-on ships **no prop meshes** — they are Rockstar's, not ours. It
ships their names and their measured sizes, which is what placement and
export actually need.

!!! question "What if I do not have a prop library?"

    **Everything still works.** Every prop lands as a wireframe box the
    exact size of the real archetype, in the right place, at the right
    scale, registered as the right entity. The **export is identical** and
    the game shows the real prop. Only your viewport shows boxes.

    So it is safe to work this way — you are choosing between previewing
    the litter and previewing its footprint.

To see the real models in Blender, point the add-on at a folder of
`.blend` files whose **objects are named after GTA archetypes**
(`prop_paper_ball`, `ng_proc_sodacan_01a`, …).

1. **Preferences → Add-ons → Void Tools → Prop Library** — pick the folder.
   Subfolders are searched too.
2. Press the **Rescan** button beside it, and let it finish.
3. Scatter again. The report says how many props came back with real
   models.

### Building one with Sollumz

You do not have to find a library — **recent Sollumz builds one for you**,
from your own extracted game files:

1. In Sollumz's add-on preferences, add a **Shared Assets** directory —
   a name and a path. That is where the libraries get written.
2. In the 3D view: **Sollumz Tools → Asset Library → Build Asset
   Library**. Point it at a folder holding your extracted `.ytyp` files
   and their assets, pick that Shared Assets directory as the output, and
   let it run — it spawns Blender subprocesses and works through them.
3. Point Void Tools' **Prop Library** at that same Shared Assets
   directory and press **Rescan**.

Those libraries drop in without any conversion: their objects carry the
archetype names Trash Scatter matches on, and where Sollumz leaves a
Drawable as an empty with the mesh parented under it, the scan takes the
mesh.

Any other library organised the same way works just as well — the ones
that circulate in the FiveM mapping scene generally are.

!!! warning "Rescan never runs by itself"

    Indexing a real library means opening every `.blend` in it to read its
    object names — on a few hundred files that is **minutes**. Doing that
    behind your back would freeze the Scatter button or a slider drag, so
    it only ever happens when you press Rescan. The panel says so when a
    folder is set but not indexed yet.

    Press it again after you add or rename anything in the library.

A prop the library does not have simply stays a box, next to the ones it
does have.

## Layout

| Setting | What it does |
| --- | --- |
| **Preset** | *Trash* — litter: butts, paper, cans, bottles, wrappers. *Dirt & Leaves* — drifts of dead leaves and the odd small stone. |
| **Density** | Props per square metre. Spacing may place fewer when they genuinely do not fit. |
| **Edge Bias** | How strongly the litter gathers along the edges of the selected area — the walls and corners, where it really collects. 0 spreads it evenly. |
| **Prop Scale** | Every prop's base size. 1.0 is the prop's real in-game size; litter does not grow when the room does, but the choice is yours. |
| **Scale Jitter** | Random size variation around that. |
| **Topple** | How many standing props — bottles, cans, cups — lie knocked over on their side. It ships at **1.0**: litter standing to attention reads as staged. |
| **Clustering** | 0 spreads the litter; toward 1 it gathers into heaps around a few seeded spots, which themselves obey Edge Bias. Butts by a doorway rather than one per square metre. |
| **Seed** | Same seed, same layout — for the props *and* the dirt. Change it to re-roll everything. |

Two rules run underneath all of it, and neither is a setting:

- **Nothing lands under furniture.** A short ray goes up from every
  candidate spot; if it hits a table top, a crate or a counter, that spot
  is dropped.
- **The litter follows the grime.** With Floor Dirt on, the same noise that
  darkens the overlay decides where props are likely to land, so the dirty
  patches collect trash and the clean stretches stay sparse. One scene
  rather than two random layers.

## Floor Dirt

| Setting | What it does |
| --- | --- |
| **Floor Dirt** | Whether the overlay is built at all. |
| **Amount** | 0 is a clean floor; 1 is a floor you could write your name in. At 0 the sheet is removed. |
| **Blotch Size** | How large the grime patches are. It also decides how fine the sheet's mesh needs to be — a bigger blotch needs fewer vertices to describe. |

The overlay is a separate object, parented to your floor, floating 4 mm
above it, wearing a decal material with the pattern in `Color 1`'s alpha —
the same channel every other tool here writes, and the one `decal.sps`
blends by.

### Optimize

**Optimize Dirt** crops the sheet to where the grime actually is and drops
the vertices the pattern does not need. It is
[Surface Painter](surface-painter.md)'s optimizer, and like it, the texture
is never touched: the result looks the same and weighs a fraction.

**Tolerance** is how far the pattern may drift in exchange for geometry.
It defaults to `0.08` — much looser than Surface Painter's `0.02`, because
a grime sheet is noise rather than a stroke someone drew on purpose. On a
20 × 14 m floor at the default: **3033 faces down to 291**, 70% of them
quads. Tighten it to `0.02` to keep the pattern exact and most of the mesh
with it; the report always says which tolerance produced which count.

Changing Tolerance rebuilds nothing on its own — otherwise it would undo
the optimisation it is about to ask for. Press the button.

!!! tip "Optimize last"

    Any change that rebuilds the sheet gives you an unoptimized one again.
    Dial the look in first, then optimize.

## Selected Scatter

Select a floor you have already scattered and its own copy of every setting
appears, **live**: drag Density, Edge Bias, Topple, Clustering, Amount or
Blotch Size and the floor rebuilds as you let go. **Live Update** turns that
off; **Re-Scatter** does it by hand.

Re-Scatter is also the answer after you move or resize the floor itself —
no property changed, so nothing rebuilt, but the area did.

## The entities

Each prop is added to your MLO archetype's entity list with its
`linked_object` set, so Sollumz exports its transform from the Blender
object. The archetype is found without any selection help: the one whose
asset is your floor or one of its parents, else the one selected in
Sollumz's ytyp panel, else — because most files hold one interior — the
file's only MLO archetype.

Entities are attached to the room whose bounds contain them, and **never**
to a room called `limbo`. That is GTA's outside; its bounds usually swallow
the whole interior and the engine caps how much may hang off it.

If no archetype is found the props are still placed, and the report says
exactly which part is missing — no YTYP, no MLO archetype in it, or several
and none of them obviously yours.
