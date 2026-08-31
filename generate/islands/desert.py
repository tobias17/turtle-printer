"""
Desert Floating Island Generator for Minecraft
============================================================

A plain desert island variant: a sand crust on top, grading smoothly down
through sandstone into the ordinary rock core every island theme shares
underneath - a simple dune, not a banded mesa. Cacti and dead bushes dot
the top; the underside sheds bare sandstone shards instead of roots or
icicles. For the dramatic multi-color terraced badlands look, see
mesa.py - that's this theme's sibling, not a variant of it.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the desert-
specific block choices and decoration.

Usage:
    python desert.py --diameter 40
    python desert.py --diameter 40 --seed 7
"""

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Sand crust smoothly grading into sandstone, then bare rock at the core -
# a plain dune, not the stepped badlands strata mesa.py builds.
GRADIENT = [
    "minecraft:sandstone",
    "minecraft:stone",
]


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the sand
    crust, 1 = deepest rock). `jitter` (driven only by smooth per-column
    noise) nudges the whole column toward a neighboring band so the strata
    boundary is wavy instead of a razor-straight ring."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_sand_crust(rng):
    """Top-crust block: solid sand, no fleck - the crust is a flat platform."""
    return "minecraft:sand"


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one desert
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of sand-crust layers, before
                       the sandstone/rock gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       sandstone shard.
    decorate_top     - if True, scatters dead bushes and cacti on top.
    decorate_underside - hanging sandstone shards on the underside. On by
                       default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_sand_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_sand_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:sandstone"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # bare eroded sandstone shards near the outer rim (no vines in a
        # desert - just weathered rock hanging on)
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:sandstone",
            r_frac_threshold=0.55, chance=0.12, length_range=(1, 3),
        )

    if decorate_top:
        # sparse dead bushes on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.1:
                blocks.setdefault((x, topY + 1, z), "minecraft:dead_bush")

        # a couple of cacti
        cactus_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(cactus_spots)
        for (x, z, topY, depth, r, localR) in cactus_spots[: rng.randint(0, 3)]:
            cactus_h = rng.randint(2, 4)
            for dy in range(cactus_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:cactus"

    # a rim column can taper closed within its own sand-crust thickness,
    # leaving sand (gravity-affected - falls with nothing solid beneath it,
    # and can't be turtle-placed bottom-up either) exposed at the very
    # bottom - see common.fix_floating_gravity.
    common.fix_floating_gravity(blocks, columns, col_bottom, lambda x, z: "minecraft:sandstone")

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big desert island plus satellites and floating sandstone debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:sandstone")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:sand": "#e3d2a0",
    "minecraft:sandstone": "#d8c98a",
    "minecraft:stone": "#8a8a8a",
    "minecraft:dead_bush": "#8a6a3a",
    "minecraft:cactus": "#4a7a3a",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a desert floating island for Minecraft.",
        out_default="desert_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"desert floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"desert multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging sandstone shards (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter dead bushes and cacti on top (off by default)",
    )


if __name__ == "__main__":
    main()
