"""Open the report on GitHub, and empty the form afterwards.

Nothing here sends anything. The report operator shows what it is about
to hand over, then opens GitHub's own new-issue form with the fields
already filled in - which is where the user reads it once more and
presses GitHub's Submit themselves.

There is no picture handling at all, deliberately. An image cannot travel
in a URL, so a file field here would only have collected something the
user still had to drag onto the issue by hand: the same work, after a
detour. The body carries a Screenshot heading instead, and the panel says
where to drop it.
"""

import bpy

from ..shared import ui_common
from . import properties, report


class SETO_OT_support_report(bpy.types.Operator):
    bl_idname = "seto.support_report"
    bl_label = "Send Report to GitHub"
    bl_description = ("Show the report, then open it on GitHub with every "
                      "field already filled in. Nothing leaves your machine "
                      "until you press Submit there")
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        # Read it before it goes anywhere. The report carries versions the
        # user never typed and a body assembled out of a dozen fields, and
        # "what exactly is this about to publish" is a fair question to
        # want answered on this side of the browser.
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        settings = context.scene.seto_support
        layout = self.layout

        layout.label(text="This is what will be filled in on GitHub:",
                     icon='INFO')
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8
        title = settings.title.strip() or "Bug report"
        col.label(text=title, icon='BOOKMARKS')
        col.separator()
        body = report.build_body(properties.text_of(settings, "steps"),
                                 properties.text_of(settings, "result"),
                                 properties.text_of(settings, "expected"),
                                 settings.include_environment)
        for line in body.splitlines():
            for wrapped in ui_common.wrap(line, 60) if line else [""]:
                col.label(text=wrapped)

        note = layout.column(align=True)
        note.scale_y = 0.8
        note.label(text="Pressing OK opens GitHub with this ready to "
                        "post.")
        note.label(text="It is still yours to edit there, and nothing is")
        note.label(text="sent until you press Submit on that page.")

    def execute(self, context):
        settings = context.scene.seto_support
        result = properties.text_of(settings, "result")
        if not settings.title.strip() and not result.strip():
            self.report({'ERROR'},
                        "Fill in a title or what happened first.")
            return {'CANCELLED'}

        body = report.build_body(properties.text_of(settings, "steps"),
                                 result,
                                 properties.text_of(settings, "expected"),
                                 settings.include_environment)
        url = report.build_url(settings.title, body)

        if report.too_long(url):
            # A URL this long is refused or silently cut by browsers and
            # servers alike, and half a report is worse than a pasted one.
            context.window_manager.clipboard = body
            bpy.ops.wm.url_open(url=report.NEW_ISSUE)
            self.report({'INFO'}, "Report copied to the clipboard - paste "
                                  "it into the issue that just opened.")
            return {'FINISHED'}

        bpy.ops.wm.url_open(url=url)
        self.report({'INFO'}, "Add a screenshot on GitHub, then press "
                              "Submit.")
        return {'FINISHED'}


class SETO_OT_support_clear(bpy.types.Operator):
    bl_idname = "seto.support_clear"
    bl_label = "Clear"
    bl_description = "Empty the form, ready for the next report"
    bl_options = {'UNDO', 'INTERNAL'}

    def execute(self, context):
        settings = context.scene.seto_support
        properties.clear(settings)
        settings.title = ""
        self.report({'INFO'}, "Report cleared.")
        return {'FINISHED'}


_classes = (SETO_OT_support_report, SETO_OT_support_clear)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
