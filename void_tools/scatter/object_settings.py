"""Per-floor scatter settings, and the rebuild they drive live.

After a floor has been scattered once it carries its own copy of the
settings (`Object.seto_scatter_data`), drawn in the "Selected Scatter"
panel, and dragging any of them rebuilds the layout in place - the same
live-control convention every strip tool follows. The rebuild never calls
`bpy.ops` (it runs from property callbacks, where operators are unsafe)
and never reads the floor's face selection: the scattered region is
captured **once**, at Scatter time, as local-space triangles in ID
properties on the floor. That is what makes the live rebuild safe in any
mode - the mesh is never touched again, and a floor moved or rotated later
carries its litter along, because the region is re-transformed through the
floor's current matrix on every rebuild.
"""

import math

import bpy
from mathutils import Vector

from . import catalog, dirt, geometry, library

# ID properties on the floor object. The region is stored local-space so
# the floor can move; SRC_PROP on each proxy names the floor it belongs to.
TRIS_PROP = "seto_scatter_tris"        # flat floats, 9 per triangle
BOUNDS_PROP = "seto_scatter_bounds"    # flat floats, 6 per boundary segment
SRC_PROP = "seto_scatter_src"
# What the standing dirt sheet was built from, so a rebuild that cannot
# change it does not pay for it. On the overlay object.
DIRT_STAMP = "seto_scatter_dirt_stamp"

COLLECTION_NAME = "Trash Scatter"

# One guard for every rebuild path: a rebuild fired from a property update
# must not re-enter itself through anything it writes.
_rebuilding = False


def is_rebuilding():
    return _rebuilding


def has_region(obj):
    """Whether this object has ever been scattered - the panel's poll."""
    return obj is not None and TRIS_PROP in obj


def store_region(floor, triangles_local, boundaries_local):
    floor[TRIS_PROP] = [v for tri in triangles_local for co in tri for v in co]
    floor[BOUNDS_PROP] = [v for seg in boundaries_local for v in seg]


def _load_region(floor):
    """The stored region, transformed through the floor's current matrix."""
    matrix = floor.matrix_world
    flat = list(floor.get(TRIS_PROP, ()))
    triangles = []
    for i in range(0, len(flat) - 8, 9):
        triangles.append(tuple(
            matrix @ Vector(flat[i + j * 3:i + j * 3 + 3]) for j in range(3)))
    flat = list(floor.get(BOUNDS_PROP, ()))
    boundaries = []
    for i in range(0, len(flat) - 5, 6):
        a = matrix @ Vector(flat[i:i + 3])
        b = matrix @ Vector(flat[i + 3:i + 6])
        boundaries.append((a.x, a.y, b.x, b.y))
    return triangles, boundaries


def _proxy_box(name):
    """The bounding-box stand-in, for a prop the library cannot dress."""
    mesh_name = f"seto_scatter_box_{name}"
    mesh = bpy.data.meshes.get(mesh_name)
    if mesh is not None:
        return mesh
    bb_min, bb_max = catalog.PROPS[name]
    x0, y0, z0 = bb_min
    x1, y1, z1 = bb_max
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata(verts, [], faces)
    return mesh


def _scatter_collection(context, floor):
    """The collection the proxies live in, under the floor's own collection."""
    parent = floor.users_collection[0] if floor.users_collection \
        else context.scene.collection
    existing = bpy.data.collections.get(COLLECTION_NAME)
    if existing is not None:
        linked = {c.name for c in context.scene.collection.children_recursive}
        if existing.name not in linked:
            try:
                parent.children.link(existing)
            except RuntimeError:
                pass  # already linked in this exact parent
        return existing
    coll = bpy.data.collections.new(COLLECTION_NAME)
    parent.children.link(coll)
    return coll


def find_mlo_archetype(scene, floor):
    """(ytyp, archetype, problem) - the archetype or the reason there is none.

    Three answers, most honest first: an MLO archetype whose asset is the
    floor or an ancestor of it; the archetype selected in Sollumz's ytyp
    panel, if it is an MLO; and - because most working files hold exactly
    one interior - the file's only MLO archetype.

    When all three fail, `problem` says exactly which precondition is
    missing. "No MLO archetype was found" cost a field tester two round
    trips because it did not say whether the file had no ytyp, a ytyp with
    no MLO, or two MLOs it could not choose between.
    """
    ytyps = getattr(scene, "ytyps", None)
    if ytyps is None:
        return None, None, "Sollumz's ytyp data is not available"
    if len(ytyps) == 0:
        return None, None, "this file has no YTYP yet - create one in " \
                           "Sollumz's ytyp panel"

    ancestors = []
    node = floor
    while node is not None:
        ancestors.append(node)
        node = node.parent

    mlos = []
    for ytyp in ytyps:
        for archetype in ytyp.archetypes:
            if archetype.type != 'sollumz_archetype_mlo':
                continue
            mlos.append((ytyp, archetype))
            if archetype.asset is not None and archetype.asset in ancestors:
                return ytyp, archetype, ""

    index = getattr(scene, "ytyp_index", 0)
    if 0 <= index < len(ytyps):
        ytyp = ytyps[index]
        archetype = getattr(ytyp, "selected_archetype", None)
        if archetype is not None and \
                archetype.type == 'sollumz_archetype_mlo':
            return ytyp, archetype, ""

    if len(mlos) == 1:
        ytyp, archetype = mlos[0]
        return ytyp, archetype, ""
    if not mlos:
        return None, None, "the file's YTYPs contain no MLO archetype - " \
                           "create one in Sollumz's ytyp panel"
    return None, None, f"the file has {len(mlos)} MLO archetypes and none " \
                       f"matches this floor - select yours in the ytyp panel"


def _room_id_for(archetype, world_position):
    """The room whose bounds hold this point, as the enum string, or None.

    The room called "limbo" is never a candidate. It is GTA's outside -
    every MLO's room 0 - its bounds usually swallow the whole interior,
    and the engine caps how many entities may attach to it (Sollumz 2.9
    enforces the cap with a popup per entity, which litter would trip
    forty times over). Trash belongs in the room it lies in, never
    outside the interior.
    """
    rooms = getattr(archetype, "rooms", None)
    if not rooms:
        return None
    candidates = [room for room in rooms
                  if room.name.strip().lower() != "limbo"]
    if not candidates:
        return None

    local = world_position
    asset = getattr(archetype, "asset", None)
    if asset is not None:
        local = asset.matrix_world.inverted_safe() @ world_position

    for room in candidates:
        lo, hi = room.bb_min, room.bb_max
        if lo[0] <= local.x <= hi[0] and lo[1] <= local.y <= hi[1] \
                and lo[2] <= local.z <= hi[2]:
            return str(room.id)
    return str(candidates[0].id)


def delete_run(scene, source_name):
    """Remove every proxy scattered on `source_name`, and its entity rows."""
    doomed = [obj for obj in bpy.data.objects
              if obj.get(SRC_PROP) == source_name]
    if not doomed:
        return 0

    doomed_set = set(doomed)
    ytyps = getattr(scene, "ytyps", None)
    if ytyps:
        for ytyp in ytyps:
            for archetype in ytyp.archetypes:
                entities = archetype.entities
                for index in range(len(entities) - 1, -1, -1):
                    if entities[index].linked_object in doomed_set:
                        entities.remove(index)

    count = len(doomed)
    meshes = {obj.data for obj in doomed if obj.data is not None}
    for obj in doomed:
        bpy.data.objects.remove(obj)
    for mesh in meshes:
        # Only the per-prop boxes are disposable; a library mesh stays
        # cached for the next rebuild even when nothing wears it right now.
        if mesh.users == 0 and mesh.name.startswith("seto_scatter_box_"):
            bpy.data.meshes.remove(mesh)
    return count


# How high above a sample the obstacle ray reaches. Table tops, chairs,
# crates and counters all start below this; ceilings almost never do.
OBSTACLE_HEIGHT = 1.0


def _without_obstructed(context, floor, placements):
    """Drop the placements that sit under furniture.

    A short ray straight up from each sample: whatever it hits within a
    metre - a table top, a crate, a counter - claims that spot, and a
    bottle inside a table leg was the last piece of visible randomness
    (field-tested). Walls are vertical and parallel to the ray, the floor
    is below the origin, and the previous run's proxies are already
    deleted by the time this runs, so the only hits left are genuine
    obstacles. Any failure to raycast (no view layer in some headless
    contexts) keeps every placement - litter through a table is better
    than no litter at all.
    """
    try:
        depsgraph = context.evaluated_depsgraph_get()
    except Exception:
        return placements

    up = Vector((0.0, 0.0, 1.0))
    kept = []
    for placement in placements:
        origin = placement.position + Vector((0.0, 0.0, 0.03))
        try:
            hit, _loc, _nrm, _idx, hit_obj, _mat = context.scene.ray_cast(
                depsgraph, origin, up, distance=OBSTACLE_HEIGHT)
        except Exception:
            return placements
        if hit and hit_obj is not None and hit_obj != floor \
                and hit_obj.get(dirt.MARKER) is None \
                and hit_obj.get(SRC_PROP) is None:
            continue
        kept.append(placement)
    return kept


class RebuildResult:
    __slots__ = ("placed", "dressed", "archetype", "problem")

    def __init__(self, placed, dressed, archetype, problem=""):
        self.placed = placed
        self.dressed = dressed
        self.archetype = archetype
        self.problem = problem


def rebuild(floor, context=None):
    """Replace this floor's layout from its stored region and settings.

    Data API only - property callbacks land here. Returns a RebuildResult,
    or None when the floor has no stored region.
    """
    global _rebuilding
    if _rebuilding:
        return None
    context = context or bpy.context
    scene = context.scene

    triangles, boundaries = _load_region(floor)
    if not triangles:
        return None

    data = floor.seto_scatter_data
    preset = catalog.PRESETS[data.preset]
    items = [(weight, catalog.footprint_radius(name),
              catalog.lying_radius(name), catalog.is_standing(name))
             for name, weight in preset]

    # The litter follows the grime: the dirt overlay's own noise field
    # biases where props land, so the dark patches collect trash and the
    # clean stretches stay sparse - one look, not two overlaid ones.
    field = None
    if data.dirt_enabled and data.dirt_amount > 0.0:
        def field(point, _data=data):
            return dirt.value_noise(point.x / _data.dirt_scale,
                                    point.y / _data.dirt_scale, _data.seed)

    # Built once and shared by the litter and the dirt sheet: both ask
    # "how far to the nearest wall" thousands of times per rebuild.
    boundary_index = geometry.as_boundary_index(boundaries)

    placements = geometry.scatter(
        triangles, boundary_index, items,
        data.density, data.seed, data.edge_bias, data.scale_jitter,
        data.prop_scale, data.topple, field, data.clustering)

    _rebuilding = True
    try:
        delete_run(scene, floor.name)

        # Obstacles are tested only now, with the previous run already
        # gone: filtering before the delete let last run's own bottles
        # "obstruct" this run, and every rebuild drifted from the last
        # (caught by the determinism test, on the first try).
        placements = _without_obstructed(context, floor, placements)

        # The dirt overlay rides the same region, seed and edge bias as
        # the litter - vanilla's own overlay sheets are why it exists at
        # all (176 of the game's 377 interiors carry one). A failure here
        # (no Sollumz, no bundled texture) costs the overlay, never the
        # props.
        #
        # Rebuilt only when something it depends on actually moved: the
        # sheet is the expensive half of a rebuild, and dragging Density
        # or Topple has nothing to do with it. The stamp is what makes
        # the prop sliders feel live.
        try:
            if data.dirt_enabled and data.dirt_amount > 0.0:
                # A string, not a float array: the stamp mixes ints and
                # floats, and Blender ID properties do not keep a mixed
                # sequence as written.
                stamp = (f"{data.dirt_amount:.4f}|{data.dirt_scale:.4f}"
                         f"|{data.edge_bias:.4f}|{data.seed}"
                         f"|{len(floor.get(TRIS_PROP, ()))}")
                existing = next((o for o in bpy.data.objects
                                 if o.get(dirt.MARKER) == floor.name), None)
                if existing is None or existing.get(DIRT_STAMP) != stamp:
                    overlay = dirt.build_overlay(
                        context, floor, triangles, boundary_index,
                        data.seed, data.dirt_amount, data.edge_bias,
                        data.dirt_scale)
                    if overlay is not None:
                        overlay[DIRT_STAMP] = stamp
            else:
                dirt.remove_overlay(floor.name)
        except Exception:
            dirt.remove_overlay(floor.name)

        if not placements:
            return RebuildResult(0, 0, None)

        index = library.get_index(context)
        needed = {preset[p.item][0] for p in placements}
        meshes = library.fetch_meshes(needed, index)
        ytyp, archetype, problem = find_mlo_archetype(scene, floor)
        collection = _scatter_collection(context, floor)

        dressed = 0
        for placement in placements:
            name = preset[placement.item][0]
            mesh = meshes.get(name)
            if mesh is not None:
                dressed += 1
            obj = bpy.data.objects.new(name, mesh or _proxy_box(name))
            # A toppled prop is a +90° roll around local X; XYZ euler
            # applies Z last, so the yaw still spins it flat on the
            # floor. Its resting height comes from the rolled bounding
            # box, not the upright one.
            if placement.lying:
                lift = catalog.ground_offset_lying(name)
                roll = math.pi / 2.0
            else:
                lift = catalog.ground_offset(name)
                roll = 0.0
            obj.location = placement.position + Vector(
                (0.0, 0.0, lift * placement.scale))
            obj.rotation_euler = (roll, 0.0, placement.yaw)
            obj.scale = (placement.scale,) * 3
            if mesh is None:
                obj.display_type = 'WIRE'
            obj[SRC_PROP] = floor.name
            collection.objects.link(obj)

            if archetype is not None:
                entity = archetype.new_entity()
                entity.archetype_name = name
                entity.linked_object = obj
                room_id = _room_id_for(archetype, placement.position)
                if room_id is not None:
                    try:
                        entity.attached_room_id = room_id
                    except TypeError:
                        pass  # room list changed under us; entity still lands

        data.entity_status = "" if archetype is not None else problem
        return RebuildResult(len(placements), dressed, archetype, problem)
    finally:
        _rebuilding = False


# ---- live-update debounce ----------------------------------------------
# A slider fires its update callback on every mouse move, and a rebuild of
# a hundred objects per mouse move is a laggy drag (field-tested). The
# callback therefore only *marks* the floor and arms a short timer; the
# rebuild runs once, when the hand has stopped. Background Blender has no
# event loop to run timers, so tests take the immediate path.

_pending = set()
_timer_armed = False

# Long enough to swallow a drag's intermediate values, short enough to
# read as "live" when the mouse stops.
_DEBOUNCE_S = 0.25


def _flush_pending():
    global _timer_armed
    _timer_armed = False
    names = list(_pending)
    _pending.clear()
    for name in names:
        floor = bpy.data.objects.get(name)
        if floor is not None and has_region(floor):
            try:
                rebuild(floor)
            except Exception:
                pass  # a broken rebuild must not kill the timer system
    return None  # one shot


def _on_setting_changed(self, _context):
    global _timer_armed
    if _rebuilding or not self.live_update:
        return
    floor = self.id_data
    if not has_region(floor):
        return
    if bpy.app.background:
        rebuild(floor)
        return
    _pending.add(floor.name)
    if not _timer_armed:
        _timer_armed = True
        bpy.app.timers.register(_flush_pending, first_interval=_DEBOUNCE_S)


class SETO_PG_scatter_data(bpy.types.PropertyGroup):
    """The floor's own copy of the scatter settings, live once seeded."""

    preset: bpy.props.EnumProperty(
        name="Preset", description="Which family of vanilla props is placed",
        items=catalog.PRESET_ITEMS, default='TRASH',
        update=_on_setting_changed,
    )
    density: bpy.props.FloatProperty(
        name="Density",
        description="Props per square metre of the scattered region",
        default=1.0, min=0.05, soft_max=6.0, max=20.0,
        update=_on_setting_changed,
    )
    seed: bpy.props.IntProperty(
        name="Seed",
        description="Same seed, same layout. Change it to re-roll",
        default=1, min=0,
        update=_on_setting_changed,
    )
    edge_bias: bpy.props.FloatProperty(
        name="Edge Bias",
        description="How strongly props gather along the region's edges",
        default=0.6, min=0.0, max=1.0, subtype='FACTOR',
        update=_on_setting_changed,
    )
    scale_jitter: bpy.props.FloatProperty(
        name="Scale Jitter",
        description="Random size variation around 1.0",
        default=0.1, min=0.0, max=0.4, subtype='FACTOR',
        update=_on_setting_changed,
    )
    prop_scale: bpy.props.FloatProperty(
        name="Prop Scale",
        description="Every prop's base size. 1.0 is real game size",
        default=1.0, min=0.1, soft_max=3.0, max=5.0,
        update=_on_setting_changed,
    )
    topple: bpy.props.FloatProperty(
        name="Topple",
        description="The chance a standing prop - a bottle, a can - is "
                    "laid on its side instead. Litter that stands to "
                    "attention reads as staged, so everything topples "
                    "by default; lower this only on purpose",
        default=1.0, min=0.0, max=1.0, subtype='FACTOR',
        update=_on_setting_changed,
    )
    clustering: bpy.props.FloatProperty(
        name="Clustering",
        description="0 spreads the litter; toward 1 it gathers into "
                    "heaps around a few seeded spots",
        default=0.3, min=0.0, max=1.0, subtype='FACTOR',
        update=_on_setting_changed,
    )
    dirt_enabled: bpy.props.BoolProperty(
        name="Floor Dirt",
        description="Lay a procedural dirt overlay over the scattered "
                    "region - the flat decal sheet vanilla interiors use",
        default=True,
        update=_on_setting_changed,
    )
    dirt_amount: bpy.props.FloatProperty(
        name="Amount",
        description="How dirty the floor is",
        default=0.5, min=0.0, max=1.0, subtype='FACTOR',
        update=_on_setting_changed,
    )
    dirt_scale: bpy.props.FloatProperty(
        name="Blotch Size",
        description="How large the grime patches are, in metres",
        default=2.0, min=0.5, soft_max=6.0, max=12.0, subtype='DISTANCE',
        update=_on_setting_changed,
    )
    # No update callback: this changes nothing until Optimize is pressed,
    # and rebuilding the sheet on every drag of it would undo the very
    # optimisation it is about to ask for.
    dirt_tolerance: bpy.props.FloatProperty(
        name="Tolerance",
        description="How far Optimize may let the grime pattern drift, "
                    "as a fraction of its strength. Higher removes more "
                    "geometry: 0.02 is faithful enough for a painted "
                    "stroke, 0.08 suits noise, and past ~0.2 the blotch "
                    "edges visibly soften",
        default=0.08, min=0.002, soft_max=0.25, max=0.5, precision=3,
    )
    live_update: bpy.props.BoolProperty(
        name="Live Update",
        description="Rebuild the layout as these settings change",
        default=True,
    )
    # Why the last rebuild could not register entities, or "" when it
    # could. Written by rebuild(), read by the panel: the status bar
    # clears itself after a moment, and a user who scatters three times
    # sees the same warning flash past three times without ever being
    # able to read it (seen in a user's log).
    entity_status: bpy.props.StringProperty(
        name="Entity Status", default="", options={'HIDDEN'})


_classes = (SETO_PG_scatter_data,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.seto_scatter_data = bpy.props.PointerProperty(
        type=SETO_PG_scatter_data)


def unregister():
    del bpy.types.Object.seto_scatter_data
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
