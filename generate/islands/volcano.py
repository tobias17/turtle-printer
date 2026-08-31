"""
Volcanic Floating Island Generator for Minecraft
=================================================

A volcanic-themed island variant: dark igneous stone instead of
grass/dirt/stone. Deliberately simple palette - a grey basalt crust on
top, black rock underneath, with no gradient banding or per-voxel noise -
plus sparse single-block magma accents scattered through the body (each
one an isolated voxel, never a vein/cluster) as the one deliberate point
of visual interest, not bulk ore texture. The interior isn't meant to be
seen in depth (these islands end up hollow once built), so most of the
visual interest still comes from the silhouette/taper/drip shape and the
crust/body color contrast. A slightly sharper underside taper than
grass.py's - a rocky mass, not just a recolored copy of the same shape.
Meant to sit around spire.py's dark tower.

Shares its silhouette/taper/drip machinery with the other island themes
in generate/islands/ (see common.py) - this file only supplies the
volcanic-specific block choices.

Outputs (into --out-dir, default generate/output/tmp):
  1. A .npz Structure (block-index array + Atlas legend) in the same
     canonical format used by tree.py/grass.py - see generate/utils.py.
  2. A 3D preview image rendered as full shaded blocks so you can check
     the shape BEFORE building anything in-game.
  3. Optionally (--schem) a WorldEdit schematic, to see it live in a
     creative-mode save.

Usage:
    python volcano.py --diameter 40
    python volcano.py --diameter 40 --seed 7
"""

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Two blocks, deliberately: a grey crust and a black body. No gradient
# stack, no noise-driven banding - "random ore and other bullshit" was
# explicitly called out as unwanted, so this stays plain apart from the
# one sparse accent below. Shape + this one color contrast is what's meant
# to read as interesting, not surface detail.
TOP_CRUST_BLOCK = "projectred_exploration:stone_basalt"
BODY_BLOCK = "minecraft:blackstone"

# Sparse magma accents through the body - single isolated voxels, never a
# vein or cluster (that's the "ore" look this theme deliberately avoids
# elsewhere). Low enough odds that most columns have none at all.
ACCENT_BLOCK = "minecraft:magma_block"
ACCENT_CHANCE = 0.015


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one volcanic
    island, positioned with its center at `offset`. Same silhouette/taper/
    drip machinery as the other island themes, but re-themed: grey basalt
    crust on top, solid black rock body, dark drips on the underside.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of crust layers before the body
                       starts. Varies smoothly across the island.
    num_drips / drip_density - see grass.py; same auto-scaling behavior.
    decorate_top     - if True, scatters small crust-block columns on top.
                       Off by default so the surface stays buildable.
    decorate_underside - hanging drips on the rock underside. On by
                       default.
    """
    size, half, radius = common.grid_dims(diameter)

    def top_block(rng, x, z, xi, zi):
        return TOP_CRUST_BLOCK

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return TOP_CRUST_BLOCK
        return ACCENT_BLOCK if rng.random() < ACCENT_CHANCE else BODY_BLOCK

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
        # a bit sharper/more concave than grass.py's default taper (both
        # pre-existing carve_columns parameters, no shared code touched) -
        # reads as a rockier, more pointed mass instead of the same rounded
        # dome shape.
        taper_strength=0.9, taper_exponent=0.5,
    )

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return BODY_BLOCK

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # a few bare hanging dark "icicles" near the outer rim (replaces
        # grass.py's draped vines)
        common.decorate_rim_underside(rng, blocks, columns, col_bottom,
                                       rim_block_fn=lambda rng: BODY_BLOCK,
                                       r_frac_threshold=0.55, chance=0.12, length_range=(1, 3))

    if decorate_top:
        # a couple of small crust-block columns (replaces grass.py's trees)
        column_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(column_spots)
        for (x, z, topY, depth, r, localR) in column_spots[: rng.randint(0, 2)]:
            col_h = rng.randint(2, 4)
            for dy in range(col_h):
                blocks[(x, topY + 1 + dy, z)] = TOP_CRUST_BLOCK

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """Ring of volcanic islands plus a couple of floating debris chunks,
    meant to sit around a central spire."""
    return common.basic_scene(seed, generate_island, debris_block=BODY_BLOCK)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "projectred_exploration:stone_basalt": "#6e6b64",
    "minecraft:blackstone": "#211f1f",
    "minecraft:magma_block": "#c9591a",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a volcanic floating island for Minecraft.",
        out_default="volcano_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"volcanic floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"volcanic multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging basalt drips (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter small basalt columns on top (off by default)",
    )


if __name__ == "__main__":
    main()
