import bpy

from ..shared import groups, icons, panel_layout as pl, ui_common
from . import checks, legend, operators


class SETO_PT_preflight_panel(bpy.types.Panel):
    bl_label = "Pre-Flight"
    bl_idname = "SETO_PT_preflight_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = pl.TAB
    bl_parent_id = groups.ANALYSIS
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 2

    # No Sollumz warning: these are Blender-level facts about a mesh, and
    # the machine that has not got Sollumz working yet is exactly the one
    # whose asset is worth checking.

    def draw_header(self, context):
        icons.draw_header(self.layout, "preflight", 'CHECKMARK')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_preflight

        col = pl.section(layout, "Scope", 'VIEWZOOM')
        col.prop(settings, "scope")

        pl.create_button(layout, "seto.preflight_run",
                         "Run Pre-Flight", 'CHECKMARK')

        # Clear sits directly under Run, not after the findings: a long list
        # pushes the bottom of this panel off the screen, and the button
        # that empties it is no use where it cannot be reached.
        if settings.has_run:
            layout.operator("seto.preflight_clear", icon='X')

        if not settings.has_run:
            pl.hint(layout, "Catches what only shows up after export.")
        elif not settings.findings:
            box = layout.box()
            box.label(text=f"All clear across {settings.checked} objects.",
                      icon='CHECKMARK')
        else:
            self._draw_findings(layout, settings)

        # Drawn in every state, unlike the other two tools' legends: the
        # most useful moment for "here is what this catches, and it will
        # not touch your mesh" is before the button is pressed.
        col = pl.section(layout, "What the findings mean", 'INFO')
        legend.draw(col)

    def _draw_findings(self, layout, settings):
        broken = sum(1 for f in settings.findings
                     if f.severity == checks.BROKEN)
        box = layout.box()
        box.label(text=f"{len(settings.findings)} findings on "
                       f"{settings.checked} objects", icon='INFO')
        if broken:
            box.label(text=f"{broken} would not draw correctly in game")

        # Filed under a heading per group, each one collapsible: forty
        # findings is a column nobody scrolls, and closing the two groups
        # you have already dealt with is how the rest becomes readable.
        # The sort keeps a group's rows together (see checks.sort_key).
        grouped = {}
        order = []
        for finding in settings.findings:
            label, icon = checks.group_for(finding.check)
            if label not in grouped:
                grouped[label] = []
                order.append((label, icon))
            grouped[label].append(finding)

        for label, icon in order:
            index = checks.group_index(label)
            rows = grouped[label]
            box = layout.box()
            header = box.row(align=True)
            header.prop(settings, "expanded", index=index,
                        text=f"{label} ({len(rows)})",
                        icon='TRIA_DOWN' if settings.expanded[index]
                        else 'TRIA_RIGHT',
                        emboss=False)
            # Fix All belongs to the heading, not to the whole panel: what
            # a user decides about eleven scales is not what they decide
            # about six textures, and one button over everything asks for
            # both answers at once. A row that has already said why it
            # will not be repaired is not counted - the number has to be
            # what the button will really do.
            waiting = sum(1 for finding in rows
                          if checks.can_fix(finding.check) and not finding.note)
            if waiting:
                fix_all = header.operator("seto.preflight_fix_all",
                                          text=f"Fix {waiting}",
                                          icon='CHECKMARK')
                fix_all.group = label
            header.label(text="", icon=icon)
            if not settings.expanded[index]:
                continue
            for finding in rows:
                self._draw_finding(box, finding)

    def _draw_finding(self, layout, finding):
        """One finding: which object, what, and the way out beside it.

        Its own method because a Blender list cannot show two lines per
        row, so this is a box rather than a UIList entry - and a message
        truncated to one column is a message nobody acts on.
        """
        block = layout.box()
        head = block.row(align=True)
        head.label(text=finding.object_name, icon='OUTLINER_OB_MESH')
        jump = head.operator("seto.preflight_select", text="",
                             icon='RESTRICT_SELECT_OFF')
        jump.object_name = finding.object_name
        jump.material_index = finding.material_index

        body = block.column(align=True)
        body.scale_y = 0.85
        icon = 'ERROR' if finding.severity == checks.BROKEN else 'INFO'
        body.label(text=finding.check, icon=icon)
        for line in ui_common.wrap(finding.message, 34):
            body.label(text=line)

        # Why a Fix declined, on the row that declined it.
        if finding.note:
            note = block.column(align=True)
            note.scale_y = 0.85
            note.label(text="Not fixed:", icon='INFO')
            for line in ui_common.wrap(finding.note, 34):
                note.label(text=line)

        # Where the repair is mechanical there is a button that does it;
        # where it is a decision there is only the explanation - see
        # checks.FIXERS.
        row = block.row(align=True)
        if checks.can_fix(finding.check):
            apply = row.operator("seto.preflight_apply_fix", text="Fix",
                                 icon='CHECKMARK')
            apply.check = finding.check
            apply.object_name = finding.object_name
        fix = row.operator("seto.preflight_fix", text="How to fix",
                           icon='QUESTION')
        fix.check = finding.check
        fix.object_name = finding.object_name


_classes = (SETO_PT_preflight_panel,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
