"""The one place in the whole add-on that touches the network.

Two operators, each one user press, each one thing: Check asks GitHub's
public API what the latest release is; Install downloads that release's
zip and installs it over this one. Neither ever runs on its own - there
is no startup check, no timer, no handler - and the suite enforces that
this file is the only one in the package that can reach the network at
all. That is the shape of the promise the add-on makes: not "never
online", but **never online without being asked.**

The download is only accepted from this repository's own releases, and
the zip is only installed after its contents look like this add-on -
paranoia is cheap here, and the addons folder is a bad place to be wrong
about.
"""

import json
import os
import shutil
import urllib.error
import urllib.request
import zipfile

import bpy

from . import logic

_HEADERS = {"User-Agent": "seto-tools-updater",
            "Accept": "application/vnd.github+json"}


class SETO_OT_update_check(bpy.types.Operator):
    bl_idname = "seto.update_check"
    bl_label = "Check for Updates"
    bl_description = ("Ask github.com whether a newer release exists. One "
                      "request, sent only when you press this")
    bl_options = {'INTERNAL'}

    def execute(self, context):
        state = context.window_manager.seto_updater
        state.update_available = False
        state.download_url = ""
        state.latest = ""

        try:
            request = urllib.request.Request(logic.RELEASES_LATEST,
                                             headers=_HEADERS)
            with urllib.request.urlopen(request, timeout=10) as response:
                release = json.load(response)
        except (urllib.error.URLError, OSError, ValueError):
            state.status = "Could not reach GitHub - check your connection."
            self.report({'ERROR'}, state.status)
            return {'CANCELLED'}

        picked = logic.pick(release)
        if picked is None:
            state.status = "The latest release has no installable zip."
            self.report({'ERROR'}, state.status)
            return {'CANCELLED'}

        tag, url, _size = picked
        state.latest = tag
        if logic.is_newer(tag):
            state.update_available = True
            state.download_url = url
            state.status = (f"{tag} is available - you have "
                            f"{logic.current_str()}.")
        else:
            state.status = f"You are on the latest ({logic.current_str()})."
        self.report({'INFO'}, state.status)
        return {'FINISHED'}


class SETO_OT_update_install(bpy.types.Operator):
    bl_idname = "seto.update_install"
    bl_label = "Install Update"
    bl_description = ("Download the new version and install it over this "
                      "one. Your settings survive; restart Blender to "
                      "finish")
    bl_options = {'INTERNAL'}

    def execute(self, context):
        state = context.window_manager.seto_updater
        if not state.download_url:
            self.report({'ERROR'}, "Check for updates first.")
            return {'CANCELLED'}
        # Only this repository's own release assets, ever. The URL came
        # from GitHub's API moments ago, but the property is writable and
        # an installer that trusts a writable string is an installer for
        # anything.
        if not state.download_url.startswith(logic.DOWNLOAD_PREFIX):
            self.report({'ERROR'}, "Refusing a download that is not from "
                                   "this add-on's own releases.")
            return {'CANCELLED'}

        path = os.path.join(bpy.app.tempdir, logic.ASSET_NAME)
        try:
            request = urllib.request.Request(
                state.download_url, headers={"User-Agent": "seto-tools-updater"})
            with urllib.request.urlopen(request, timeout=60) as response, \
                    open(path, "wb") as out:
                shutil.copyfileobj(response, out)
        except (urllib.error.URLError, OSError):
            state.status = "The download failed - try again."
            self.report({'ERROR'}, state.status)
            return {'CANCELLED'}

        # The zip has to look like this add-on before it goes anywhere
        # near the addons folder: one seto_tools/ root with the package
        # init in it, nothing outside it.
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                looks_right = ("seto_tools/__init__.py" in names
                               and all(name.startswith("seto_tools/")
                                       for name in names))
        except zipfile.BadZipFile:
            looks_right = False
        if not looks_right:
            state.status = ("The download did not look like Void Tools - "
                            "nothing was installed.")
            self.report({'ERROR'}, state.status)
            return {'CANCELLED'}

        bpy.ops.preferences.addon_install(filepath=path, overwrite=True)
        state.update_available = False
        state.status = (f"Installed {state.latest}. Restart Blender to "
                        f"finish.")
        self.report({'INFO'}, state.status)
        return {'FINISHED'}


_classes = (SETO_OT_update_check, SETO_OT_update_install)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
