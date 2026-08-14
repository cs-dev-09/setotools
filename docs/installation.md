# Installation

## Requirements

| | |
| --- | --- |
| Blender | 4.2 or newer — verified against 5.0.1 and 5.2.0 LTS |
| [Sollumz](https://docs.sollumz.org) | installed, enabled, **with its dependencies** |

Sollumz's dependencies matter: the shader definitions live there, and every
material Void Tools builds is a real Sollumz shader material. Without them the
tab draws a "Sollumz not available" notice instead of its buttons.

## Install — from the extension repository

The shorter way, and the one that keeps itself up to date. Blender 4.2 and
newer can take a repository URL and handle everything from there.

1. **Edit → Preferences → Get Extensions**
2. In the top-right dropdown: **Repositories → +  → Add Remote Repository**
3. Paste this URL, tick **Check for Updates on Start**, and press **Create**:

        https://seto3d.github.io/void-tools/repo/index.json

4. Back in **Get Extensions**, search for **Void Tools** and press **Install**.

That is the whole thing. Blender lists the version, tells you when a new one
is out and installs it — no zip, no folder, and nothing to remember. It also
shows what the add-on is allowed to reach before you install it: Void Tools
declares **network**, for the one thing it uses it for — asking github.com
whether there is a newer release.

## Install — from a zip

Unchanged, and still supported. Every release ships both artifacts.

1. Download `seto_tools.zip` from the
   [latest release](https://github.com/seto3d/void-tools/releases). **Do not
   unzip it.**
2. In Blender: **Edit → Preferences → Add-ons → Install from Disk**
3. Pick the zip, then tick the add-on to enable it.
4. **Restart Blender.**

The tools appear in the 3D viewport's N-panel, under a **Void Tools** tab,
whichever way you installed.

!!! info "Why two files"

    `seto_tools.zip` is a classic add-on: it carries its own folder and Blender
    copies it into `scripts/addons/`. `void_tools-<version>.zip` is an
    extension: its manifest sits at the archive root and Blender names the
    folder itself. One archive cannot be both, so both ship.

    **Do not install both.** They register the same panels and operators, and
    two copies of that in one Blender is the crash this add-on warns about
    below. Pick one; if you are switching, remove the other first.

!!! warning "Coming from the three separate add-ons"

    Void Tools used to ship as `seto_fake_ao`, `seto_fake_dmg` and
    `seto_decal_tool`. If any of them is still installed, **disable and remove
    it first** — they register the same operators and panels as this one, and
    Blender will not tell you which copy answered.

## Updating

**Installed from the repository?** Blender does it. **Get Extensions → Check
for Updates**, and the Updates panel in the tab stands aside and says so —
two updaters for one add-on can disagree, and this one could leave a second
copy behind.

**Installed from a zip?** The **Updates** panel at the top of the tab does it
from inside Blender: when a new release exists, its version shows on the panel
header and **Install Update** brings it in with your settings intact.

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
