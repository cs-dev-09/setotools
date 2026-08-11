"""The Updates box, drawn inside the Support panel.

Not a panel of its own: version, one button, and a status line do not
earn a heading in the tab, and the Support panel is already where "the
add-on itself" matters live.
"""

from ..shared import ui_common
from . import logic


def draw(layout, context):
    state = context.window_manager.seto_updater

    box = layout.box()
    box.label(text=f"Seto Tools {logic.current_str()}", icon='FILE_REFRESH')

    row = box.row()
    row.scale_y = 1.2
    row.operator("seto.update_check", icon='URL')

    if state.status:
        note = box.column(align=True)
        note.scale_y = 0.8
        for line in ui_common.wrap(state.status, 38):
            note.label(text=line)

    if state.update_available:
        row = box.row()
        row.scale_y = 1.4
        row.operator("seto.update_install", icon='IMPORT')

    hint = box.column(align=True)
    hint.scale_y = 0.7
    hint.label(text="One request to github.com, only when")
    hint.label(text="you press it. Never automatic.")
