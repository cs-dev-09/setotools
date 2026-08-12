"""Turning what a user types into a GitHub issue they can send.

Pure text work - no bpy beyond reading versions, no network at all. The
add-on never posts anything: it builds the URL of GitHub's own **new
issue** form with every field already filled in, and the browser opens
there. What is written is visible on screen before anything is sent, and
sending it is the user pressing GitHub's own button while signed in as
themselves. Posting on somebody's behalf would need a token this add-on
has no business holding.

Half of a useful report is the half nobody remembers to include: which
Blender, which Void Tools, whether Sollumz was even found. That is
collected here so the reporter does not have to know it matters.
"""

import platform
import sys
import urllib.parse

# Browsers and servers both give up on very long URLs, and a truncated
# issue body is worse than a pasted one. Past this the operator puts the
# body on the clipboard instead and says so.
MAX_URL = 6000

NEW_ISSUE = "https://github.com/seto3d/setotools/issues/new"


def addon_version():
    module = sys.modules.get(__package__.rpartition(".")[0])
    version = getattr(module, "bl_info", {}).get("version", ())
    return ".".join(str(number) for number in version) or "unknown"


def environment():
    """The versions a maintainer asks for first, gathered without asking."""
    import bpy

    from ..shared import sollumz_integration as szi

    available, message = szi.get_status_message()
    return (
        ("Void Tools", addon_version()),
        ("Blender", bpy.app.version_string),
        ("Sollumz", "found" if available else f"not found - {message}"),
        ("OS", f"{platform.system()} {platform.release()}"),
    )


def build_body(steps, result, expected, include_environment=True):
    """The issue text, as GitHub markdown."""
    lines = []
    for heading, text in (("What I did", steps),
                          ("What happened", result),
                          ("What I expected", expected)):
        lines.append(f"**{heading}**")
        lines.append(text.strip() or "_(not filled in)_")
        lines.append("")
    # A place for the picture. GitHub takes images by dropping them onto
    # the box, which a prefilled URL cannot do - so the body asks for it
    # where it should go instead of leaving the reporter to remember.
    lines.append("**Screenshot**")
    lines.append("_(drag your screenshot onto this box)_")
    lines.append("")
    if include_environment:
        lines.append("**Versions**")
        for name, value in environment():
            lines.append(f"- {name}: {value}")
        lines.append("")
    return "\n".join(lines).strip()


def build_url(title, body):
    """GitHub's new-issue form with the fields prefilled."""
    query = urllib.parse.urlencode({"title": title.strip() or "Bug report",
                                    "body": body})
    return f"{NEW_ISSUE}?{query}"


def too_long(url):
    return len(url) > MAX_URL
