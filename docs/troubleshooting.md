# Troubleshooting

## The tab is not there at all

**Restart Blender** first — installing an add-on does not always finish until
you do.

If it is still missing after a restart, and you installed from a zip you built
yourself: the zip may have Windows path separators in its entry names, which
makes the whole add-on extract as a handful of files with backslashes in their
names on macOS and Linux. Build it with `python scripts/build_zip.py`, never
with PowerShell's `Compress-Archive`.

## "Sollumz not available"

Sollumz has to be installed **and** enabled **and** have its dependencies set
up. The shader definitions live in the dependencies, and every material these
tools build is a real Sollumz shader material.

The add-on tries every enabled add-on and lets an import decide, so it finds
Sollumz whether it was installed as a legacy folder, an extension, a GitHub
branch archive or a development build. If yours is named something nobody
anticipated, there is a **manual override** in the add-on preferences that
takes either the module name or the folder.

## A setting does nothing when I drag it

Check which panel you are in. A setting in a tool's **create panel** is the
default for the *next* thing you create. The live copy is under
**Selected …**, and appears only when one of that tool's objects is active.

Also check **Live Update** in the Selected panel: with it off, changes wait for
**Rebuild Now**.

## The strip snaps back onto the wall when I change a setting

That is a rebuild re-deriving where the strip sits. Move it where you want it
and press **Pin Position** — see
[Position and pinning](the-tab.md#position-and-pinning).

## The decal is invisible

`decal.sps` renders `Color 1 alpha × texture alpha`, so:

- check `Color 1` alpha is not 0 — Corner Alpha and Border Alpha both drive it
- if it is faint at alpha 1.0, the transparency is in the image itself

Surface Offset is the other suspect: at 0.0003 m a decal can still z-fight
against a surface at distance. Try 0.001–0.002.

## The source mesh got rounded and I did not ask for it

That is **Bevel Mesh**, on a strip you made. Untick it and the modifier is
removed and the mesh is exactly as it was found — nothing was cut.

If you deleted the strip and the round stayed, that was a bug fixed in a recent
version: deleting a strip now takes its modifier and weights with it. Remove
the leftover `Seto … Bevel` modifier by hand once, and it will not come back.

## Two strips on one wall are rounding each other's edges

Fixed. All four tools used to drive the source round through Blender's shared
`bevel_weight_edge` attribute, which **every** Bevel modifier limiting by
weight reads, so two tools on one wall each rounded the other's edges and the
rounds compounded. Each tool has its own attribute now. Update, then untick and
re-tick Bevel Mesh once on each strip to rewrite the weights.

## "No textures found in this category"

Press **Refresh Library**. The library is scanned on demand, not watched.

## Nothing crosses that height (Ground Level)

The panel says which of the three cases it is — the object is entirely below
the height, entirely above it, or lying flat at it. A flat plane is parallel to
the floor and never crosses it; pick the object that *stands on* the floor
instead.

## Reporting a bug

**Support → Report a Bug** at the foot of the tab fills in a GitHub issue with
what it knows — versions, what you were doing — and opens GitHub's own issue
page in your browser.

**It never sends anything itself.** You see the whole report before it travels,
and nothing leaves your machine unless you press submit on GitHub.

A report with a .blend attached is worth more than any amount of description.
