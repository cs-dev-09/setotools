"""What the updater knows without touching the network.

Pure functions: version parsing, comparison, and choosing the installable
asset out of a release. Everything that *does* touch the network lives in
operators.py, so this half is testable offline and the network half is
one screenful that can be read in full.
"""

import sys

RELEASES_LATEST = "https://api.github.com/repos/seto3d/void-tools/releases/latest"
RELEASES_PAGE = "https://github.com/seto3d/void-tools/releases/latest"
DOWNLOAD_PREFIX = "https://github.com/seto3d/void-tools/releases/download/"
ASSET_NAME = "seto_tools.zip"


def current():
    """The running add-on's version, straight from bl_info."""
    module = sys.modules.get(__package__.rpartition(".")[0])
    version = getattr(module, "bl_info", {}).get("version", ())
    return tuple(version) or (0, 0, 0)


def current_str():
    return ".".join(str(number) for number in current())


def parse_tag(tag):
    """A release tag as a comparable version tuple, or None.

    Tolerant about the leading v and about short tags ("v1.1" is 1.1.0),
    and strict about garbage: a tag that does not parse must never be
    treated as newer, so it parses to None and None is never newer.
    """
    parts = tag.strip().lstrip("vV").split(".")
    try:
        numbers = tuple(int(part) for part in parts[:3])
    except ValueError:
        return None
    if not numbers:
        return None
    while len(numbers) < 3:
        numbers += (0,)
    return numbers


def is_newer(tag):
    version = parse_tag(tag)
    return version is not None and version > current()


def pick(release):
    """(tag, download url, size) of the installable zip, or None.

    Strict about the asset name: GitHub attaches source archives to every
    release, and installing one of those would put a folder Blender cannot
    load into the addons directory.
    """
    tag = release.get("tag_name") or ""
    for asset in release.get("assets", []):
        if (asset.get("name") == ASSET_NAME
                and asset.get("browser_download_url")):
            return tag, asset["browser_download_url"], int(asset.get("size", 0))
    return None
