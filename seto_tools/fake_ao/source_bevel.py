"""Rounding the SOURCE corner, reversibly, with a Bevel modifier.

The bevel used to be cut into the source mesh with `bmesh.ops.bevel` when the
strip was created. That worked exactly once: the edge it rounded no longer
existed afterwards, so the width could never be changed, the round could never
be taken back, and the strip had to store the corner it was built from because
the indices pointing at it had stopped meaning anything.

A **Bevel modifier** driven by edge weights is the same round with none of
that. Nothing about the mesh changes, so the stored edge indices stay valid;
width, segments and profile can be dragged live; switching it off leaves the
mesh exactly as it was found. Sollumz exports the *evaluated* object
(`ydrexport.py` -> `get_evaluated_obj` -> `to_mesh()`), so the round is baked
into the YDR the same as if it had been applied by hand.

**One modifier per source object**, shared by every AO strip on it - which is
what a corner treatment actually is, a property of the wall rather than of the
decal running along it. Per-strip widths still work: with WEIGHT limiting, the
modifier's width is scaled by each edge's own weight, so the modifier carries
the widest strip's width and every other strip's edges are weighted down to
their share of it. Segments and profile have no per-edge equivalent, so those
are genuinely shared.

Only edges that belong to a strip are ever written to. A bevel weight set by
hand anywhere else on the mesh is left alone.
"""

import bpy

MODIFIER_NAME = "Seto AO Bevel"

# Which per-object group a tool keeps its strips in, what its modifier is
# called, and which edge attribute that modifier's Weight limit reads. Edge
# Wear and Smooth Edge build the same strip and want the same live round, and
# the only things that differ between the three are these four names.
#
# The attribute has to be per tool. All three used to write Blender's own
# `bevel_weight_edge`, which every Bevel modifier limiting by Weight reads - so
# an AO strip and an Edge Wear strip on one wall gave that wall two modifiers
# that each rounded BOTH tools' edges, at each other's widths, and the round
# compounded. Measured on a cube: one strip took it from 8 vertices to 16, two
# strips from different tools took it to 44.
AO = ("seto_fake_ao_data", "is_fake_ao", MODIFIER_NAME, "seto_bevel_ao")
EDGE_WEAR = ("seto_fake_damage_data", "is_fake_damage", "Seto Edge Wear Bevel",
             "seto_bevel_edge_wear")
SMOOTH_EDGE = ("seto_smooth_edge_data", "is_smooth_edge", "Seto Smooth Edge Bevel",
               "seto_bevel_smooth_edge")

# Blender's own bevel-weight attribute. Not written any more - it is the user's,
# and a modifier they added themselves reads it - but our old weights are still
# sitting in it in any scene saved before this, so they are cleared off our own
# edges as each source is synced.
LEGACY_WEIGHT_ATTRIBUTE = "bevel_weight_edge"
WEIGHT_ATTRIBUTE = AO[3]

ALL_TOOLS = (AO, EDGE_WEAR, SMOOTH_EDGE)


def strips_for(source, tool=AO):
    """Every strip of one tool built from `source`, in a stable order."""
    if source is None:
        return []
    attr, flag = tool[0], tool[1]
    found = [obj for obj in bpy.data.objects
             if obj.type == 'MESH'
             and getattr(getattr(obj, attr), flag)
             and getattr(obj, attr).source_object is source]
    return sorted(found, key=lambda obj: obj.name)


def _edge_indices(mesh, edge_keys_text):
    """The mesh edges a strip's stored keys point at.

    Returns None when the strip has no usable edge list at all - Ground Level
    strips, which are built along a contour that is not in the mesh, and old
    strips whose corner was rounded away destructively.
    """
    # Imported here rather than at module scope: object_settings imports this
    # module to drive the sync from its update callback.
    from . import object_settings

    keys = object_settings.parse_edge_keys(edge_keys_text)
    if not keys:
        return None

    by_pair = {}
    for edge in mesh.edges:
        a, b = edge.vertices
        by_pair[(a, b)] = edge.index
        by_pair[(b, a)] = edge.index

    found = [by_pair[(va, vb)] for va, vb, _ in keys if (va, vb) in by_pair]
    return found or None


def _weights(mesh, name=WEIGHT_ATTRIBUTE):
    attribute = mesh.attributes.get(name)
    if attribute is None:
        attribute = mesh.attributes.new(name, 'FLOAT', 'EDGE')
    return attribute


def _clear_legacy_weights(mesh, indices):
    """Take our old writes off Blender's own bevel-weight attribute.

    Scenes saved before each tool got its own attribute have our weights in
    `bevel_weight_edge`, where a Bevel modifier the user added themselves would
    still act on them. Only the edges our strips own are touched.
    """
    attribute = mesh.attributes.get(LEGACY_WEIGHT_ATTRIBUTE)
    if attribute is None:
        return
    for index in indices:
        if index < len(attribute.data):
            attribute.data[index].value = 0.0


def _remove_modifier(source, name=MODIFIER_NAME):
    modifier = source.modifiers.get(name)
    if modifier is not None:
        source.modifiers.remove(modifier)


def _remove_weights(mesh, name):
    """Take our own weight attribute off the mesh entirely.

    Zeroing it would do for the round, but the attribute would still be listed
    in the Object Data panel of a mesh we are supposed to have left as we found
    it. Only ever called with one of our own names.
    """
    attribute = mesh.attributes.get(name)
    if attribute is not None:
        mesh.attributes.remove(attribute)


def sync(source, leader=None, tool=AO):
    """Bring `source`'s bevel modifier and edge weights in line with every AO
    strip built from it.

    `leader` is the strip whose settings won this round - the one just created
    or just edited - and decides the shared segments and profile. Without one,
    the widest contributing strip decides.

    Returns a short description of what the modifier ended up as, or None when
    there is nothing to round.
    """
    if source is None or source.type != 'MESH':
        return None
    if source.mode == 'EDIT':
        # Writing mesh attributes underneath an open edit-mesh loses them the
        # moment Blender flushes its own copy back.
        return None

    attr, _flag, modifier_name, weight_attribute = tool
    mesh = source.data
    contributors = []
    ours = []          # every edge any strip owns, contributing or not

    for strip in strips_for(source, tool):
        data = getattr(strip, attr)
        indices = _edge_indices(mesh, data.edge_keys)
        if indices is None:
            continue
        ours.extend(indices)
        if data.bevel_mesh and data.bevel_width > 0.0:
            contributors.append((data, indices))

    if not ours:
        _remove_modifier(source, modifier_name)
        _remove_weights(mesh, weight_attribute)
        return None

    weights = _weights(mesh, weight_attribute)
    _clear_legacy_weights(mesh, ours)

    if not contributors:
        # Every strip has its bevel switched off: put our edges back to zero
        # and take the modifier away, leaving the mesh as it was found.
        for index in ours:
            weights.data[index].value = 0.0
        _remove_modifier(source, modifier_name)
        mesh.update()
        return None

    widest = max(data.bevel_width for data, _ in contributors)
    if leader is None:
        leader = max(contributors, key=lambda entry: entry[0].bevel_width)[0]
    else:
        leader = getattr(leader, attr)

    contributing = {index for _, indices in contributors for index in indices}
    for index in ours:
        if index not in contributing:
            weights.data[index].value = 0.0
    for data, indices in contributors:
        # The modifier carries the widest width; everything else is that width
        # scaled down by its own edge weight.
        share = data.bevel_width / widest
        for index in indices:
            weights.data[index].value = share

    modifier = source.modifiers.get(modifier_name)
    if modifier is None:
        modifier = source.modifiers.new(modifier_name, 'BEVEL')
    modifier.affect = 'EDGES'
    modifier.limit_method = 'WEIGHT'
    # This tool's own attribute, never Blender's shared one - see the tuples at
    # the top. Without it, two tools' modifiers on one wall round each other's
    # edges.
    modifier.edge_weight = weight_attribute
    modifier.offset_type = 'OFFSET'
    modifier.width = widest
    modifier.segments = leader.bevel_segments
    modifier.profile = leader.bevel_profile

    mesh.update()
    return f"{widest:.4g} m, {modifier.segments} segment(s)"


# --- Deleting the last strip -------------------------------------------------
#
# sync() takes the modifier away when a source has no strips left, but nothing
# calls it once the strip that would have called it has been deleted: the
# object is gone, and with it the property callback. So a wall kept its round,
# and a modifier named after a tool the user could no longer see.
#
# Blender has no "object was deleted" callback, so this watches the object
# count from the depsgraph instead - the one signal a deletion cannot avoid
# producing. Everything below is written to be nearly free on the common case,
# where the count has not changed and the handler returns on its second line.

_seen_object_count = -1
_cleaning = False


def clean_orphans():
    """Take our modifier and weights off any source whose strips are all gone.

    Idempotent, and only ever touches a modifier we created and an attribute we
    named. Returns how many sources were cleaned.
    """
    cleaned = 0
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or obj.mode == 'EDIT':
            continue
        for tool in ALL_TOOLS:
            modifier_name, weight_attribute = tool[2], tool[3]
            if obj.modifiers.get(modifier_name) is None:
                continue
            if strips_for(obj, tool):
                continue
            _remove_modifier(obj, modifier_name)
            _remove_weights(obj.data, weight_attribute)
            cleaned += 1
    return cleaned


@bpy.app.handlers.persistent
def _on_depsgraph_update(scene, depsgraph=None):
    global _seen_object_count, _cleaning
    if _cleaning:
        return
    count = len(bpy.data.objects)
    if count == _seen_object_count:
        return
    # Recorded before the work, so a re-entrant update caused by removing the
    # modifier finds nothing to do.
    _seen_object_count = count
    _cleaning = True
    try:
        clean_orphans()
    finally:
        _cleaning = False


@bpy.app.handlers.persistent
def _on_load(*args):
    # A new file is a new set of objects; the count from the old one means
    # nothing, and matching it by chance would skip the first check.
    global _seen_object_count
    _seen_object_count = -1


def register():
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
