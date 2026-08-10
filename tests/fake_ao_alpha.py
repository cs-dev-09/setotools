"""Alpha Bottom / Alpha Top - the fade ALONG the run, not across it.

Alpha Center and Alpha Outer fade the strip from the corner out onto the wall.
These two fade it from one end of the run to the other, so a corner does not
have to arrive at the floor or the ceiling at full strength.

Three things worth pinning, all of them easy to get wrong:
  * 1.0 at both ends must leave the strip byte-for-byte as it was,
  * the fade multiplies the across-fade rather than replacing it,
  * bottom and top are the BUILDING's, so a rotated source still fades toward
    the real floor rather than along its own local Z.
"""

import bpy, sys
from mathutils import Vector
sys.path.append(r"D:\SetoClaude\setotools")
R = []
def check(n, c, d=""):
    R.append((bool(c), n, d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import seto_tools
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    seto_tools.register()
from seto_tools.fake_ao import geometry, operators
from seto_tools.shared import vertex_color

CENTER = vertex_color.DEFAULT_ALPHA_CENTER
OUTER = vertex_color.DEFAULT_ALPHA_OUTER
# Color 1 is BYTE_COLOR, so every value lands on the nearest 1/255.
TOLERANCE = 2.0 / 255


def corner_cube(rotate_x=0.0):
    """A cube with its +X/+Y vertical edge selected. `rotate_x` turns the whole
    object over, to prove the fade follows the world and not the object."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.active_object
    if rotate_x:
        cube.rotation_euler = (rotate_x, 0.0, 0.0)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for edge in cube.data.edges:
        a, b = (cube.data.vertices[i].co for i in edge.vertices)
        if abs(a.x - 1) < 1e-4 and abs(b.x - 1) < 1e-4 and abs(a.y - 1) < 1e-4 and abs(b.y - 1) < 1e-4:
            edge.select = True
    bpy.ops.object.mode_set(mode='EDIT')
    return cube


def create(rotate_x=0.0, **settings):
    cube = corner_cube(rotate_x)
    settings.setdefault("width", 0.4)
    settings.setdefault("bevel_enabled", False)
    try:
        bpy.ops.seto.create_fake_ao(**settings)
    except RuntimeError as e:
        print("  (err", e, ")")
    bpy.ops.object.mode_set(mode='OBJECT')
    strips = [o for o in bpy.data.objects if o.name.startswith(("ambient_occlusion_", "fake_ao_"))]
    return cube, (strips[-1] if strips else None)


def by_world_height(strip):
    """{rounded world Z: sorted set of alphas at that height}."""
    attr = strip.data.attributes["Color 1"]
    out = {}
    for index, loop in enumerate(strip.data.loops):
        world = strip.matrix_world @ strip.data.vertices[loop.vertex_index].co
        out.setdefault(round(world.z, 2), set()).add(round(attr.data[index].color_srgb[3], 3))
    return {height: sorted(values) for height, values in out.items()}


def same(got, expected):
    return len(got) == len(expected) and all(abs(a - b) <= TOLERANCE for a, b in zip(got, expected))


# --- 1. Untouched by default -------------------------------------------------
cube, strip = create()
if not check("strip created", strip is not None):
    sys.exit(1)
baseline = by_world_height(strip)
check("the run has a bottom and a top to fade between", len(baseline) == 2, str(sorted(baseline)))
check("out of the box every height carries the plain across-fade",
      all(same(v, sorted({CENTER, OUTER})) for v in baseline.values()), str(baseline))

cube, strip = create(alpha_bottom=1.0, alpha_top=1.0)
check("1.0 at both ends changes nothing at all",
      by_world_height(strip) == baseline, str(by_world_height(strip)))

# --- 2. Fading out toward the floor -----------------------------------------
cube, strip = create(alpha_bottom=0.0, alpha_top=1.0)
heights = by_world_height(strip)
low, high = min(heights), max(heights)
check("the bottom of the run goes to zero", same(heights[low], [0.0]), str(heights[low]))
check("and the top is left at full strength",
      same(heights[high], sorted({CENTER, OUTER})), str(heights[high]))

# --- 3. It multiplies the across-fade, it does not replace it ----------------
cube, strip = create(alpha_bottom=0.5, alpha_top=1.0)
heights = by_world_height(strip)
low, high = min(heights), max(heights)
check("half at the bottom halves BOTH the corner and the shelf value",
      same(heights[low], sorted({CENTER * 0.5, OUTER * 0.5})),
      f"{heights[low]} vs {sorted({CENTER*0.5, OUTER*0.5})}")

# --- 4. Both ends at once ----------------------------------------------------
cube, strip = create(alpha_bottom=0.0, alpha_top=0.0)
heights = by_world_height(strip)
check("zero at both ends leaves nothing behind on a two-vertex run",
      all(same(v, [0.0]) for v in heights.values()), str(heights))

# --- 5. Bottom and top are the building's, not the object's -----------------
# Tipped on its side, the corner edge runs along world Y and has no height at
# all, so there is no bottom or top to fade between. The STRIP still spans two
# heights - its shelf climbs the wall - which is exactly the trap: measuring
# the vertices rather than the run would read that as a bottom and a top and
# fade the shelf. So the test is that the fade changes nothing, not that the
# strip is flat.
import math  # noqa: E402
cube, strip = create(rotate_x=math.radians(90.0), alpha_bottom=1.0, alpha_top=1.0)
flat_baseline = by_world_height(strip)
cube, strip = create(rotate_x=math.radians(90.0), alpha_bottom=0.0, alpha_top=1.0)
check("a run with no height is left alone rather than faded across its shelf",
      by_world_height(strip) == flat_baseline,
      f"{by_world_height(strip)} vs {flat_baseline}")

# Tipped 45 degrees the same edge still rises, and the low end still fades.
cube, strip = create(rotate_x=math.radians(45.0), alpha_bottom=0.0, alpha_top=1.0)
tilted = by_world_height(strip)
low, high = min(tilted), max(tilted)
check("a tilted source fades toward the real floor, not its own local Z",
      same(tilted[low], [0.0]) and same(tilted[high], sorted({CENTER, OUTER})),
      f"low {tilted[low]}, high {tilted[high]}")

# --- 6. Live on the finished strip ------------------------------------------
cube, strip = create()
data = strip.seto_fake_ao_data
data.alpha_bottom = 0.0
heights = by_world_height(strip)
check("dragging Alpha Bottom on the strip rebuilds it live",
      same(heights[min(heights)], [0.0]), str(heights[min(heights)]))
data.alpha_bottom = 1.0
check("and putting it back restores exactly what was there",
      by_world_height(strip) == baseline, str(by_world_height(strip)))

# --- 7. The helper on its own ------------------------------------------------
from mathutils import Matrix  # noqa: E402
from seto_tools.shared import run_fade  # noqa: E402

# This tool grew the along-run fade first and carried its own copy of it for a
# while. One implementation now, re-exported here - if the copy comes back,
# these checks stop proving anything about what the other two tools run.
check("the along-run fade is the shared one",
      geometry.local_up_axis is run_fade.local_up_axis)

check("local_up_axis reads world up out of an unrotated matrix",
      (geometry.local_up_axis(Matrix.Identity(4)) - Vector((0, 0, 1))).length < 1e-6)
tipped = Matrix.Rotation(math.radians(90.0), 4, 'X')
check("and out of a rotated one",
      abs(geometry.local_up_axis(tipped).normalized().dot(Vector((0, -1, 0)))) > 0.999,
      str(geometry.local_up_axis(tipped)))
scaled = Matrix.Diagonal((1.0, 1.0, 4.0, 1.0))
check("a non-uniform scale does not tip the axis over",
      (geometry.local_up_axis(scaled).normalized() - Vector((0, 0, 1))).length < 1e-6,
      str(geometry.local_up_axis(scaled)))

failed = [r for r in R if not r[0]]
print("\n" + "=" * 60); print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
