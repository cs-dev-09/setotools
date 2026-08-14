# Sign Glow tool subpackage.
#
# The halo behind illuminated 3D lettering: trace the letters' silhouette,
# blur it twice at two radii, and put the result on an emissive plane sitting
# just behind them. It is how a lit sign reads at night in game without a
# single real light being placed.
#
# **Contributed by Molo Modding** (https://github.com/molossen), who wrote it
# as a standalone add-on. What changed on the way in was the packaging, not
# the idea: the maths is theirs. The single file became the module layout every
# tool here uses, the `MOLO_*` / `molo.*` names became `SETO_*` / `seto.*`
# (a class name from another add-on registers twice the day a user has both
# installed, and the test suite finds panels by the SETO_PT_ prefix), the
# French UI strings and comments became English, and the panel moved out of its
# own "Molo" tab into this add-on's Materials section. The DDS writer it
# brought was general enough to belong to everyone, so it lives in
# shared/dds.py now.
#
# Module responsibilities:
#   geometry.py        - silhouette rasterising and the two-layer blur, pure maths
#   properties.py      - Scene-level create-time settings
#   object_settings.py - the glow's own settings and its live rebuild
#   operators.py       - create, rebuild, export to Sollumz, save DDS
#   ui.py              - N-Panel

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
