# Verification scripts

These drive a real Blender in background mode against a real Sollumz install.
Nothing is mocked: every check runs the actual operators and reads the actual
mesh data back, which is the only way to catch the things that go wrong here —
Sollumz renaming a helper, a shader parameter moving, an attribute landing on the
wrong domain.

```bash
blender -b --python tests/verify_decal_tool.py
```

Each script prints one `[PASS]`/`[FAIL]` line per check, ends with
`RESULT: n/n checks passed`, and exits non-zero if anything failed.

| Script | Covers |
| --- | --- |
| `verify_decal_tool.py` | the Decal Tool end to end — surface alignment under rotated and non-uniformly scaled sources, library scanning, coplanar merge, surface walking, thumbnails, failure cleanup |
| `border.py` | the decal's border ring: grid shape, alpha-0 outer edge, per-side Border Alpha, Edge Fade |
| `corner_alpha.py` | per-corner alpha on the inner rectangle, and that it can never resurrect the border |
| `params.py` | the shader value parameters each tool writes, and that the tools do not share them |
| `bundled.py` | each tool's `textures/` folder, colour space, embedded flag, and material separation |
| `vcolor.py` | the shared `Color 1` and shade-smooth, across all four tools |
| `panels.py` | **every** Seto panel's `draw()`, driven by hand against a validating stub layout, with Sollumz both available and missing. Blender only draws from the UI thread, so nothing else here would catch a panel that explodes on first redraw |
| `icons.py` | the add-on's own panel icons — that the PNGs ship, decode at 32×32, and that each header asks for its own rather than a built-in; plus the enums that must be greyed out when the library behind them is empty. `preview.icon_id` is always 0 in background mode, so the id itself cannot be checked here |
| `smoothedge.py` | Smooth Edge specifically |
| `fake_ao_bevel.py` | Fake AO's Bevel: that the strip's round lands on the source's round, that the chamfer inherits the wall's material rather than slot 0, that its UVs stay inside the wall's atlas island, that the source is beveled exactly once, and that a rebuild neither re-bevels the source nor adopts the chamfer face creation left bare |
| `surface_painter.py` | Surface Painter: that the paint mesh's UVs are one planar projection (an island would draw the decal twice), that dragging and wheel-resizing leave what you grabbed under the pointer at any size and rotation, and that Optimize crops and welds without moving the image |
| `drawable_uv.py` | Drawable-collection placement, and Fake Damage's UV scale/offset |
| `verify_coexist_export.py` | all tools registered together, their collections, and a real Sollumz YDR export |

## Run them against every Blender you support

Sollumz's API differs between versions, and so does its exporter — 2.9.0 dropped
the CodeWalker-XML exporter that 2.8.x has, for instance. A green run on one
version proves nothing about the other.

```bash
"/c/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --python tests/verify_decal_tool.py
"/d/Blender52/blender.exe" -b --python tests/verify_decal_tool.py
```

## Two traps worth knowing

**The scripts import the *installed* add-on, not this folder.** They add the repo
to `sys.path`, but if `seto_tools` is already enabled in that Blender, Python
resolves the installed copy first. After changing code, copy it into
`scripts/addons/seto_tools` **and verify the copy actually landed** before
trusting a run — a sync that silently fails looks exactly like a code regression.

**`bpy.ops` raises when an operator reports `{'ERROR'}`.** That is normal for
script calls; in the UI it is just a red status message. The scripts translate it
back into a return value rather than letting it abort the run.
