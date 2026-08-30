"""
Block name compatibility layer: generate/'s modern (1.13+ flattened) block
names -> Minecraft 1.12.2 legacy (registry name, block_data meta) pairs,
for importing generated structures into a real 1.12.2 (Forge/MeatballCraft)
world save with world_import/import_structure.py.

generate/ intentionally keeps using modern, self-descriptive block names
(see AGENTS.md) - one name per concept, no separate metadata dimension -
because that's the clearer representation for procedural generation code.
1.12.2 has no such names: every block is a per-world-assigned numeric id
(see a save's level.dat -> FML.Registries -> "minecraft:blocks" -> "ids",
which amulet-core reads automatically) plus a 4-bit metadata nibble, and
the pre-1.13 registry names/metas often don't correspond 1:1 with their
modern split-out names - e.g. every wood species' log/leaves were ONE
block with a species meta, not a separate block per species, and several
modern blocks (blackstone, deepslate, mud, honeycomb, amethyst, moss,
coral, mangrove, tuff, calcite, ...) didn't exist in 1.12.2 at all.

LEGACY_MAP is a complete, hand-curated table: every block name any
generate/ module currently produces maps to an explicit (legacy base
name, block_data meta) pair - checked against this project's actual
BLOCK_COLORS dicts, not guessed in the abstract. Nothing falls back to an
automatic/guessed substitute at import time: translate_block() raises on
any name not listed here, so a newly added theme/block is caught
immediately instead of silently placing the wrong (or a nonexistent)
block. Two categories:

  1. Blocks with a genuine pre-1.13 equivalent - the (name, meta) is
     Mojang's own official flattening conversion. A few of these are
     easy to get wrong by assuming the modern name is "close enough" to
     already be a valid legacy name - it usually isn't:
       - modern "minecraft:snow" (thin layer) is legacy "snow_layer";
         legacy "snow" is actually the SOLID snow block (modern
         "snow_block"'s legacy name) - the reverse of what the names
         suggest.
       - "minecraft:ladder[facing=west]" needs meta 4, not 0 - meta 0
         would place a ladder facing the wrong way.
       - "minecraft:brown/red_mushroom_block" (used here for a giant
         mushroom's CAP) needs meta 14 (cap texture on all six faces),
         not 0 (meta 0 is the porous "fleshy" look, meta 10 is the stem
         look reserved for "minecraft:mushroom_stem" below).
  2. Blocks with NO 1.12.2 equivalent at all - a deliberately chosen
     vanilla-1.12.2 substitute picked to preserve the original's role/
     color as closely as vanilla (no mod dependency) allows, noted
     per-entry below. These are real, considered design choices, not
     placeholders - revisit them (e.g. to swap in a nicer MeatballCraft
     mod block once its exact registry name is confirmed in-game via
     JEI - see ../MEATBALLCRAFT_MODS.md) by editing this one table, never
     the generators themselves.
"""

LEGACY_MAP = {
    # ---- clean pre-1.13 renames (Mojang's own flattening conversion) ----
    "minecraft:oak_log": ("log", 0),
    "minecraft:spruce_log": ("log", 1),
    "minecraft:birch_log": ("log", 2),
    "minecraft:oak_leaves": ("leaves", 0),
    "minecraft:oak_leaves[persistent=true]": ("leaves", 4),
    "minecraft:spruce_leaves": ("leaves", 1),
    "minecraft:birch_leaves": ("leaves", 2),
    "minecraft:birch_leaves[persistent=true]": ("leaves", 6),
    "minecraft:dark_oak_leaves[persistent=true]": ("leaves2", 5),
    "minecraft:oak_planks": ("planks", 0),
    "minecraft:grass_block": ("grass", 0),
    "minecraft:orange_wool": ("wool", 1),
    "minecraft:dandelion": ("yellow_flower", 0),
    "minecraft:fern": ("tallgrass", 2),
    "minecraft:dead_bush": ("deadbush", 0),
    "minecraft:lily_pad": ("waterlily", 0),
    "minecraft:jungle_sapling": ("sapling", 3),
    "minecraft:red_sand": ("sand", 1),
    "minecraft:terracotta": ("hardened_clay", 0),
    "minecraft:white_terracotta": ("stained_hardened_clay", 0),
    "minecraft:orange_terracotta": ("stained_hardened_clay", 1),
    "minecraft:yellow_terracotta": ("stained_hardened_clay", 4),
    "minecraft:red_terracotta": ("stained_hardened_clay", 14),
    "minecraft:mossy_stone_bricks": ("stonebrick", 1),
    "minecraft:prismarine_bricks": ("prismarine", 1),
    "minecraft:dark_prismarine": ("prismarine", 2),
    "minecraft:skeleton_skull": ("skull", 0),
    "minecraft:snow_block": ("snow", 0),           # legacy "snow" = the SOLID block (id 80)
    "minecraft:snow": ("snow_layer", 0),           # legacy "snow_layer" = the thin layer (id 78)
    "minecraft:mushroom_stem": ("brown_mushroom_block", 10),        # meta 10 = stem texture
    "minecraft:brown_mushroom_block": ("brown_mushroom_block", 14),  # meta 14 = all-cap texture
    "minecraft:red_mushroom_block": ("red_mushroom_block", 14),
    "minecraft:ladder[facing=west]": ("ladder", 4),  # legacy facing meta: 2=N,3=S,4=W,5=E

    # ---- already-correct bare legacy names (single/default variant) ----
    "minecraft:bone_block": ("bone_block", 0),
    "minecraft:brown_mushroom": ("brown_mushroom", 0),
    "minecraft:red_mushroom": ("red_mushroom", 0),
    "minecraft:cactus": ("cactus", 0),
    "minecraft:cobblestone": ("cobblestone", 0),
    "minecraft:dirt": ("dirt", 0),
    "minecraft:mossy_cobblestone": ("mossy_cobblestone", 0),
    "minecraft:mycelium": ("mycelium", 0),
    "minecraft:packed_ice": ("packed_ice", 0),
    "minecraft:purpur_block": ("purpur_block", 0),
    "minecraft:sand": ("sand", 0),
    "minecraft:sandstone": ("sandstone", 0),
    "minecraft:sea_lantern": ("sea_lantern", 0),
    "minecraft:stone": ("stone", 0),
    # meta 0 + a solid block directly above is a valid hanging vine (implicit
    # top attachment, no side-face meta bit needed) - every generator only
    # ever places these just under a solid rim/underside column, so this is
    # correct as-is, not a shortcut.
    "minecraft:vine": ("vine", 0),

    # ---- deliberate substitutes: no 1.12.2 equivalent exists at all ----
    "minecraft:amethyst_block": ("stained_hardened_clay", 10),   # purple
    "minecraft:budding_amethyst": ("stained_hardened_clay", 2),  # magenta (distinguishable purple)
    "minecraft:amethyst_cluster": ("stained_glass", 10),         # purple glass - spikier accent
    "minecraft:basalt": ("stone", 5),              # andesite
    "minecraft:polished_basalt": ("stone", 6),     # polished andesite
    "minecraft:beehive": ("pumpkin", 0),
    "minecraft:honeycomb_block": ("hardened_clay", 0),  # plain terracotta - golden/tan, close to honey
    "minecraft:blackstone": ("coal_block", 0),
    "minecraft:cobbled_deepslate": ("cobblestone", 0),
    "minecraft:deepslate": ("stone", 0),
    "minecraft:polished_blackstone_bricks": ("stonebrick", 0),
    "minecraft:blue_ice": ("diamond_block", 0),    # closest icy-blue, distinct from packed_ice
    "minecraft:brain_coral_block": ("wool", 6),    # pink
    "minecraft:fire_coral_block": ("wool", 14),    # red
    "minecraft:tube_coral_block": ("wool", 11),    # blue
    "minecraft:calcite": ("quartz_block", 0),      # pale
    "minecraft:cornflower": ("wool", 11),          # blue
    "minecraft:wither_rose": ("wool", 15),         # black
    "minecraft:kelp": ("vine", 0),
    "minecraft:sea_pickle": ("wool", 5),           # lime
    "minecraft:magma_block": ("netherrack", 0),
    "minecraft:mangrove_leaves": ("leaves", 3),    # jungle leaves
    "minecraft:mangrove_log": ("log", 3),          # jungle log
    "minecraft:mangrove_roots": ("log", 1),        # spruce log - dark, gnarled-reading bark
    "minecraft:moss_block": ("wool", 13),          # green
    "minecraft:moss_carpet": ("carpet", 13),       # green
    "minecraft:mud": ("dirt", 0),
    "minecraft:soul_lantern": ("glowstone", 0),
    "minecraft:soul_soil": ("dirt", 1),            # coarse dirt - ashy brown-grey
    "minecraft:tuff": ("stone", 5),                # andesite
}


def translate_block(modern_name):
    """modern_name ("minecraft:foo" or "minecraft:foo[prop=val]", exactly
    as it appears in a generator's BLOCK_COLORS/placement code) -> (legacy
    base name without namespace, block_data meta int).

    Raises KeyError with the offending name if it's not in LEGACY_MAP - by
    design (see module docstring): a new theme/block must be added here
    deliberately, never silently guessed at import time."""
    try:
        return LEGACY_MAP[modern_name]
    except KeyError:
        raise KeyError(
            f"No 1.12.2 mapping for block {modern_name!r} - add it to "
            f"LEGACY_MAP in world_import/block_compat.py"
        ) from None
