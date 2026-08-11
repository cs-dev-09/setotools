"""Pre-Flight: that it finds what breaks after export, and nothing else.

The second half matters as much as the first. A checker that cries wolf is
worse than no checker, so every rule here is one vanilla GTA obeys - the
suite builds a deliberately clean object and asserts it comes back with
nothing to say about it.

It must also stay read-only: the whole promise is that it reports and the
author decides.
"""
import bpy, sys

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import seto_tools
if getattr(bpy.types, "SETO_PT_preflight_panel", None) is None:
    seto_tools.register()

from seto_tools.preflight import checks

scene = bpy.context.scene
settings = scene.seto_preflight
settings.scope = 'SELECTED'
view = bpy.context.view_layer


def deselect_all():
    for obj in view.objects:
        obj.select_set(False)


def clean_plane(name):
    """A plane with a material, a UV map and an applied scale - what vanilla
    looks like to every check here."""
    bpy.ops.mesh.primitive_plane_add(size=2)
    obj = bpy.context.active_object
    obj.name = name
    material = bpy.data.materials.new(name + "_mat")
    material.use_nodes = True
    obj.data.materials.append(material)
    return obj


def failing(obj):
    return {name for name, _severity, _message, _slot in checks.run(obj)}


print("=== a clean object has nothing said about it ===")
clean = clean_plane("pf_clean")
found = checks.run(clean)
check("no findings on a clean plane", not found, found)

print("=== each check catches its own thing ===")
no_uv = clean_plane("pf_no_uv")
while no_uv.data.uv_layers:
    no_uv.data.uv_layers.remove(no_uv.data.uv_layers[0])
check("a missing UV map is caught", "UV map" in failing(no_uv), failing(no_uv))

# A mesh with no material at all is deliberately NOT reported: an imported
# MLO is full of collision bounds and helpers that legitimately have none,
# and flagging every one buried the findings that mattered.
no_mat = clean_plane("pf_no_mat")
no_mat.data.materials.clear()
check("a mesh with no material is left alone entirely", not failing(no_mat),
      failing(no_mat))

empty_slot = clean_plane("pf_empty_slot")
empty_slot.data.materials.append(None)
check("an empty material slot is caught",
      "Empty slots" in failing(empty_slot), failing(empty_slot))

uniform = clean_plane("pf_uniform_scale")
uniform.scale = (2.0, 2.0, 2.0)
result = {n: s for n, s, _m, _slot in checks.run(uniform)}
check("uniform unapplied scale is caught", "Scale" in result, result)
check("but only as risky - it exports predictably",
      result.get("Scale") == checks.RISKY, result)

nonuniform = clean_plane("pf_nonuniform_scale")
nonuniform.scale = (2.0, 1.0, 1.0)
result = {n: s for n, s, _m, _slot in checks.run(nonuniform)}
check("non-uniform unapplied scale is caught as broken",
      result.get("Scale") == checks.BROKEN, result)

# N-gons are deliberately NOT a finding: Sollumz triangulates on export,
# so flagging one on every box-modelled asset is the noise that teaches
# people to ignore a checker.
ngon = clean_plane("pf_ngon")
mesh = ngon.data
mesh.clear_geometry()
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0.5, 1.5, 0), (0, 1, 0)],
                 [], [(0, 1, 2, 3, 4)])
mesh.uv_layers.new(name="UVMap 0")
check("an n-gon is not reported at all", not failing(ngon), failing(ngon))

png = clean_plane("pf_png")
png_image = bpy.data.images.new("pf_png_tex", width=64, height=64)
png_image.filepath_raw = "//textures/wall_diffuse.png"
node = png.data.materials[0].node_tree.nodes.new('ShaderNodeTexImage')
node.image = png_image
check("a PNG texture is caught", "Texture format" in failing(png),
      failing(png))
check("and the message names it",
      any("png" in m for _n, _s, m, _slot in checks.run(png)), checks.run(png))
check("and names the material holding it, which is where the fix happens",
      any(png.data.materials[0].name in m for _n, _s, m, _slot in checks.run(png)),
      checks.run(png))

dds = clean_plane("pf_dds")
dds_image = bpy.data.images.new("pf_dds_tex", width=64, height=64)
dds_image.filepath_raw = "//textures/wall_diffuse.dds"
node = dds.data.materials[0].node_tree.nodes.new('ShaderNodeTexImage')
node.image = dds_image
check("a DDS texture is fine", "Texture format" not in failing(dds),
      failing(dds))

# Surface Painter's own textures are generated, and Sollumz packs images
# into the .blend - neither has a format to judge.
packed = clean_plane("pf_packed")
packed_image = bpy.data.images.new("pf_packed_tex", width=64, height=64)
node = packed.data.materials[0].node_tree.nodes.new('ShaderNodeTexImage')
node.image = packed_image
check("an image with no file on disk is left alone",
      "Texture format" not in failing(packed), failing(packed))

loose = clean_plane("pf_loose")
loose.data.vertices.add(1)
check("a loose vertex is caught", "Loose vertices" in failing(loose),
      failing(loose))

print("=== every check has a remedy written for it ===")
# A finding with no route out is a complaint. The panel's How to fix button
# reads these, so a check added without one ships a dead button.
for name, _fn in checks.CHECKS:
    lines = checks.FIXES.get(name)
    check(f"{name} has fix steps", bool(lines), lines)
    if lines:
        check(f"{name}'s steps are numbered instructions",
              any(line.strip().startswith("1.") for line in lines), lines)
check("an unknown check still answers rather than raising",
      checks.fix_for("nothing like this")[0].startswith("No fix"))

print("=== only the mechanical repairs have a fixer ===")
# The three that are missing are missing on purpose: an unwrap, a shader
# choice and a DDS conversion are decisions or impossibilities, not
# procedures, and offering to do them badly is worse than explaining them.
for name in ("Loose vertices", "Zero-area faces", "Empty slots", "Scale"):
    check(f"{name} can be fixed", checks.can_fix(name))
for name in ("UV map", "Texture format"):
    check(f"{name} is left to the author", not checks.can_fix(name))
check("there is no material check at all any more",
      "Material" not in {n for n, _fn in checks.CHECKS},
      [n for n, _fn in checks.CHECKS])
check("every fixer belongs to a real check",
      set(checks.FIXERS) <= {n for n, _fn in checks.CHECKS},
      set(checks.FIXERS))

print("=== and each one actually repairs its own finding ===")
fix_loose_obj = clean_plane("pf_fix_loose")
fix_loose_obj.data.vertices.add(5)
deselect_all()
fix_loose_obj.select_set(True)
bpy.ops.seto.preflight_run()
verts_before = len(fix_loose_obj.data.vertices)
bpy.ops.seto.preflight_apply_fix(check="Loose vertices",
                                 object_name=fix_loose_obj.name)
check("Delete Loose removed exactly the loose ones",
      len(fix_loose_obj.data.vertices) == verts_before - 5,
      (verts_before, len(fix_loose_obj.data.vertices)))
check("and the finding left the list",
      "Loose vertices" not in {f.check for f in settings.findings},
      {f.check for f in settings.findings})
check("running the fixer again reports there is nothing left to do",
      not checks.fix_loose(fix_loose_obj, bpy.context)[0])

fix_dead = clean_plane("pf_fix_degenerate")
mesh = fix_dead.data
mesh.clear_geometry()
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                  (2, 0, 0), (2, 0, 0), (2, 0, 0)],
                 [], [(0, 1, 2, 3), (4, 5, 6)])
mesh.uv_layers.new(name="UVMap 0")
faces_before = len(mesh.polygons)
deselect_all()
fix_dead.select_set(True)
bpy.ops.seto.preflight_run()
bpy.ops.seto.preflight_apply_fix(check="Zero-area faces",
                                 object_name=fix_dead.name)
check("the zero-area face went and the real one stayed",
      len(fix_dead.data.polygons) == faces_before - 1,
      (faces_before, len(fix_dead.data.polygons)))

fix_slots = clean_plane("pf_fix_slots")
fix_slots.data.materials.append(None)
deselect_all()
fix_slots.select_set(True)
bpy.ops.seto.preflight_run()
bpy.ops.seto.preflight_apply_fix(check="Empty slots",
                                 object_name=fix_slots.name)
check("the unused empty slot was removed",
      len(fix_slots.material_slots) == 1, len(fix_slots.material_slots))

# The regression this suite existed without: removing a slot renumbers
# every face above it, and doing that by hand on top of what the RNA
# already does moved every face one material too far - the object came
# back wearing its neighbours' textures. What matters is not how many
# slots are left but that each face still has the material it had.
bpy.ops.mesh.primitive_cube_add(size=2)
shift = bpy.context.active_object
shift.name = "pf_slot_shift"
first = bpy.data.materials.new("pf_shift_first")
last = bpy.data.materials.new("pf_shift_last")
first.use_nodes = last.use_nodes = True
shift.data.materials.append(first)     # slot 0
shift.data.materials.append(None)      # slot 1 - empty, unused
shift.data.materials.append(last)      # slot 2
for index, poly in enumerate(shift.data.polygons):
    poly.material_index = 0 if index < 3 else 2
wore = [shift.data.materials[poly.material_index].name
        for poly in shift.data.polygons]

deselect_all()
shift.select_set(True)
view.objects.active = shift
bpy.ops.seto.preflight_run()
bpy.ops.seto.preflight_apply_fix(check="Empty slots",
                                 object_name=shift.name)
wears = [shift.data.materials[poly.material_index].name
         for poly in shift.data.polygons]
check("no face changed the material it wears", wore == wears, (wore, wears))
check("the empty slot in the middle is gone",
      all(slot.material is not None for slot in shift.material_slots),
      [s.material for s in shift.material_slots])
check("and both real materials survived",
      {m.name for m in shift.data.materials} == {first.name, last.name},
      [m.name for m in shift.data.materials])

# A slot faces actually point at must NOT be removed: dropping it shifts
# every index above and hands those faces a material nobody assigned.
used_slot = clean_plane("pf_fix_slots_used")
used_slot.data.materials.append(None)
for poly in used_slot.data.polygons:
    poly.material_index = 1
changed, message = checks.fix_empty_slots(used_slot, bpy.context)
check("a slot with faces on it is refused, with the reason",
      not changed and "faces" in message, (changed, message))
check("and nothing was removed", len(used_slot.material_slots) == 2)

fix_scale_obj = clean_plane("pf_fix_scale")
fix_scale_obj.scale = (2.0, 1.0, 1.0)
deselect_all()
fix_scale_obj.select_set(True)
view.objects.active = fix_scale_obj
bpy.ops.seto.preflight_run()
bpy.ops.seto.preflight_apply_fix(check="Scale",
                                 object_name=fix_scale_obj.name)
check("the scale came back to 1",
      all(abs(s - 1.0) < 1e-5 for s in fix_scale_obj.scale),
      tuple(fix_scale_obj.scale))
check("and it went into the mesh, not nowhere",
      abs(max(v.co.x for v in fix_scale_obj.data.vertices) - 2.0) < 1e-4,
      max(v.co.x for v in fix_scale_obj.data.vertices))

# Shared mesh data is the one case where applying moves objects nobody
# asked about, so the fixer refuses instead.
shared_a = clean_plane("pf_fix_scale_shared")
shared_b = bpy.data.objects.new("pf_fix_scale_shared_b", shared_a.data)
scene.collection.objects.link(shared_b)
shared_a.scale = (2.0, 1.0, 1.0)
changed, message = checks.fix_scale(shared_a, bpy.context)
check("a shared mesh is refused, with the reason",
      not changed and "share" in message, (changed, message))
check("and its scale was left alone", abs(shared_a.scale[0] - 2.0) < 1e-6)

print("=== the fixable rows come first, whatever else was found ===")
deselect_all()
for obj in (no_uv, no_mat, png, fix_loose_obj, used_slot):
    obj.select_set(True)
fix_loose_obj.data.vertices.add(3)     # give it a fixable finding again
view.objects.active = no_uv
bpy.ops.seto.preflight_run()
order = [(f.check, checks.can_fix(f.check)) for f in settings.findings]
fixable_positions = [i for i, (_c, ok) in enumerate(order) if ok]
other_positions = [i for i, (_c, ok) in enumerate(order) if not ok]
check("something fixable and something not were both found",
      fixable_positions and other_positions, order)
check("every fixable row sits above every other one",
      not fixable_positions or not other_positions
      or max(fixable_positions) < min(other_positions), order)

print("=== the list is filed under group headings ===")
# The panel draws a heading when the group changes, so every row of a
# group has to be contiguous - and the fixable ones still come first.
groups = [checks.group_for(f.check)[0] for f in settings.findings]
seen = []
for label in groups:
    if not seen or seen[-1] != label:
        check(f"{label} is drawn once, not split", label not in seen, groups)
        seen.append(label)
check("every check is filed somewhere named",
      all(checks.group_for(name)[0] != checks.DEFAULT_GROUP[0]
          for name, _fn in checks.CHECKS),
      [(n, checks.group_for(n)[0]) for n, _fn in checks.CHECKS])
check("an unknown check still gets a heading rather than nothing",
      checks.group_for("something new")[0] == checks.DEFAULT_GROUP[0])
check("every heading has an open/closed flag of its own",
      len(settings.expanded) == len(checks.GROUP_ORDER),
      (len(settings.expanded), len(checks.GROUP_ORDER)))
check("every group label is in the fixed order the flags are indexed by",
      all(label in checks.GROUP_ORDER
          for label, _icon in checks.GROUPS.values()),
      [v[0] for v in checks.GROUPS.values()])
check("an unknown heading falls on the last flag rather than off the end",
      checks.group_index("nothing like this") == len(checks.GROUP_ORDER) - 1)
check("they start closed - the counts are the summary",
      not any(settings.expanded), list(settings.expanded))
# Scale is BROKEN when non-uniform and RISKY when not; if severity sorted
# before the group, one heading would come out as two.
check("a group whose rows differ in severity stays in one block",
      groups.count("Scale issues") == 0
      or all(g == "Scale issues" for g in
             groups[groups.index("Scale issues"):
                    groups.index("Scale issues")
                    + groups.count("Scale issues")]),
      groups)

print("=== a finding in one material says which one ===")
png_rows = [f for f in settings.findings
            if f.object_name == png.name and f.check == "Texture format"]
check("the PNG finding carries its material slot",
      png_rows and png_rows[0].material_index == 0,
      [(f.check, f.material_index) for f in settings.findings])
check("a whole-object finding carries no slot",
      all(f.material_index == -1 for f in settings.findings
          if f.check in ("UV map", "Loose vertices")),
      [(f.check, f.material_index) for f in settings.findings])

deselect_all()
bpy.ops.seto.preflight_select(object_name=png.name, material_index=0)
check("jumping to it selects that material slot",
      png.active_material_index == 0, png.active_material_index)
check("and the object is active", view.objects.active is png)

print("=== Fix All is per heading, not over everything ===")
# One button over the whole list asks for two decisions at once. Each
# heading gets its own, and it must touch nothing outside itself.
scale_rows = {f.object_name for f in settings.findings
              if checks.group_for(f.check)[0] == "Scale issues"}
other_rows = [(f.object_name, f.check) for f in settings.findings
              if checks.group_for(f.check)[0] != "Scale issues"]
if scale_rows:
    bpy.ops.seto.preflight_fix_all(group="Scale issues")
    left = [(f.object_name, f.check) for f in settings.findings]
    check("every other heading was left exactly as it was",
          all(row in left for row in other_rows), (other_rows, left))
    check("and the scale rows it could fix are gone",
          not any(f.object_name in scale_rows
                  and checks.group_for(f.check)[0] == "Scale issues"
                  and not f.note for f in settings.findings),
          [(f.object_name, f.check, f.note) for f in settings.findings])

print("=== Fix All clears the mechanical ones and leaves the rest ===")
before_fixable = sum(1 for f in settings.findings if checks.can_fix(f.check))
before_other = sum(1 for f in settings.findings if not checks.can_fix(f.check))
check("there is something for it to do", before_fixable > 0, before_fixable)
bpy.ops.seto.preflight_fix_all()
after_fixable = sum(1 for f in settings.findings if checks.can_fix(f.check))
check("every fixable finding that could be repaired is gone",
      after_fixable < before_fixable,
      (before_fixable, after_fixable,
       [(f.object_name, f.check) for f in settings.findings]))
check("and the decisions were left exactly where they were",
      sum(1 for f in settings.findings
          if not checks.can_fix(f.check)) == before_other,
      [(f.object_name, f.check) for f in settings.findings])
check("the UV and texture findings are still listed",
      {"UV map", "Texture format"} <= {f.check for f in settings.findings},
      {f.check for f in settings.findings})

try:
    bpy.ops.seto.preflight_fix_all()
    check("a second Fix All has nothing left to do", False, "operator ran")
except RuntimeError as e:
    check("a second Fix All has nothing left to do",
          "fixed" in str(e).lower() or "Nothing" in str(e), e)

print("=== a refusal explains itself on its own row ===")
# The reported bug: two linked duplicates of an MLO prop, both with
# unapplied non-uniform scale. Fix and Fix All both decline - correctly,
# because applying would resize every object sharing the mesh - but the
# panel said nothing about why, so it read as a broken button.
link_a = clean_plane("pf_linked_a")
link_b = bpy.data.objects.new("pf_linked_b", link_a.data)
scene.collection.objects.link(link_b)
link_a.scale = (2.0, 1.0, 1.0)
link_b.scale = (2.0, 1.0, 1.0)

deselect_all()
link_a.select_set(True)
link_b.select_set(True)
view.objects.active = link_a
bpy.ops.seto.preflight_run()
check("both linked duplicates are flagged",
      sum(1 for f in settings.findings
          if f.object_name.startswith("pf_linked")) == 2,
      [(f.object_name, f.check) for f in settings.findings])

try:
    bpy.ops.seto.preflight_apply_fix(check="Scale", object_name=link_a.name)
except RuntimeError:
    pass          # CANCELLED reaches a script as an exception
row = next(f for f in settings.findings if f.object_name == link_a.name)
check("the row now says why it was not fixed", bool(row.note), row.note)
check("and the reason names the sharing", "share" in row.note, row.note)
check("the scale was left alone", abs(link_a.scale[0] - 2.0) < 1e-6)

reported = ""
try:
    bpy.ops.seto.preflight_fix_all()
    check("Fix All declines when every row declines", False, "operator ran")
except RuntimeError as error:
    reported = str(error)      # Python unbinds `error` at the end of except
    check("Fix All declines when every row declines",
          "declined" in reported, reported)
check("and it says why in the message rather than pointing at nothing",
      "share" in reported, reported)
check("every declined row carries its reason",
      all(f.note for f in settings.findings
          if f.object_name.startswith("pf_linked")),
      [(f.object_name, f.note) for f in settings.findings])

# A fake user is a user as far as .users is concerned, and Sollumz imports
# leave plenty of them. Counting it would refuse on a mesh only one object
# actually uses - which is the same silent dead button, on a file that has
# nothing wrong with it.
faked = clean_plane("pf_fake_user")
faked.data.use_fake_user = True
faked.scale = (2.0, 1.0, 1.0)
changed, message = checks.fix_scale(faked, bpy.context)
check("a fake user is not mistaken for another object", changed, message)
check("and the scale really was applied",
      all(abs(s - 1.0) < 1e-5 for s in faked.scale), tuple(faked.scale))

print("=== one answer can settle every row waiting on it ===")
# Six lamp posts sharing one mesh means six identical questions. Confirming
# once has to be able to do all of them - that is the whole point of the
# checkbox in the dialog.
shared_mesh = None
crowd = []
for index in range(3):
    obj = clean_plane(f"pf_crowd_{index}")
    if shared_mesh is None:
        shared_mesh = obj.data
    else:
        obj.data = shared_mesh
    obj.scale = (2.0, 1.0, 1.0)
    crowd.append(obj)

meshes_before = len(bpy.data.meshes)
deselect_all()
for obj in crowd:
    obj.select_set(True)
view.objects.active = crowd[0]
bpy.ops.seto.preflight_run()
check("all three are waiting on the same question",
      sum(1 for f in settings.findings
          if f.object_name.startswith("pf_crowd")) == 3,
      [(f.object_name, f.check) for f in settings.findings])

bpy.ops.seto.preflight_apply_fix(check="Scale", object_name=crowd[0].name,
                                 isolate_users=True, apply_to_all=True)
check("every one of them was applied",
      all(abs(s - 1.0) < 1e-5 for obj in crowd for s in obj.scale),
      [tuple(o.scale) for o in crowd])
check("and each really took the scale into its own mesh",
      all(abs(max(v.co.x for v in obj.data.vertices) - 2.0) < 1e-4
          for obj in crowd),
      [max(v.co.x for v in o.data.vertices) for o in crowd])
check("none of them still share a mesh",
      len({obj.data.name for obj in crowd}) == 3,
      [o.data.name for o in crowd])
# Two copies, not three: the last object reached is no longer sharing
# anything, so it keeps the original mesh.
check("only the copies that were needed were made",
      len(bpy.data.meshes) == meshes_before + 2,
      (meshes_before, len(bpy.data.meshes)))
check("and the rows are gone from the list",
      not [f for f in settings.findings
           if f.object_name.startswith("pf_crowd")],
      [(f.object_name, f.check) for f in settings.findings])

print("=== a fix for something with no fixer is refused ===")
try:
    bpy.ops.seto.preflight_apply_fix(check="UV map",
                                     object_name=fix_scale_obj.name)
    check("no automatic fix means no fix", False, "operator ran")
except RuntimeError as e:
    check("no automatic fix means no fix", "no automatic fix" in str(e), e)

print("=== the operator collects findings and stays read-only ===")
deselect_all()
for obj in (clean, no_uv, no_mat, nonuniform):
    obj.select_set(True)
view.objects.active = clean

before = {o.name: (len(o.data.vertices), tuple(o.scale),
                   len(o.data.materials)) for o in (clean, no_uv, no_mat,
                                                    nonuniform)}
bpy.ops.seto.preflight_run()

check("it ran", settings.has_run)
check("it checked all four", settings.checked == 4, settings.checked)
names = {f.object_name for f in settings.findings}
check("the clean object is not in the findings", "pf_clean" not in names,
      names)
check("the broken ones are", {"pf_no_uv", "pf_nonuniform_scale"} <= names,
      names)
check("and the materialless one is not", "pf_no_mat" not in names, names)
check("the fix operator is registered for the panel's button",
      hasattr(bpy.types, "SETO_OT_preflight_fix"))
check("severities came through",
      any(f.severity == checks.BROKEN for f in settings.findings))
after = {o.name: (len(o.data.vertices), tuple(o.scale),
                  len(o.data.materials)) for o in (clean, no_uv, no_mat,
                                                   nonuniform)}
check("nothing was fixed behind the user's back", before == after,
      (before, after))

print("=== the jump-to button, and clearing ===")
deselect_all()
bpy.ops.seto.preflight_select(object_name="pf_no_uv")
check("the named object is selected and active",
      view.objects.active is no_uv and no_uv.select_get())
try:
    bpy.ops.seto.preflight_select(object_name="pf_does_not_exist")
    check("a stale name is an error, not a crash", False, "operator ran")
except RuntimeError as e:
    check("a stale name is an error, not a crash", "no longer" in str(e), e)

bpy.ops.seto.preflight_clear()
check("clearing empties the list", len(settings.findings) == 0)
check("and forgets that a run happened", not settings.has_run)

print("=== an all-clear run is distinguishable from no run ===")
deselect_all()
clean.select_set(True)
bpy.ops.seto.preflight_run()
check("a clean scope still counts as having run", settings.has_run)
check("with no findings", len(settings.findings) == 0)

deselect_all()
try:
    bpy.ops.seto.preflight_run()
    check("empty scope is an error", False, "operator ran")
except RuntimeError as e:
    check("empty scope is an error", "No mesh objects" in str(e), e)

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
