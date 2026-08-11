"""Open the report, and copy it if the URL will not carry it.

Neither operator sends anything. The first opens GitHub's own new-issue
form with the fields already filled in, which is where the user reads
what they wrote and presses GitHub's Submit themselves; the second puts
the same text on the clipboard for the times a browser would choke on a
URL that long.
"""

import bpy

from . import report


class SETO_OT_support_report(bpy.types.Operator):
    bl_idname = "seto.support_report"
    bl_label = "Open Prefilled Issue"
    bl_description = ("Open GitHub's new-issue form with everything above "
                      "already filled in. Nothing is sent until you press "
                      "Submit there")
    bl_options = {'INTERNAL'}

    def execute(self, context):
        settings = context.scene.seto_support
        if not settings.title.strip() and not settings.result.strip():
            self.report({'ERROR'},
                        "Fill in a title or what happened first.")
            return {'CANCELLED'}

        body = report.build_body(settings.steps, settings.result,
                                 settings.expected,
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
        self.report({'INFO'}, "Check it over on GitHub, then press Submit.")
        return {'FINISHED'}


class SETO_OT_support_copy(bpy.types.Operator):
    bl_idname = "seto.support_copy"
    bl_label = "Copy to Clipboard"
    bl_description = ("Put the report on the clipboard, to paste wherever "
                      "you like - an issue, a Discord thread, an email")
    bl_options = {'INTERNAL'}

    def execute(self, context):
        settings = context.scene.seto_support
        body = report.build_body(settings.steps, settings.result,
                                 settings.expected,
                                 settings.include_environment)
        title = settings.title.strip()
        context.window_manager.clipboard = (f"**{title}**\n\n{body}"
                                            if title else body)
        self.report({'INFO'}, "Copied.")
        return {'FINISHED'}


_classes = (SETO_OT_support_report, SETO_OT_support_copy)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
