"""The props Trash Scatter places, and everything known about them.

Every entry is a **vanilla GTA V archetype**, verified against the game's own
ytyp data (name, bbMin, bbMax measured from the extracted archetypes, not
guessed). That is the whole trick of the tool: the scattered objects are
plain wireframe boxes in Blender, but each one is registered as an MLO
entity by archetype name, so in game the engine streams the real prop -
paper with its own texture, a cigarette butt with its own model - at zero
geometry cost to the interior itself.

The bounding box serves three jobs: the proxy box the user sees is built
from it, the prop is grounded by it (origin lifted so bbMin.z sits on the
floor), and the spacing radius that keeps two props from overlapping comes
from its footprint.

Weights are per-preset, not per-prop: cigarette butts are everywhere and
newspapers are rare, which is a fact about litter, not about the archetype.
"""

# name -> (bb_min, bb_max) in metres, relative to the prop's own origin.
PROPS = {
    "hei_prop_hei_paper_bag": ((-0.0905, -0.0536, -0.1289), (0.0905, 0.0536, 0.1289)),
    "ng_proc_cigarette01a": ((-0.07, -0.0041, -0.0041), (0.016, 0.0041, 0.0041)),
    "ng_proc_litter_plasbot1": ((-0.0534, -0.1897, 0.0005), (0.0534, 0.1671, 0.1072)),
    "ng_proc_litter_plasbot2": ((-0.0769, -0.2011, -0.0001), (0.0769, 0.1958, 0.1007)),
    "ng_proc_paper_01a": ((-0.1039, -0.0838, 0.0049), (0.1303, 0.0838, 0.1125)),
    "ng_proc_paper_02a": ((-0.1552, -0.1742, 0.0012), (0.1477, 0.1742, 0.0474)),
    "ng_proc_paper_03a": ((-0.1437, -0.1961, 0.0056), (0.1328, 0.2006, 0.0232)),
    "ng_proc_paper_burger01a": ((-0.1769, -0.1899, -0.0029), (0.1904, 0.1816, 0.0209)),
    "ng_proc_paper_mag_1a": ((-0.2041, -0.2869, 0.0), (0.2041, 0.2869, 0.0402)),
    "ng_proc_paper_news_quik": ((-0.2827, -0.253, 0.0), (0.2827, 0.253, 0.0542)),
    "ng_proc_sodabot_01a": ((-0.0447, -0.0447, 0.0), (0.0447, 0.0447, 0.299)),
    "ng_proc_sodacan_01a": ((-0.0488, -0.0488, 0.0003), (0.0488, 0.0488, 0.1576)),
    "ng_proc_sodacan_02a": ((-0.0507, -0.0836, -0.0003), (0.0507, 0.087, 0.1006)),
    "ng_proc_sodacan_03a": ((-0.0572, -0.094, -0.0006), (0.0572, 0.094, 0.0543)),
    "ng_proc_sodacan_04a": ((-0.0584, -0.0863, -0.0001), (0.0584, 0.0863, 0.0141)),
    "prop_amb_ciggy_01": ((-0.0758, -0.0036, -0.0036), (0.0161, 0.0036, 0.0036)),
    "prop_beer_bottle": ((-0.0375, -0.0374, 0.0), (0.0375, 0.0374, 0.2828)),
    "prop_bottle_cap_01": ((-0.0156, -0.0163, -0.0032), (0.0156, 0.0163, 0.0032)),
    "prop_cliff_paper": ((-0.2197, -0.1011, -0.0135), (0.2197, 0.099, 0.0162)),
    "prop_cs_ciggy_01": ((-0.0758, -0.0042, -0.0042), (0.0161, 0.0042, 0.0042)),
    "prop_cs_ciggy_01b": ((-0.0711, -0.0041, -0.0041), (0.0161, 0.0041, 0.0041)),
    "prop_cs_glass_scrap": ((-0.0507, -0.0316, -0.0071), (0.0507, 0.0316, 0.0049)),
    "prop_cs_paper_cup": ((-0.0398, -0.0446, -0.0306), (0.049, 0.0443, 0.0864)),
    "prop_ecola_can": ((-0.0358, -0.0358, -0.0642), (0.0358, 0.0358, 0.063)),
    "prop_food_bs_burg1": ((-0.0883, -0.0842, -0.0002), (0.0883, 0.0842, 0.0956)),
    "prop_food_bs_chips": ((-0.0688, -0.0247, 0.0006), (0.0688, 0.0247, 0.1613)),
    "prop_ld_can_01": ((-0.0358, -0.0358, -0.0642), (0.0358, 0.0358, 0.063)),
    "prop_ld_scrap": ((-0.1071, -0.153, -0.0086), (0.1071, 0.153, 0.0086)),
    "prop_paper_bag_small": ((-0.0733, -0.0368, -0.0331), (0.0733, 0.0291, 0.1021)),
    "prop_paper_ball": ((-0.0502, -0.0415, -0.0408), (0.0528, 0.0495, 0.0447)),
    "prop_rock_5_smash1": ((-0.1199, -0.1087, -0.0551), (0.1198, 0.1087, 0.0551)),
    "prop_rub_litter_05": ((-0.2586, -0.2289, 0.0), (0.2586, 0.229, 0.0227)),
    "prop_rub_litter_09": ((-0.1482, -0.2115, -0.0448), (0.1727, 0.2142, 0.0337)),
    "prop_rub_litter_8": ((-0.2074, -0.1661, 0.0026), (0.2046, 0.169, 0.1818)),
    "ng_proc_leaves02": ((-0.0876, -0.1849, 0.005), (0.0876, 0.1849, 0.0171)),
    "ng_proc_leaves03": ((-0.0385, -0.1018, 0.005), (0.0385, 0.1018, 0.0178)),
    "ng_proc_leaves04": ((-0.2023, -0.0829, 0.005), (0.2023, 0.0829, 0.0126)),
    "ng_proc_leaves05": ((-0.1537, -0.0905, 0.005), (0.1286, 0.1254, 0.0423)),
    "ng_proc_leaves06": ((-0.1051, -0.0686, 0.005), (0.1051, 0.0686, 0.0129)),
    "ng_proc_leaves07": ((-0.078, -0.137, 0.005), (0.078, 0.1369, 0.0423)),
    "ng_proc_leaves08": ((-0.1092, -0.0475, 0.005), (0.1092, 0.0475, 0.0141)),
    "p_cs_leaf_s": ((-0.1217, -0.1241, -0.0009), (0.1228, 0.123, 0.0)),
}

# preset id -> list of (archetype name, weight). Weights are relative within
# the preset; the ratios are what litter actually looks like: butts and
# papers everywhere, a newspaper or a burger box now and then.
PRESETS = {
    'TRASH': (
        ("prop_amb_ciggy_01", 4), ("prop_cs_ciggy_01", 4),
        ("prop_cs_ciggy_01b", 4), ("ng_proc_cigarette01a", 4),
        ("ng_proc_paper_01a", 3), ("ng_proc_paper_02a", 3),
        ("ng_proc_paper_03a", 3), ("prop_paper_ball", 4),
        ("ng_proc_paper_burger01a", 2), ("prop_cliff_paper", 2),
        ("prop_ld_scrap", 2), ("ng_proc_paper_news_quik", 1),
        ("ng_proc_paper_mag_1a", 1),
        ("ng_proc_sodacan_01a", 2), ("ng_proc_sodacan_02a", 2),
        ("ng_proc_sodacan_03a", 2), ("ng_proc_sodacan_04a", 2),
        ("prop_ld_can_01", 2), ("prop_ecola_can", 2),
        ("ng_proc_sodabot_01a", 2), ("prop_beer_bottle", 2),
        ("ng_proc_litter_plasbot1", 2), ("ng_proc_litter_plasbot2", 1),
        ("prop_cs_paper_cup", 2), ("prop_food_bs_burg1", 1),
        ("prop_food_bs_chips", 1), ("prop_paper_bag_small", 1),
        ("hei_prop_hei_paper_bag", 1),
        ("prop_cs_glass_scrap", 2), ("prop_bottle_cap_01", 2),
        ("prop_rub_litter_05", 1), ("prop_rub_litter_8", 1),
        ("prop_rub_litter_09", 1),
    ),
    'DIRT': (
        ("ng_proc_leaves02", 3),
        ("ng_proc_leaves03", 3), ("ng_proc_leaves04", 3),
        ("ng_proc_leaves05", 3), ("ng_proc_leaves06", 3),
        ("ng_proc_leaves07", 3), ("ng_proc_leaves08", 3),
        ("p_cs_leaf_s", 2), ("prop_rock_5_smash1", 1),
    ),
}

# Rubble and Spills shipped briefly and were removed at the owner's
# request; the Floor Dirt overlay covers what Spills was for, and better.
PRESET_ITEMS = (
    ('TRASH', "Trash",
     "Litter: cigarette butts, paper, crushed cans, bottles, food wrappers"),
    ('DIRT', "Dirt & Leaves",
     "Ground grime: drifts of dead leaves and the odd small stone"),
)


def footprint_radius(name):
    """Half the footprint diagonal - the spacing radius geometry.py uses.

    The full half-diagonal keeps everything so far apart the floor looks
    curated; litter genuinely touches. 0.6 of it lets edges approach without
    the boxes interpenetrating visibly.
    """
    bb_min, bb_max = PROPS[name]
    half_x = (bb_max[0] - bb_min[0]) / 2.0
    half_y = (bb_max[1] - bb_min[1]) / 2.0
    return ((half_x * half_x + half_y * half_y) ** 0.5) * 0.6


def ground_offset(name):
    """How far above the surface the prop's origin sits when it rests on it."""
    return -PROPS[name][0][2]


def is_standing(name):
    """Whether this prop stands upright - a bottle, a can, a chip bag.

    Standing props are the ones the Topple slider may lay on their side:
    real litter is mostly knocked over. Any prop even slightly taller
    than its footprint counts - a chip bag or a paper cup standing to
    attention reads as staged just as much as a bottle does (field-
    tested in game; the threshold started at 1.4 and let both stand).
    Papers, slicks and butts fail it and always lie flat.
    """
    bb_min, bb_max = PROPS[name]
    height = bb_max[2] - bb_min[2]
    footprint = max(bb_max[0] - bb_min[0], bb_max[1] - bb_min[1])
    return height > footprint * 1.05


def ground_offset_lying(name):
    """The origin height when the prop lies on its side.

    Lying is a +90° roll around local X, which maps local Y up: the
    corner that ends lowest is bb_min.y, so that is what rests on the
    floor.
    """
    return -PROPS[name][0][1]


def lying_radius(name):
    """The spacing radius when the prop lies down - its X-Z footprint."""
    bb_min, bb_max = PROPS[name]
    half_x = (bb_max[0] - bb_min[0]) / 2.0
    half_z = (bb_max[2] - bb_min[2]) / 2.0
    return ((half_x * half_x + half_z * half_z) ** 0.5) * 0.6
