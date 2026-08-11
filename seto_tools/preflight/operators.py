"""Run the checks, jump to what they found, and repair what is mechanical.

Checking is read-only. Fixing is not, and is deliberately narrow: only the
four findings with exactly one right answer have a Fix button at all (see
checks.FIXERS), each is one undo step, and each says in the status bar what
it did rather than changing a mesh quietly.

Nothing is ever fixed in bulk or without being asked. A pass that swept the
scene "fixing" things would be the last thing anyone wants from a checker -
the point of this tool is that the author stays the one deciding.
"""

import bpy

from ..shared import viewport_grade as vg
from . import checks


def _fill(settings, rows):
    """Replace the findings list with `rows`, in the order that matters.

    Rebuilt whole rather than appended to: a CollectionProperty cannot be
    reordered in place, and the sort - fixable first - has to survive a
    repair removing a row from the middle.
    """
    rows = sorted(rows, key=lambda row: (checks.sort_key(row[1], row[2]),
                                         row[0]))
    settings.findings.clear()
    for object_name, check, severity, message, slot, note in rows:
        finding = settings.findings.add()
        finding.object_name = object_name
        finding.check = check
        finding.severity = severity
        finding.message = message
        finding.material_index = slot
        finding.note = note


def _rows(settings):
    return [(f.object_name, f.check, f.severity, f.message, f.material_index,
             f.note) for f in settings.findings]


def _set_note(settings, object_name, check, note):
    for finding in settings.findings:
        if finding.object_name == object_name and finding.check == check:
            finding.note = note


class SETO_OT_preflight_run(bpy.types.Operator):
    bl_idname = "seto.preflight_run"
    bl_label = "Run Pre-Flight"
    bl_description = ("Check every mesh in scope for the things that break "
                      "after export - missing UVs or materials, unapplied "
                      "scale, n-gons, stray geometry")
    bl_options = {'UNDO'}

    def execute(self, context):
        settings = context.scene.seto_preflight
        objects = vg.scope_objects(context, settings.scope)
        if not objects:
            self.report({'ERROR'}, "No mesh objects in scope to check.")
            return {'CANCELLED'}

        rows = []
        for obj in objects:
            for name, severity, message, slot in checks.run(obj):
                rows.append((obj.name, name, severity, message, slot, ""))
        _fill(settings, rows)

        settings.has_run = True
        settings.checked = len(objects)
        broken = sum(1 for f in settings.findings
                     if f.severity == checks.BROKEN)
        self.report({'INFO'}, f"Checked {len(objects)} objects: "
                              f"{len(settings.findings)} findings, "
                              f"{broken} would break in game.")
        return {'FINISHED'}


def _frame_selected(context):
    """Fly the viewport onto what was just selected.

    Selecting an object somewhere off screen is only half a jump - the
    other half is being able to see it. Every 3D view gets it, because
    the one the user is looking at is not knowable from here. No viewport
    at all (background, or a layout without one) is not an error.
    """
    import bpy
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for region in area.regions:
                if region.type != 'WINDOW':
                    continue
                try:
                    with context.temp_override(window=window, area=area,
                                               region=region):
                        bpy.ops.view3d.view_selected()
                except RuntimeError:
                    pass


def _show_material(context, obj, index):
    """Put the offending material slot under the cursor.

    Two halves: make it the object's active slot, and turn whichever
    Properties editor is open to its Material tab - landing on the object
    with the Modifier tab showing still leaves the shader to hunt for.
    """
    if index < 0 or index >= len(obj.material_slots):
        return
    obj.active_material_index = index
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'PROPERTIES':
                continue
            for space in area.spaces:
                if space.type != 'PROPERTIES':
                    continue
                try:
                    space.context = 'MATERIAL'
                except TypeError:
                    # Some object types have no material tab to show.
                    pass


class SETO_OT_preflight_select(bpy.types.Operator):
    bl_idname = "seto.preflight_select"
    bl_label = "Select"
    bl_description = ("Select this object, frame it in the viewport, and "
                      "show the material the finding is in")
    bl_options = {'UNDO', 'INTERNAL'}

    object_name: bpy.props.StringProperty()
    material_index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        obj = context.view_layer.objects.get(self.object_name)
        if obj is None:
            self.report({'ERROR'},
                        f"{self.object_name} is no longer in the view layer.")
            return {'CANCELLED'}
        for other in context.view_layer.objects:
            other.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        _show_material(context, obj, self.material_index)
        _frame_selected(context)
        return {'FINISHED'}


class SETO_OT_preflight_fix(bpy.types.Operator):
    """The remedy for one finding, opened where it was clicked.

    A popup rather than an expanding row: the steps run to six or seven
    lines, and folding that into a panel that already lists every finding
    pushes the rest of the tool off the screen. `invoke_popup` puts it
    beside the cursor and it closes on the next click.

    It does not fix anything either - see the module docstring. The button
    says "how", not "do it".
    """
    bl_idname = "seto.preflight_fix"
    bl_label = "How to fix"
    bl_description = "Show what to do about this finding"
    bl_options = {'INTERNAL'}

    check: bpy.props.StringProperty()
    object_name: bpy.props.StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=320)

    def draw(self, context):
        layout = self.layout
        layout.label(text=self.check, icon='TOOL_SETTINGS')
        if self.object_name:
            layout.label(text=self.object_name, icon='OUTLINER_OB_MESH')
        col = layout.column(align=True)
        for line in checks.fix_for(self.check):
            col.label(text=line)

    def execute(self, context):
        return {'FINISHED'}


def _refresh(settings, objects):
    """Re-check these objects and replace their rows, keeping the order.

    A finding that has been repaired has to leave the list, or the panel
    keeps offering to fix something that is already fixed. Re-running the
    whole scope instead would be slower and would quietly re-check objects
    the user has edited since, changing rows they were not looking at.
    """
    names = {obj.name for obj in objects}
    old = _rows(settings)
    # A refusal explains a finding that is still there, so it has to
    # survive the re-check that follows the attempt.
    notes = {(row[0], row[1]): row[5] for row in old if row[5]}
    rows = [row for row in old if row[0] not in names]
    for obj in objects:
        for name, severity, message, slot in checks.run(obj):
            rows.append((obj.name, name, severity, message, slot,
                         notes.get((obj.name, name), "")))
    _fill(settings, rows)


class SETO_OT_preflight_apply_fix(bpy.types.Operator):
    """Repair one finding, and say in the status bar what was done.

    Only the four checks in `checks.FIXERS` reach this - the panel draws
    no button for the rest. It is one undo step: Ctrl+Z puts the mesh back
    exactly as it was, which is what makes a fix button acceptable at all
    in a tool whose other six panels never touch a source mesh.
    """
    bl_idname = "seto.preflight_apply_fix"
    bl_label = "Fix"
    bl_description = ("Repair this finding. One undo step, and the status "
                      "bar reports what changed")
    bl_options = {'UNDO', 'INTERNAL'}

    check: bpy.props.StringProperty()
    object_name: bpy.props.StringProperty()
    # Set only by the confirmation below, never by the panel: the copy it
    # authorises breaks instancing, so it has to be a thing the user said
    # yes to rather than a default.
    isolate_users: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    apply_to_all: bpy.props.BoolProperty(
        name="Do the same for every other shared mesh in the list",
        description="Answer once instead of once per row - every finding "
                    "held up by the same sharing is fixed the same way",
        default=True,
    )

    def _shared(self, context):
        """(object, sharer count) when this fix needs asking about first."""
        obj = context.view_layer.objects.get(self.object_name)
        if obj is None or self.check != "Scale" or obj.library is not None:
            return None, 0
        count = checks.mesh_sharers(obj)
        return (obj, count) if count > 1 else (None, 0)

    def _blocked_rows(self, context):
        """Every row in the list held up by the same sharing, this one
        included. What "do them all" means, and what the dialog counts."""
        settings = context.scene.seto_preflight
        names = []
        for finding in settings.findings:
            if finding.check != self.check:
                continue
            obj = context.view_layer.objects.get(finding.object_name)
            if obj is None or obj.library is not None:
                continue
            if checks.mesh_sharers(obj) > 1:
                names.append(finding.object_name)
        return names

    def invoke(self, context, event):
        # Blender's own Ctrl+A asks the same question on shared data. It
        # is asked here rather than refused because the answer is often
        # yes - and refused by default in Fix All, where nobody is there
        # to answer for forty props at once.
        obj, count = self._shared(context)
        if obj is not None:
            self.isolate_users = True
            return context.window_manager.invoke_props_dialog(self, width=340)
        self.isolate_users = False
        return self.execute(context)

    def draw(self, context):
        obj, count = self._shared(context)
        layout = self.layout
        col = layout.column(align=True)
        col.label(text=f"{count} objects share this mesh.", icon='ERROR')
        col.separator()
        for line in (
                "Applying the scale writes it into the mesh, so all",
                f"{count} would resize. This will give " + (obj.name if obj
                                                            else "it"),
                "its own copy of the mesh first, then apply.",
                "",
                "That ends the instancing for this object: its mesh",
                "is separate data from here on, and editing one no",
                "longer changes the others.",
        ):
            col.label(text=line)

        blocked = len(self._blocked_rows(context))
        if blocked > 1:
            layout.separator()
            box = layout.box()
            box.prop(self, "apply_to_all")
            note = box.column(align=True)
            note.scale_y = 0.8
            note.label(text=f"{blocked} rows are waiting on the same answer.")

    def execute(self, context):
        settings = context.scene.seto_preflight
        obj = context.view_layer.objects.get(self.object_name)
        if obj is None:
            self.report({'ERROR'},
                        f"{self.object_name} is no longer in the view layer.")
            return {'CANCELLED'}
        fixer = checks.FIXERS.get(self.check)
        if fixer is None:
            self.report({'ERROR'}, f"{self.check} has no automatic fix.")
            return {'CANCELLED'}

        # One answer, every row it applies to. Names rather than objects:
        # each repair re-checks and rebuilds the list, so a reference into
        # it would be stale by the second one.
        if self.isolate_users and self.apply_to_all:
            names = self._blocked_rows(context)
            if len(names) > 1:
                return self._all(context, settings, fixer, names)

        changed, message = fixer(obj, context, isolate=self.isolate_users)
        _refresh(settings, [obj])
        if not changed:
            # Not an error: acting would have been wrong, and the reason
            # belongs on the row rather than only in a status bar that the
            # next click wipes.
            _set_note(settings, obj.name, self.check, message)
            self.report({'INFO'}, f"{obj.name}: {message}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"{obj.name}: {message}")
        return {'FINISHED'}

    def _all(self, context, settings, fixer, names):
        """Answer once, repair every row that was waiting on it.

        The last object to be reached is no longer sharing anything - the
        ones before it took their own copies - so it keeps the original
        mesh and no data is duplicated needlessly.
        """
        fixed = 0
        touched = []
        for name in names:
            target = context.view_layer.objects.get(name)
            if target is None:
                continue
            changed, message = fixer(target, context, isolate=True)
            touched.append(target)
            if changed:
                fixed += 1
            else:
                _set_note(settings, name, self.check, message)
        _refresh(settings, touched)
        if not fixed:
            self.report({'ERROR'}, "None of them could be fixed - "
                                   "each row now says why.")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Fixed {fixed} shared-mesh finding"
                              f"{'s' if fixed != 1 else ''} in one go.")
        return {'FINISHED'}


class SETO_OT_preflight_fix_all(bpy.types.Operator):
    """Repair a heading's findings that have a fixer, in one undo step.

    Only the mechanical ones - the two that are decisions are left
    exactly where they were, and the report says how many are still
    waiting so nobody reads an empty-ish list as "all done".

    It runs up to three passes because one repair can uncover another:
    dropping a zero-area face leaves the vertices that were in it loose,
    and a Fix All that stopped before clearing those would leave work it
    had just created. The cap is there so a fixer that somehow never
    settles cannot spin.
    """
    bl_idname = "seto.preflight_fix_all"
    bl_label = "Fix All"
    bl_description = ("Repair every finding under this heading that has a "
                      "Fix button. One undo step; the ones that need a "
                      "decision are left alone")
    bl_options = {'UNDO'}

    # Which heading's rows to do. The panel always sets it - what a user
    # decides about eleven scales is not what they decide about six
    # textures. Empty means everything, which is what a script calling
    # this directly wants.
    group: bpy.props.StringProperty(default="")

    def _mine(self, check):
        return (checks.can_fix(check)
                and (not self.group
                     or checks.group_for(check)[0] == self.group))

    def execute(self, context):
        settings = context.scene.seto_preflight
        fixed = 0
        refused = 0
        touched = {}

        reasons = {}
        for _pass in range(3):
            todo = [(row[0], row[1]) for row in _rows(settings)
                    if self._mine(row[1]) and not row[5]]
            if not todo:
                break
            worked = False
            for object_name, check in todo:
                obj = context.view_layer.objects.get(object_name)
                if obj is None:
                    continue
                changed, message = checks.FIXERS[check](obj, context)
                touched[object_name] = obj
                if changed:
                    fixed += 1
                    worked = True
                else:
                    refused += 1
                    reasons[(object_name, check)] = message
            _refresh(settings, list(touched.values()))
            # Every refusal explains itself on its own row: a run that
            # declines eleven things and says so once, in a status bar,
            # leaves nobody anywhere to look.
            for (object_name, check), message in reasons.items():
                _set_note(settings, object_name, check, message)
            if not worked:
                break

        if not fixed:
            if not refused:
                self.report({'ERROR'},
                            f"Nothing under {self.group or 'these findings'} "
                            f"can be fixed automatically.")
            else:
                sample = next(iter(reasons.values()), "")
                self.report({'ERROR'},
                            f"{refused} finding{'s' if refused != 1 else ''} "
                            f"declined, none fixed. {sample} "
                            f"Each row now says why.")
            return {'CANCELLED'}

        left = len(settings.findings)
        report = f"Fixed {fixed} finding{'s' if fixed != 1 else ''} on " \
                 f"{len(touched)} object{'s' if len(touched) != 1 else ''}."
        if refused:
            report += f" {refused} declined - see the note on each."
        if left:
            report += f" {left} left for you to decide on."
        self.report({'INFO'}, report)
        return {'FINISHED'}


class SETO_OT_preflight_clear(bpy.types.Operator):
    bl_idname = "seto.preflight_clear"
    bl_label = "Clear Findings"
    bl_description = "Empty the list"
    bl_options = {'UNDO'}

    def execute(self, context):
        settings = context.scene.seto_preflight
        settings.findings.clear()
        settings.has_run = False
        settings.checked = 0
        return {'FINISHED'}


_classes = (SETO_OT_preflight_run, SETO_OT_preflight_select,
            SETO_OT_preflight_fix, SETO_OT_preflight_apply_fix,
            SETO_OT_preflight_fix_all, SETO_OT_preflight_clear)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
