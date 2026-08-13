"""Trash Scatter - vanilla GTA props scattered over a floor as MLO entities.

Select the floor faces, press Scatter: cigarette butts, paper, cans and
rubble land where litter really lands - dense along the walls, sparse in
the open - each one a wireframe proxy box registered as an entity on the
floor's MLO archetype, so the game streams the real prop at zero geometry
cost to the interior.
"""

from . import properties
from . import object_settings
from . import operators
from . import ui

_modules = (properties, object_settings, operators, ui)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
