# Development

## Layout

```
void_tools/
    __init__.py      registers the tools, in panel order
    shared/          code every tool uses
    textures/        textures shipped with the add-on
    fake_ao/         Ambient Occlusion
    edge_dirt/       its strip with its own texture and material
    fake_damage/     Edge Wear
    smooth_edge/
    decal_tool/
    surface_painter/
    density_checker/ the read-only triangle-budget heatmap
    texture_budget/  the same, for texture resolution and VRAM
    preflight/       the read-only export checklist
    updater/         the only code that can reach the network
    support/         bug report form and sponsor links
```

Display names and module names differ on purpose. A tester objected that "Fake
AO" and "Fake Damage" were odd names — everything in a game is fake — so the
tools are **Ambient Occlusion** and **Edge Wear** in the UI, while the packages
stay `fake_ao/` and `fake_damage/`, the operators stay `seto.create_fake_ao`
and `seto.create_fake_damage`, and the per-object data stays
`seto_fake_ao_data`. Renaming any of those would cost every strip in every
existing .blend its settings.

## Inside a tool

| File | Holds |
| --- | --- |
| `geometry.py` | pure mesh maths — no Sollumz, no `bpy.data` |
| `properties.py` | Scene-level settings |
| `object_settings.py` | per-object settings, and the live rebuild |
| `operators.py` | the Create operator |
| `ui.py` | the N-panel |

Surface Painter is the exception — it is the one tool that is not "select,
press Create", so its work lives in `shell.py`, `library.py`, `previews.py` and
`brush.py`. The analysis tools have no `object_settings.py`, because they build
nothing.

## Rules that are decided, not open

- **Source meshes are never modified** — with one stated exception. Every tool
  that *builds* something builds it as a separate object. **Vertex Color Bake**
  writes `Color 1` onto the selected mesh, because that is what baking vertex
  colour means; it is the only one, it is documented as such on its own page and
  on the front page, and adding a second exception is a decision, not a
  detail.
- **Live rebuilds never call `bpy.ops`.** They run from property update
  callbacks, where operators are unsafe — data API only.
- **Panels are drawn through `shared/panel_layout.py`**, not by hand. One
  vocabulary for the whole tab.
- **A strip's position is remembered, never derived** — see
  `shared/manual_offset.py`.
- **Every tool's source bevel has its own weight attribute.** Blender's
  `bevel_weight_edge` is the user's, and every Bevel modifier limiting by
  weight reads it.

## Tests

Verification scripts live in `tests/`. They drive a **real Blender in
background mode against a real Sollumz install** — there is no mocking, because
the things that break here are Sollumz renaming a helper, a shader parameter
moving, or an attribute landing on the wrong domain.

```bash
blender -b --python tests/verify_decal_tool.py
```

Each script prints one `[PASS]`/`[FAIL]` line per check, ends with
`RESULT: n/n checks passed`, and exits non-zero if anything failed.

**Run them against every Blender you support.** Sollumz's API differs between
versions and so does its exporter, so a green run on one proves nothing about
the other.

### Two traps worth knowing

**`bpy.ops` raises when an operator reports `{'ERROR'}`.** That is normal for
script calls; in the UI it is a red status line. The scripts translate it back.

**The scripts import the *installed* add-on, not the repo.** They add the repo
to `sys.path`, but if `void_tools` is already enabled in that Blender, Python
resolves the installed copy first. After changing code, copy it into
`scripts/addons/void_tools` and **verify the copy landed** before trusting a
red run — a sync that silently failed looks exactly like a code regression.

**Writing `obj.location` leaves `matrix_world` stale** until the depsgraph is
evaluated; writing `matrix_world` updates `location` at once. The UI never
notices; a script always does.

## The docs

This site is [MkDocs](https://www.mkdocs.org/) with the
[Material](https://squidfunk.github.io/mkdocs-material/) theme, built from
`docs/` and published to GitHub Pages by `.github/workflows/docs.yml` on every
push to `main`.

```bash
pip install -r docs/requirements.txt
mkdocs serve      # live preview on http://127.0.0.1:8000
mkdocs build --strict
```

The versions in `docs/requirements.txt` are **pinned on purpose**: MkDocs 2.0
removes the plugin system and rewrites theming with no migration path, so an
unpinned build would one day fail on a docs change that had nothing to do with
it.

`--strict` is what CI runs. It turns warnings into errors, so a nav entry
pointing at a file that does not exist fails the build instead of publishing a
broken page.
