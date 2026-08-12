# Installation

## Requirements

| | |
| --- | --- |
| Blender | 4.2 or newer — verified against 5.0.1 and 5.2.0 LTS |
| [Sollumz](https://docs.sollumz.org) | installed, enabled, **with its dependencies** |

Sollumz's dependencies matter: the shader definitions live there, and every
material Void Tools builds is a real Sollumz shader material. Without them the
tab draws a "Sollumz not available" notice instead of its buttons.

## Install

1. Download `seto_tools.zip` from the
   [latest release](https://github.com/seto3d/void-tools/releases). **Do not
   unzip it.**
2. In Blender: **Edit → Preferences → Add-ons → Install from Disk**
3. Pick the zip, then tick the add-on to enable it.
4. **Restart Blender.**

The tools appear in the 3D viewport's N-panel, under a **Void Tools** tab.

!!! warning "Coming from the three separate add-ons"

    Void Tools used to ship as `seto_fake_ao`, `seto_fake_dmg` and
    `seto_decal_tool`. If any of them is still installed, **disable and remove
    it first** — they register the same operators and panels as this one, and
    Blender will not tell you which copy answered.

## Updating

The **Updates** panel at the top of the tab does it from inside Blender: when a
new release exists, its version shows on the panel header and **Install
Update** brings it in with your settings intact.

See [Updating](updating.md) for what the version check sends, and how to turn
it off.

## Where your settings live

Two kinds, and the difference matters when you open a new file:

**Add-on preferences** — remembered across files, restarts and updates. The
decal library folder and the Surface Painter library folder are both here,
along with the Sollumz override and the update-check switch. Reach them at
**Edit → Preferences → Add-ons → Void Tools**.

**Scene settings** — saved in the .blend, per file. Everything in a tool's
create panel is one of these: it is the starting point for the next thing you
create, and nothing more.

**Per-object settings** — saved on the generated object itself. Everything in a
**Selected …** panel is one of these, and every one of them is live.

## Building the zip yourself

If you are working from a clone rather than a release:

```bash
python scripts/build_zip.py
```

That produces the same `seto_tools.zip`. Do not build it with PowerShell's
`Compress-Archive` — it writes Windows path separators into the entry names,
which Blender's installer splits on `/` only, so the add-on extracts as a
handful of files with backslashes in their names on macOS and Linux and the tab
never appears. The script checks its own output for exactly that before it
reports success.
