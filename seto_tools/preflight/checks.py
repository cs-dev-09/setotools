"""The checks themselves - what makes an asset fail after it is exported.

Every check here is one this add-on's author would otherwise find by
exporting, building a resource, starting a server, walking to the prop and
seeing nothing. That loop is five minutes; these are milliseconds.

They earn their place by being things **vanilla barely does**. Run over
Franklin's house, 261 of its 265 render meshes come back with nothing said
about them at all - no missing UVs, no missing materials, no unapplied
scale, no n-gons anywhere - and the four that do trip a check trip the
mildest one, a handful of zero-area faces. So a finding here is not a
matter of taste: it is the asset differing from a shipped GTA interior in
a way the exporter cares about, and the false-positive rate on real vanilla
art is 1.5%.

Each check is a function taking an evaluated-free object and returning a
message or None. `FIXES` holds what to do about each in words, because a
finding without a remedy is just a complaint - and `FIXERS` holds the ones
this add-on will do for you.

**Only four checks have a fixer, on purpose.** A repair belongs here when
there is exactly one right answer: deleting a vertex that is in no face,
dropping a face with no area, removing an empty material slot, applying a
scale. The other two are decisions. An automatic unwrap produces a layout
no GTA asset would ship with, and Blender cannot write a DDS at all.
Offering to do those badly would be worse than saying plainly that they
are yours.

**N-gons are deliberately not checked.** Sollumz triangulates on export, so
a five-sided face is not a fault at all in this pipeline - and flagging one
on every model that has ever been box-modelled is exactly the noise that
teaches people to ignore a checker.
"""

# Severity is only about what happens in game, never about the author.
BROKEN = 'BROKEN'      # it will not look right, or will not draw at all
RISKY = 'RISKY'        # it exports, but a known class of bug starts here


def _has_material(obj):
    return any(slot.material for slot in obj.material_slots)


def check_uv(obj):
    """No UV map means the texture has nothing to land on."""
    if _has_material(obj) and not obj.data.uv_layers:
        return BROKEN, "No UV map - its texture has nowhere to land"
    return None


# There is deliberately no "this mesh has no material" check. A scene like
# an imported MLO is full of meshes that legitimately have none - collision
# bounds, helpers, blockouts - and flagging every one of them buried the
# findings that matter under hundreds that did not. A mesh with an *empty
# slot* is still reported, because that is debris either way and the fixer
# can clear it; a mesh with no slots at all is left alone.


def check_empty_slots(obj):
    """Empty slots are faces assigned to a material that is not there."""
    empty = [index for index, slot in enumerate(obj.material_slots)
             if slot.material is None]
    if empty:
        count = len(empty)
        return (RISKY, f"{count} empty material slot{'s' if count > 1 else ''}",
                empty[0])
    return None


def check_scale(obj):
    """Unapplied scale, and why non-uniform is the dangerous kind.

    A normal goes through the inverse-transpose of the object matrix and a
    tangent through its plain linear part, so the two only disagree under
    non-uniform scale - which is exactly when lighting and normal maps come
    out wrong on an export that otherwise looks fine in Blender.
    """
    scale = tuple(obj.scale)
    if all(abs(s - 1.0) <= 1e-4 for s in scale):
        return None
    if max(scale) - min(scale) > 1e-4:
        return BROKEN, ("Non-uniform scale not applied - normals and "
                        "tangents will disagree")
    return RISKY, f"Scale {scale[0]:.3g} not applied"


def check_texture_format(obj):
    """Textures that are not DDS.

    GTA streams DDS: mip-mapped and block-compressed. A PNG or a TGA in a
    shader has neither, so it shimmers at distance where a mip chain would
    have smoothed it, and it inflates the .ytd it is embedded into - a
    1024² PNG is four times the memory of the same image as BC1.

    Generated and packed images with no filepath are left alone: there is
    no format to judge, and Surface Painter's own textures live that way.

    The material is named alongside the image because that is where the fix
    happens: an object with nine slots gives no clue which shader to open,
    and hunting for the one holding a .png is the slowest part of the job.
    """
    wrong = set()
    first_slot = -1
    for index, slot in enumerate(obj.material_slots):
        material = slot.material
        if material is None or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type != 'TEX_IMAGE' or node.image is None:
                continue
            path = node.image.filepath_raw or node.image.filepath
            if not path:
                continue
            extension = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            if extension and extension != "dds":
                wrong.add(f"{node.image.name} (.{extension}) "
                          f"in {material.name}")
                if first_slot < 0:
                    first_slot = index
    if wrong:
        listed = "; ".join(sorted(wrong)[:2])
        more = f"; +{len(wrong) - 2} more" if len(wrong) > 2 else ""
        return (RISKY, f"Not DDS: {listed}{more} - no mips, no compression",
                first_slot)
    return None


def check_degenerate(obj):
    """Zero-area faces: they cost a triangle and draw nothing."""
    count = sum(1 for poly in obj.data.polygons if poly.area <= 1e-9)
    if count:
        return RISKY, f"{count} zero-area face{'s' if count > 1 else ''}"
    return None


def check_loose(obj):
    """Vertices in no face at all - they export, and draw nothing."""
    used = set()
    for poly in obj.data.polygons:
        used.update(poly.vertices)
    loose = len(obj.data.vertices) - len(used)
    if loose and obj.data.polygons:
        return RISKY, f"{loose} loose vert{'ices' if loose > 1 else 'ex'}"
    return None


# Order matters: the panel lists them in the order they are run, and a
# broken thing should be read before a risky one.
CHECKS = (
    ("UV map", check_uv),
    ("Scale", check_scale),
    ("Texture format", check_texture_format),
    ("Empty slots", check_empty_slots),
    ("Zero-area faces", check_degenerate),
    ("Loose vertices", check_loose),
)


# What to do about each finding, keyed by the check's name. Written as the
# steps someone would actually take in Blender, in order, because "n-gons
# found" with no route out is the sort of report people learn to close.
# Every entry in CHECKS must have one - tests/preflight.py enforces it.
FIXES = {
    "UV map": (
        "The texture has nowhere to land without one.",
        "1. Tab into Edit Mode and press A.",
        "2. U > Smart UV Project for a quick layout,",
        "   or unwrap by hand where it matters.",
        "3. Sollumz exports the first UV layer, so",
        "   name it UVMap 0.",
    ),
    "Scale": (
        "Normals go through the inverse-transpose of",
        "the matrix and tangents through its linear",
        "part, so under non-uniform scale the two",
        "disagree and normal maps light up wrong.",
        "1. Object Mode, select the object.",
        "2. Ctrl+A > Scale.",
        "3. If Seto strips are built on it, nudge a",
        "   setting to rebuild them onto the new size.",
        "Sharing a mesh with other objects? Applying",
        "would resize all of them, so Fix asks first",
        "and makes this object its own copy if you",
        "agree - which ends the instancing for it.",
        "If the instancing is deliberate, cancel and",
        "leave it: GTA exports each entity's own scale",
        "anyway. Fix All never makes that trade for you.",
    ),
    "Texture format": (
        "GTA streams DDS: mip-mapped and block",
        "compressed. A PNG has neither, so it shimmers",
        "at distance and inflates the .ytd.",
        "1. Convert the image to DDS - BC1 for opaque,",
        "   BC3 when it needs alpha - with mips on.",
        "2. Open the material named in the finding and",
        "   point its Image Texture node at the .dds.",
        "3. Packed or generated images are left alone;",
        "   only files on disk are judged.",
        "No Fix button here: Blender cannot write a",
        "DDS, so the conversion happens outside it.",
    ),
    "Empty slots": (
        "An empty slot is a material index faces can",
        "still point at, and it exports as nothing.",
        "1. Properties > Material tab.",
        "2. If faces use the slot, give them a real",
        "   material first (Edit Mode > Assign).",
        "3. Select the empty slot and press '-'.",
    ),
    "Zero-area faces": (
        "They cost a triangle each and draw nothing.",
        "1. Edit Mode, press A.",
        "2. Mesh > Clean Up > Degenerate Dissolve.",
        "3. Raise its threshold only if some survive -",
        "   too high and it eats real detail.",
    ),
    "Loose vertices": (
        "Vertices in no face at all. They export and",
        "draw nothing.",
        "1. Edit Mode, press A.",
        "2. Mesh > Clean Up > Delete Loose.",
        "3. Tick Vertices in the operator panel, and",
        "   leave Faces and Edges off unless you mean",
        "   to lose them too.",
    ),
}


def fix_for(check):
    """How to fix `check`, or a line saying nothing is written for it."""
    return FIXES.get(check, ("No fix written for this check yet.",))


# --------------------------------------------------------------- the fixers
# Each takes (obj, context) and returns (changed, message). They work on
# object data through bmesh and the data API rather than by driving Edit
# Mode, so they behave the same headless as they do under the cursor - and
# every one of them is a single undo step.


def mesh_sharers(obj):
    """How many objects really use this mesh.

    `.users` counts a fake user as a user, and Sollumz imports leave
    plenty of those - counting it would treat a mesh only one object uses
    as shared, which is a fix button that silently does nothing.
    """
    return obj.data.users - (1 if obj.data.use_fake_user else 0)


def fix_loose(obj, context, **options):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        loose = [vert for vert in bm.verts if not vert.link_faces]
        if not loose:
            return False, "No loose vertices left to remove."
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()
    count = len(loose)
    return True, f"Deleted {count} loose vert{'ices' if count > 1 else 'ex'}"


def fix_degenerate(obj, context, **options):
    """Drop the zero-area faces and nothing else.

    Deliberately not `dissolve_degenerate`: that also welds edges under a
    distance, which is a judgement about how close is too close. Removing
    a face with no area is not a judgement. Any vertices it leaves behind
    become a Loose vertices finding, which has its own fixer - two small
    honest steps rather than one that does more than it says.
    """
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        dead = [face for face in bm.faces if face.calc_area() <= 1e-9]
        if not dead:
            return False, "No zero-area faces left."
        bmesh.ops.delete(bm, geom=dead, context='FACES')
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()
    count = len(dead)
    return True, f"Removed {count} zero-area face{'s' if count > 1 else ''}"


def fix_empty_slots(obj, context, **options):
    """Remove the empty slots, as far as it can be done unambiguously.

    Three cases, and only the middle one is a judgement call.

    Every slot empty - the state an object that never got a material ends
    up in - is safe whatever the faces point at: there is no other
    material for them to be handed by mistake, so all of it goes. What is
    left is an object with no material and no slots pretending otherwise,
    which is not reported at all: a scene like an MLO is full of meshes
    that legitimately have none.

    Empty slots nothing points at go too, with the indices above them
    renumbered so the faces keep the material they had.

    An empty slot with faces on it, on an object that *does* have real
    materials, is refused: removing it shifts the slots above down, and
    those faces would silently inherit a material nobody assigned them.
    Which one they should have is the author's answer, not this tool's.
    """
    mesh = obj.data
    empty = [index for index, slot in enumerate(obj.material_slots)
             if slot.material is None]
    if not empty:
        return False, "No empty material slots left."

    if len(empty) == len(obj.material_slots):
        count = len(empty)
        mesh.materials.clear()
        for poly in mesh.polygons:
            poly.material_index = 0
        return True, (f"Removed {count} empty slot"
                      f"{'s' if count > 1 else ''} - the object had no "
                      f"material behind them")

    used = {poly.material_index for poly in mesh.polygons}
    removable = [index for index in empty if index not in used]
    if not removable:
        return False, ("The empty slots have faces on them and this object "
                       "has real materials too - assign those faces to a "
                       "real slot first, or removing would hand them a "
                       "material nobody chose.")
    if obj.mode != 'OBJECT':
        return False, "Leave Edit Mode first."

    # `materials.pop()` per slot, highest index first, and **no** manual
    # renumbering afterwards. Two ways of getting this wrong have already
    # shipped here. Shifting the face indices by hand as well moved every
    # face one material too far, because pop() already does that shift -
    # measured, not assumed: popping slot 1 takes a face on slot 2 to
    # slot 1 by itself. And handing the job to Blender's
    # `material_slot_remove_unused` operator quietly did nothing at all on
    # a real MLO, where its own conditions are not met on every object;
    # the data API has no such conditions.
    #
    # Removing highest-first matters: taking slot 1 out first would
    # renumber slot 2 before it is reached.
    for index in sorted(removable, reverse=True):
        mesh.materials.pop(index=index)
    count = len(removable)
    return True, (f"Removed {count} empty material slot"
                  f"{'s' if count > 1 else ''}")


def fix_scale(obj, context, isolate=False, **options):
    """Apply the scale, exactly as Ctrl+A does - through the operator.

    By hand this is one matrix multiply into the mesh; through the
    operator it is also every child's parent-inverse, every constraint and
    every modifier Blender knows to correct. Doing it by hand is how a
    fixer moves somebody's children across the room.

    A mesh several objects share cannot simply be applied to: the scale
    goes into the vertices, so every one of them would resize. Blender's
    own Ctrl+A offers to make the object single-user first, and so does
    this - but only when `isolate` says the user was asked and agreed,
    because on an MLO full of instanced props that trade is real: one
    mesh becomes many, and the instancing is gone.
    """
    import bpy
    if obj.library is not None or obj.data.library is not None:
        return False, "Linked from another file - open that file to change it."
    sharers = mesh_sharers(obj)
    isolated = False
    if sharers > 1:
        if not isolate:
            return False, (f"{sharers} objects share this mesh - applying "
                           f"would resize all of them. Press Fix on this row "
                           f"to make it single-user first; Fix All will not "
                           f"do that for you.")
        obj.data = obj.data.copy()
        isolated = True
    if obj.mode != 'OBJECT':
        return False, "Leave Edit Mode first."
    scale = tuple(obj.scale)
    with context.temp_override(object=obj, active_object=obj,
                               selected_objects=[obj],
                               selected_editable_objects=[obj]):
        bpy.ops.object.transform_apply(location=False, rotation=False,
                                       scale=True)
    note = " on its own copy of the mesh" if isolated else ""
    return True, (f"Applied scale {scale[0]:.3g}, {scale[1]:.3g}, "
                  f"{scale[2]:.3g}{note}")


# Which checks this add-on will repair itself. The three that are missing -
# Material, UV map, Texture format - are missing because their answer is a
# decision, not a procedure. See the module docstring.
FIXERS = {
    "Loose vertices": fix_loose,
    "Zero-area faces": fix_degenerate,
    "Empty slots": fix_empty_slots,
    "Scale": fix_scale,
}


def can_fix(check):
    return check in FIXERS


def run(obj):
    """Every failing check on one object.

    Rows are `(name, severity, message, material_index)`. The index is -1
    unless the finding lives in one particular material slot - a .png in
    the third shader, an empty slot at index one - in which case the panel's
    jump button can put that slot under the cursor instead of leaving
    somebody to open nine shaders looking for it.
    """
    found = []
    for name, check in CHECKS:
        result = check(obj)
        if result is None:
            continue
        severity, message = result[0], result[1]
        slot = result[2] if len(result) > 2 else -1
        found.append((name, severity, message, slot))
    return found


# What each check is filed under in the panel, and the icon its heading
# gets. Thirty findings in one column is a wall; the same thirty under
# "Scale issues (11)" and "Texture issues (6)" is a report you can read
# from the top and stop when you have seen enough.
GROUPS = {
    "Scale": ("Scale issues", 'CON_SIZELIKE'),
    "Empty slots": ("Material issues", 'MATERIAL'),
    "Zero-area faces": ("Geometry issues", 'MESH_DATA'),
    "Loose vertices": ("Geometry issues", 'MESH_DATA'),
    "UV map": ("UV issues", 'UV'),
    "Texture format": ("Texture issues", 'TEXTURE'),
}

DEFAULT_GROUP = ("Other issues", 'INFO')

# Every heading that can be drawn, in a fixed order. The panel keeps one
# open/closed flag per entry and indexes it by position here, so the order
# is what those flags mean - append to the end rather than inserting, or
# somebody's collapsed "Texture issues" becomes a collapsed "UV issues".
GROUP_ORDER = ("Scale issues", "Material issues", "Geometry issues",
               "UV issues", "Texture issues", DEFAULT_GROUP[0])


def group_for(check):
    return GROUPS.get(check, DEFAULT_GROUP)


def group_index(label):
    """Where `label`'s open/closed flag lives. Unknown headings share the
    last one, which is where DEFAULT_GROUP is."""
    try:
        return GROUP_ORDER.index(label)
    except ValueError:
        return len(GROUP_ORDER) - 1


def sort_key(check, severity):
    """Fixable first, then by group, then what breaks in game.

    What can be dealt with in one click belongs at the top: a list whose
    actionable rows are scattered through thirty explanations is a list
    people scroll past. The group comes before the severity so a heading
    is drawn once - sorting by severity first would split "Scale issues"
    into two blocks, because an unapplied scale is graded differently
    depending on whether it is uniform.
    """
    return (0 if can_fix(check) else 1,
            group_for(check)[0],
            0 if severity == BROKEN else 1,
            check)
