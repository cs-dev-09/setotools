# SPDX-License-Identifier: GPL-3.0-or-later
"""Materialize - height, normal and specular maps from one diffuse image.

The **Materials** section: the tool that makes the texture, rather than the
geometry the texture goes on. Everything else in this add-on starts from an
image you already have; this is where that image comes from.

Written by gecu (https://github.com/gecu3d) as a standalone add-on
(`velxor_materialize`) and folded in here with its module layout intact:

    imageops.py     pure numpy - blur pyramid, contrast remap, HSL colour mask
    imageio.py      bpy.types.Image <-> numpy, and the colour-space crossing
    generators.py   the three transforms, independent of bpy
    properties.py   the PropertyGroups, on `scene.vmat`
    operators.py    generation, material set-up, export
    ui.py           the panels

**Licensing.** The algorithms are ported from Bounding Box Software's
Materialize, which is GPL-3, so this package is GPL-3 and the add-on that
contains it is distributed under the same terms - see LICENSE at the root.
Keep the SPDX headers on these files.

**It does not need Sollumz.** That is not an oversight: the maths is numpy, and
a machine with no working Sollumz can still author a texture. Its panels say so
through `panel_layout.PlainChildPanel`, and `tests/panels.py` enforces that the
claim is declared rather than assumed.
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
