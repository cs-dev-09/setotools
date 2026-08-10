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
| `panels.py` | **every** Seto panel's `draw()`, driven by hand against a validating stub layout, with Sollumz both available and missing. Blender only draws from the UI thread, so nothing else here would catch a panel that explodes on first redraw. Also the tab's layout contract (`shared/panel_layout.py`): that every settings child polls for Sollumz and declares its own `bl_order`, and that each tool's "Selected X" panel is last and open |
| `ground_strip.py` | Ambient Occlusion's **Ground Level** mode: that the strip runs along where the mesh crosses a world height and goes up only, that the source mesh is not touched, that the height survives a rotated and non-uniformly scaled object, and that an object nowhere near the level says so |
| `sollumz_detect.py` | finding Sollumz whatever it is called — a legacy folder, an extension, a GitHub branch archive, a development build, or a name nobody anticipated — plus the manual override, and that a fork missing Sollumz's `dependencies` module is still usable. `resolve()` is pure, so forks nobody here has installed are testable |
| `strip_settings.py` | the strip shape the Geometry section owns for Edge Wear and Smooth Edge: that no setting is offered twice down the tab, that a value typed into the section reaches both tools' operators and lands on the strip, and that a finished strip is never retro-fitted when the section changes afterwards |
| `icons.py` | the add-on's own panel icons — that the PNGs ship, decode at 32×32, and that each header asks for its own rather than a built-in; plus the enums that must be greyed out when the library behind them is empty. `preview.icon_id` is always 0 in background mode, so the id itself cannot be checked here |
| `smoothedge.py` | Smooth Edge specifically |
| `fake_ao_alpha.py` | Ambient Occlusion's **Alpha Bottom/Top**: that 1.0 at both ends is byte-for-byte a no-op, that the fade multiplies the across-fade rather than replacing it, that it follows world up on a rotated source, and that a run with no height is left alone instead of having its shelf faded |
| `fake_ao_bevel.py` | Ambient Occlusion's live Bevel: that the source mesh is modified rather than edited, that the round reaches the *evaluated* mesh Sollumz exports and matches the strip's, that switching it off puts the source back, that one modifier serves several strips at each one's own width, and that bevel weights land on strip edges and nowhere else |
| `pinned_position.py` | that a hand-moved strip stays where it was put, on all four strip tools: that Pin Position adopts the drag, that a rebuild no longer snaps the strip back onto its source, that repeated rebuilds accumulate no drift, that a setting which legitimately moves the strip carries the offset along rather than freezing it, and that Clear Offset returns it |
| `edge_dirt.py` | Edge Dirt, which shares Ambient Occlusion's geometry and rebuild: that a dirt strip carries its own per-object data and never claims to be an AO strip, that the shared rebuild reads the group it is handed, that the two Scene settings and materials stay apart, and that the rebuild guard is one flag for both |
| `surface_painter.py` | Surface Painter: that the paint mesh's UVs are one planar projection (an island would draw the decal twice), that dragging and wheel-resizing leave what you grabbed under the pointer at any size and rotation, and that Optimize crops and welds without moving the image |
| `drawable_uv.py` | Drawable-collection placement, and Edge Wear's UV scale/offset |
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
