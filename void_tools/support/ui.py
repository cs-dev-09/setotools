"""The bug report form and the two links, at the bottom of the tab.

Where a user goes when they want to say something. Both links open a
browser through Blender's own `wm.url_open`, so nothing here talks to the
network itself - and the report is written here but **sent by the user**,
on GitHub's own page, signed in as themselves. See report.py.

A collapsed panel below the tools rather than a row inside them: a sponsor
button repeated at the foot of six tool panels is nagging, and a bug
report form is only wanted on the day something is wrong.
"""

import bpy

from ..shared import icons
from . import properties
from ..shared import panel_layout as pl

SPONSOR_URL = "https://github.com/sponsors/seto3d"
ISSUES_URL = "https://github.com/seto3d/void-tools/issues"

# Where a bug report actually gets answered. A ticket on the Discord is a
# conversation - somebody can ask which Blender, ask for the .blend, and say
# "try this" in the same minute - where a GitHub issue is a letter that waits
# for the next time the maintainer sits down. Most people reporting a problem
# with a Blender add-on are not GitHub users either, and an issue form asks
# them for an account before it asks them what went wrong.
DISCORD_URL = "https://discord.gg/2xwCCnFxyK"


def draw_links(layout, issues=True):
    """The links, drawn the same way wherever they appear.

    `issues` is off in the panel, where the form above it already is the
    way to report something - a second button that only opens the issue
    list is one more thing to read past. The add-on preferences keep it,
    because there is no form there.

    "Become a Sponsor" was the wording first and it read like a request.
    Nobody opens a modelling tool wanting to be asked for money, and this
    one is free either way - so the button says where it goes and leaves
    the asking out of it.
    """
    col = layout.column(align=True)
    col.scale_y = 1.2
    if issues:
        col.operator("wm.url_open", text="Report a Bug",
                     icon='URL').url = ISSUES_URL
    col.operator("wm.url_open", text="Support the Project",
                 icon='FUND').url = SPONSOR_URL


class SETO_PT_support_panel(bpy.types.Panel):
    bl_label = "Support"
    bl_idname = "SETO_PT_support_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = pl.TAB
    # Last in the tab, after the tool sections (Dressing holds 5).
    bl_order = 6
    bl_options = {'DEFAULT_CLOSED'}

    # No Sollumz poll: the day someone most needs the bug report form is
    # the day the add-on is not working properly on their machine.

    def draw_header(self, context):
        icons.draw_header(self.layout, "support", 'COMMUNITY')

    def draw(self, context):
        layout = self.layout

        # The Discord first, and on its own. A ticket there gets asked "which
        # Blender?" and "can you attach the .blend?" in the same minute, which
        # is most of what fixing a report takes - and it does not ask anybody
        # for a GitHub account before it asks them what went wrong.
        box = layout.box()
        box.label(text="Report a bug", icon='ERROR')

        note = box.column(align=True)
        note.scale_y = 0.8
        note.label(text="Open a ticket on the Discord - that is")
        note.label(text="where these get answered, usually same day.")

        row = box.row()
        row.scale_y = 1.4
        row.operator("wm.url_open", text="Open a Ticket on Discord",
                     icon='URL').url = DISCORD_URL

        # The one thing the old form was genuinely good at: nobody remembers
        # which Blender they are on, whether Sollumz was even found, or which
        # version of this add-on they installed. The ticket wants all three,
        # so they go to the clipboard in one press instead of being typed
        # wrongly from memory.
        box.operator("seto.support_copy_versions", icon='COPYDOWN')

        layout.separator()
        draw_links(layout, issues=True)

        note = layout.column(align=True)
        note.scale_y = 0.8
        note.label(text="Void Tools is free and always will be.")
        note.label(text="If it saved you an afternoon, there is a")
        note.label(text="page for that - no pressure either way.")


class SETO_PT_support_github_panel(pl.PlainChildPanel, bpy.types.Panel):
    """The GitHub issue form, kept for people who would rather write one.

    Second, and collapsed: the Discord is where a report gets answered, but an
    issue is a better home for something reproducible that should stay
    findable, and some people simply prefer it. The form itself is unchanged -
    see properties.py for why it is shaped the way it is.
    """
    bl_label = "Report on GitHub instead"
    bl_idname = "SETO_PT_support_github_panel"
    bl_parent_id = "SETO_PT_support_panel"
    bl_order = pl.FIRST_CHILD

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_support

        box = layout.box()

        col = box.column(align=True)
        col.label(text="Title")
        col.prop(settings, "title", text="")
        col.separator()

        # An aligned stack of line fields, all of them, always: aligned
        # fields at natural height share their borders and read as one
        # frame, and drawing every line every time is what keeps the
        # panel perfectly still while it is typed into. Revealing lines
        # as they filled was tried in two flavours and both moved the
        # form under the user's hands. See properties.py for the whole
        # history; in particular **never `emboss=False`** on these - it
        # removes the typing along with the border - and **no scale_y** -
        # shrinking aligned fields opens seams that read as separate
        # frames.
        for name, label in properties.FIELDS:
            col.label(text=label)
            area = col.column(align=True)
            for index in range(properties.LINES):
                area.prop(settings, f"{name}_{index}", text="")
            col.separator()

        box.prop(settings, "include_environment")

        # No file field for the picture. An image cannot travel in a URL,
        # so anything gathered here would have to be dragged onto the
        # issue by hand anyway - which is the same work, after a detour
        # through a file browser. Saying where it goes is worth more than
        # a control that cannot finish the job.
        shot = box.column(align=True)
        shot.scale_y = 0.8
        shot.label(text="Add your screenshot on GitHub - drag it",
                   icon='IMAGE_DATA')
        shot.label(text="onto the issue box after it opens.")

        row = box.row()
        row.scale_y = 1.4
        row.operator("seto.support_report", icon='URL')
        box.operator("seto.support_clear", text="Clear Report", icon='X')

        # No paragraph under the buttons explaining what Send does. The
        # preview it opens says all of it - on the screen where it still
        # matters - and a wall of small print in the panel is read once
        # and scrolled past for ever after.


_classes = (SETO_PT_support_panel, SETO_PT_support_github_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
