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

# Which per-object group a tool keeps its strips in, and what its modifier is
# called. Edge Wear and Smooth Edge build the same strip and want the same live
# round, and the only things that differ between the three are these.
AO = ("seto_fake_ao_data", "is_fake_ao", MODIFIER_NAME)
EDGE_WEAR = ("seto_fake_damage_data", "is_fake_damage", "Seto Edge Wear Bevel")
SMOOTH_EDGE = ("seto_smooth_edge_data", "is_smooth_edge", "Seto Smooth Edge Bevel")
# Blender's own bevel-weight attribute - the one the modifier's Weight limit
# reads. A generic float on the edge domain since 4.0.
WEIGHT_ATTRIBUTE = "bevel_weight_edge"


def strips_for(source, tool=AO):
    """Every strip of one tool built from `source`, in a stable order."""
    if source is None:
        return []
    attr, flag, _ = tool
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


def _weights(mesh):
    attribute = mesh.attributes.get(WEIGHT_ATTRIBUTE)
    if attribute is None:
        attribute = mesh.attributes.new(WEIGHT_ATTRIBUTE, 'FLOAT', 'EDGE')
    return attribute


def _remove_modifier(source, name=MODIFIER_NAME):
    modifier = source.modifiers.get(name)
    if modifier is not None:
        source.modifiers.remove(modifier)


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

    attr, _flag, modifier_name = tool
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
        return None

    weights = _weights(mesh)

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
    modifier.offset_type = 'OFFSET'
    modifier.width = widest
    modifier.segments = leader.bevel_segments
    modifier.profile = leader.bevel_profile

    mesh.update()
    return f"{widest:.4g} m, {modifier.segments} segment(s)"
