"""
Desert / Badlands Floating Island Generator for Minecraft
============================================================

A desert/mesa island variant: a sand crust on top, grading down through
banded sandstone and terracotta (like eroded badlands strata) into the
plain rock core every island theme shares underneath. Cacti and dead
bushes dot the top; the underside sheds bare sandstone shards instead of
roots or icicles.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the desert-
specific block choices and decoration.

Usage:
    python desert.py --diameter 40
    python desert.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Sand crust down through banded sandstone/terracotta (badlands-style
# strata) into bare rock at the core.
GRADIENT = [
    "minecraft:sand",
    "minecraft:sandstone",
    "minecraft:orange_terracotta",
    "minecraft:terracotta",
    "minecraft:stone",
]

FLECK_CHANCE = 0.02  # rare red-sandstone fleck at any depth, for banding variety
NUM_TERRACES = 5  # how many mesa shelves the underside steps through, regardless of size


def _terrace_columns(blocks, col_bottom, columns, band_size):
    """Post-processes an already-carved island (from the ordinary, unmodified
    common.carve_columns) so each column's underside depth snaps down to the
    nearest multiple of `band_size`, instead of the smooth continuous taper
    every other theme uses. This only ever *removes* already-carved blocks
    (never invents new ones) and keeps col_bottom/columns in sync, so drips
    and rim decoration - which read those to find each column's true bottom -
    still attach cleanly to the new, shallower surface.

    Deliberately local to desert.py rather than a carve_columns option: this
    is the one theme that wants a genuinely different taper *shape* (stacked
    badlands shelves instead of a cone), and keeping the change here means
    the shared carve loop every other theme depends on is never touched.
    """
    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        bottomY, _, _, _ = col_bottom[(x, z)]
        new_depth = band_size * (depth // band_size)
        if new_depth == 0:
            new_depth = depth  # already thinner than one shelf - leave it
        new_bottomY = topY - new_depth
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)
        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, new_depth, r, localR))
    columns[:] = new_columns


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the sand
    crust, 1 = deepest rock). `jitter` blends toward a neighboring shade for
    per-column/per-voxel randomness so the strata read as banded, not a
    perfectly smooth gradient."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    pos = min(max(pos, 0.0), n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    block = GRADIENT[hi] if rng.random() < frac else GRADIENT[lo]
    if rng.random() < FLECK_CHANCE:
        block = "minecraft:red_sandstone"
    return block


def pick_sand_crust(rng):
    """Top-crust / shallow-band block: sand with a rare red-sand fleck."""
    return "minecraft:red_sand" if rng.random() < 0.08 else "minecraft:sand"


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one desert
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of sand-crust layers, before
                       the sandstone/terracotta gradient starts.
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

    # a handful of big shelves regardless of island size, so the terracing
    # always reads as a few bold mesa steps rather than many thin bands that
    # blur back into a smooth cone at larger diameters.
    band_size = max(2, max_depth // NUM_TERRACES)

    def top_block(rng, x, z, xi, zi):
        return pick_sand_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_sand_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        # quantize into the same shelves the silhouette gets stepped into
        # below, so each terrace reads as one solid stratum (with the usual
        # per-voxel jitter for texture) instead of a smooth color blend -
        # that's what actually makes it look like badlands strata.
        depth_bands = max(1, (thickness - 1 + max_depth) // band_size)
        band_t = math.floor(min(max(t_grad, 0.0), 0.999999) * depth_bands) / depth_bands
        return pick_gradient(rng, band_t, jitter=g_jitter + rng.uniform(-0.5, 0.5))

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # step the smooth taper this just produced down into discrete mesa
    # shelves - see _terrace_columns above.
    _terrace_columns(blocks, col_bottom, columns, band_size)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:red_sand" if is_tip else "minecraft:sandstone"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # bare eroded sandstone shards near the outer rim (no vines in a
        # desert - just weathered rock hanging on)
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:sandstone" if rng.random() < 0.7 else "minecraft:red_sandstone",
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
    "minecraft:red_sand": "#bf6a3a",
    "minecraft:sandstone": "#d8c98a",
    "minecraft:red_sandstone": "#9c5028",
    "minecraft:orange_terracotta": "#a34d27",
    "minecraft:terracotta": "#8f5a44",
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
