"""Where to report a bug, and where to fund the next tool.

One collapsed panel at the foot of the tab - a bug report form that opens
GitHub's own issue page with everything filled in, and the two links -
plus the same links in the add-on preferences. See ui.py for why they are
not repeated inside every tool, and report.py for why the add-on fills the
form in but never sends it.
"""

from . import properties
from . import operators
from . import ui

_modules = (properties, operators, ui)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
