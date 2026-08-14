"""The Density Check, end to end - the budget maths and the measuring.

What matters here, in the order it broke elsewhere in this add-on before:
that the measurement is taken from the **evaluated** mesh in **world** space
(a modifier or a scale must change the verdict, because it changes what
Sollumz exports); that Analyze touches only the Object - colour and ID
properties - and never the mesh; and that Finish restores the user's own
colour even after Analyze has run twice over it.
"""
import bpy, sys

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import void_tools
if getattr(bpy.types, "SETO_PT_density_checker_panel", None) is None:
    void_tools.register()

from void_tools.density_checker import geometry, operators
from void_tools.shared import viewport_grade as vg

print("=== the maths, before any scene is involved ===")
check("the budget grows with the square root of area",
      geometry.budget(1000.0, 4.0) == 2000.0)
check("ratio is spend over entitlement",
      geometry.ratio(200, 1000.0, 4.0) == 0.1)
check("no area means no ratio", geometry.ratio(3, 1000.0, 0.0) is None)
check("density is triangles over area", geometry.density(200, 4.0) == 50.0)
check("a quarter of budget pins to green", geometry.fraction(0.25) == 0.0)
check("four times budget pins to red", geometry.fraction(4.0) == 1.0)
mid = geometry.fraction(1.0)
check("exactly on budget sits at yellow - vanilla is the midpoint",
      abs(mid - 0.5) < 1e-9, mid)
check("no surface reads as the worst case", geometry.fraction(None) == 1.0)

def near(a, b):
    return all(abs(x - y) < 1e-9 for x, y in zip(a, b))

check("0 is green", near(geometry.colour(0.0), geometry.GREEN))
check("1 is red", near(geometry.colour(1.0), geometry.RED))
check("0.5 is yellow", near(geometry.colour(0.5), geometry.YELLOW))

scene = bpy.context.scene
settings = scene.seto_density_checker
view = bpy.context.view_layer


def deselect_all():
    for obj in view.objects:
        obj.select_set(False)


def analyze():
    return bpy.ops.seto.density_analyze()


print("=== a sparse plane and a dense grid, graded apart ===")
bpy.ops.mesh.primitive_plane_add(size=2)          # 4 m², 2 triangles
sparse = bpy.context.active_object
sparse.name = "density_sparse"
sparse.color = (0.2, 0.3, 0.4, 1.0)               # the user's own colour

bpy.ops.mesh.primitive_grid_add(x_subdivisions=100, y_subdivisions=100, size=2)
dense = bpy.context.active_object                  # 4 m², 20 000 triangles
dense.name = "density_dense"

sparse_verts = len(sparse.data.vertices)

deselect_all()
sparse.select_set(True)
dense.select_set(True)
settings.scope = 'SELECTED'
analyze()

check("the raw measurements land on the object",
      sparse[operators.TRIS_PROP] == 2
      and abs(sparse[operators.AREA_PROP] - 4.0) < 1e-3,
      (sparse.get(operators.TRIS_PROP), sparse.get(operators.AREA_PROP)))
check("the sparse plane went green", sparse.color[1] > sparse.color[0],
      tuple(sparse.color))
check("the dense grid went red - ten times its budget",
      dense.color[0] > dense.color[1], tuple(dense.color))
check("the source mesh was not touched",
      len(sparse.data.vertices) == sparse_verts)
check("the shared grading session names this tool",
      scene.seto_grade.owner == "DENSITY", scene.seto_grade.owner)

print("=== world space and the evaluated mesh, not the raw one ===")
# The same plane four times as wide covers four times the floor - if the
# area comes back unchanged, it was measured in local space and a scaled
# wall lies about its budget.
bpy.ops.mesh.primitive_plane_add(size=2)
wide = bpy.context.active_object
wide.name = "density_wide"
wide.scale = (4.0, 1.0, 1.0)

deselect_all()
wide.select_set(True)
analyze()
check("scale changes the verdict: the area is world-space",
      abs(wide[operators.AREA_PROP] - 16.0) < 1e-2,
      wide.get(operators.AREA_PROP))

bpy.ops.mesh.primitive_plane_add(size=2)
modified = bpy.context.active_object
modified.name = "density_modified"
subsurf = modified.modifiers.new("subsurf", 'SUBSURF')
subsurf.levels = 2

deselect_all()
modified.select_set(True)
analyze()
check("a modifier changes the verdict: the evaluated mesh is what is measured",
      modified[operators.TRIS_PROP] == 32, modified.get(operators.TRIS_PROP))

print("=== triangles with no surface ===")
loose_mesh = bpy.data.meshes.new("density_loose")
loose_mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [])
loose = bpy.data.objects.new("density_loose", loose_mesh)
scene.collection.objects.link(loose)

deselect_all()
loose.select_set(True)
analyze()
check("no measurable surface is flagged, not divided by",
      loose[operators.AREA_PROP] == 0.0)
check("and drawn as the worst case", loose.color[0] > loose.color[1],
      tuple(loose.color))

print("=== Finish restores what the user had, even after two runs ===")
deselect_all()
sparse.select_set(True)
analyze()   # the second run over sparse - must not adopt green as "saved"
bpy.ops.seto.density_clear()

check("the user's own colour came back",
      all(abs(a - b) < 1e-5 for a, b in zip(sparse.color, (0.2, 0.3, 0.4, 1.0))),
      tuple(sparse.color))
check("every measurement property is gone",
      all(operators.TRIS_PROP not in o and operators.AREA_PROP not in o
          and vg.SAVED_COLOUR_PROP not in o
          for o in (sparse, dense, wide, modified, loose)))
check("the session is free again", scene.seto_grade.owner == "")

print("=== the two grading tools do not lose each other's colours ===")
# Texture Budget paints into the same object colours. Starting it while a
# density analysis is up must hand the *user's* colour back at the end, not
# the green the Density Check had painted over it.
deselect_all()
sparse.select_set(True)
analyze()
bpy.context.scene.seto_texture_budget.scope = 'SELECTED'
bpy.ops.seto.texture_analyze()
check("the second tool took the session over",
      scene.seto_grade.owner == "TEXTURE", scene.seto_grade.owner)
check("and the first tool's measurements were cleared",
      operators.TRIS_PROP not in sparse)
bpy.ops.seto.texture_clear()
check("finishing still returns the user's own colour",
      all(abs(a - b) < 1e-5 for a, b in zip(sparse.color, (0.2, 0.3, 0.4, 1.0))),
      tuple(sparse.color))

print("=== an empty scope refuses instead of pretending ===")
deselect_all()
try:
    analyze()
    check("empty scope is an error", False, "operator ran")
except RuntimeError as e:
    check("empty scope is an error", "No mesh objects" in str(e), e)

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
