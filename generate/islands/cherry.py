"""
Cherry Blossom Shrine Floating Island Generator for Minecraft
================================================================

A Japanese-garden island variant: instead of every other theme's single
flat top with a reshaped UNDERSIDE, this one reshapes the TOP itself into a
stepped ziggurat - a raked zen-garden ring at the rim rising through mossy
cherry groves to a small shrine deck at the peak, like rice terraces or a
pagoda's base. Five concentric rings, each a fixed few blocks taller than
the ring outside it, with earthy packed-mud/mud-brick retaining walls
forming the visible "steps" between them. Underneath, a normal earthy
taper (coarse dirt/mud/tuff/deepslate/stone) with hanging root drips -
that part stays close to grass.py's shape since the terracing on top is
what makes this theme read as different in STRUCTURE, not just palette.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the shrine-
specific block choices, the terracing post-process, and decoration.

Usage:
    python cherry.py --diameter 40
    python cherry.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Earthy crust-to-core gradient for the normal tapering underside (below the
# terraced top, unaffected by it) - kept to 2 solid bands (no fleck/dither).
GRADIENT = [
    "minecraft:coarse_dirt",
    "minecraft:stone",
]

# Concentric terrace rings: TIER_THRESHOLDS splits r/localR into 5 bands
# (rim ring = tier 0, up through tier 4 at the very center), each tier
# TIER_HEIGHT blocks taller than the one outside it. Each ring is a single
# solid color - the terracing itself carries the "shape", so no per-voxel
# color variety is needed on top of it.
TIER_THRESHOLDS = [0.78, 0.58, 0.38, 0.18]
TIER_HEIGHT = 3

TIER_CRUST = [
    "minecraft:grass_block",
    "minecraft:moss_block",
    "minecraft:podzol",
    "minecraft:mud_bricks",
    "minecraft:cherry_planks",
]

RISER_BLOCK = "minecraft:packed_mud"


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the crust,
    1 = deepest rock). `jitter` (driven only by smooth per-column noise)
    nudges the whole column toward a neighboring shade so the band edge is
    wavy instead of a razor-straight ring, without per-voxel dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_tier_crust(rng, tier):
    """Walking-surface block for a given terrace ring: solid grass at the
    rim (tier 0), grading through moss and cherry-grove floor, to a solid
    wooden shrine deck at the peak (tier 4). Each ring is one flat color."""
    return TIER_CRUST[tier]


def pick_riser(rng):
    """Vertical retaining-wall block filling the step between two terraces."""
    return RISER_BLOCK


def _terrace_tiers(blocks, col_bottom, columns, rng):
    """Post-processes the already-carved (unmodified common.carve_columns)
    TOP into a stepped ziggurat instead of a single flat plane. Every other
    theme so far reshapes the UNDERSIDE (a shelf, a skirt, terraced tiers,
    towers) while keeping the flat walkable top untouched; this one flips
    which side gets reshaped - the underside stays a normal taper, and the
    top rises in 5 concentric rings toward the center, each TIER_HEIGHT
    blocks taller than the ring outside it, with a filled riser column
    forming the visible cliff face of each step.

    Only ever ADDS blocks above each column's original topY (like a drip in
    reverse) and updates col_bottom/columns' topY entries so downstream code
    (this file's own decorate_top) places trees/lanterns on the new walking
    surface; bottomY and everything below is untouched, so drips/rim
    underside decoration read the same real depths as any other theme.
    Deliberately local to cherry.py rather than a carve_columns option, so
    no other theme is affected.

    Returns tier_of: {(x, z): tier} for use by decorate_top.
    """
    def tier_for_frac(frac):
        tier = 0
        for th in TIER_THRESHOLDS:
            if frac < th:
                tier += 1
        return tier

    tier_of = {}
    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        frac = r / localR if localR else 1.0
        tier = tier_for_frac(frac)
        tier_of[(x, z)] = tier
        if tier == 0:
            new_columns.append((x, z, topY, depth, r, localR))
            continue
        extra = tier * TIER_HEIGHT
        for y in range(topY + 1, topY + extra):
            blocks[(x, y, z)] = pick_riser(rng)
        new_top = topY + extra
        blocks[(x, new_top, z)] = pick_tier_crust(rng, tier)
        bottomY, _, _, _ = col_bottom[(x, z)]
        col_bottom[(x, z)] = (bottomY, new_top, r, localR)
        new_columns.append((x, z, new_top, depth, r, localR))
    columns[:] = new_columns
    return tier_of


def generate_island(seed=0, diameter=40, top_thickness_range=(3, 5), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one cherry-blossom
    shrine island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), carve_columns's own top surface is
                       flat; _terrace_tiers then rises the center of it into
                       a stepped ziggurat regardless (see module docstring).
    top_thickness_range - (min, max) number of crust layers before the
                       earthy underside gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       root.
    decorate_top     - if True, scatters zen-garden petals, cherry trees and
                       a shrine lantern on the terraced top.
    decorate_underside - hanging root drips on the underside. On by default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_tier_crust(rng, 0)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_tier_crust(rng, 0)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
        taper_strength=0.8, taper_exponent=0.75,
    )
    # rise the top into a 5-ring stepped ziggurat - see _terrace_tiers above.
    tier_of = _terrace_tiers(blocks, col_bottom, columns, rng)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:hanging_roots" if is_tip else "minecraft:coarse_dirt"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # a few bare hanging roots near the outer rim
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:hanging_roots",
            r_frac_threshold=0.55, chance=0.16, length_range=(2, 5),
        )

    if decorate_top:
        # zen-garden petal litter on the outer ring, cherry trees higher up
        tree_spots = []
        for (x, z, topY, depth, r, localR) in columns:
            tier = tier_of.get((x, z), 0)
            if tier == 0 and rng.random() < 0.08:
                blocks.setdefault((x, topY + 1, z), "minecraft:pink_petals")
            elif tier >= 2 and rng.random() < 0.05:
                tree_spots.append((x, z, topY))

        rng.shuffle(tree_spots)
        for (x, z, topY) in tree_spots[: rng.randint(2, 5)]:
            trunk_h = rng.randint(3, 5)
            for dy in range(trunk_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:cherry_log"
            leaf_y = topY + 1 + trunk_h
            for dx in range(-2, 3):
                for dz in range(-2, 3):
                    for dy in range(0, 3):
                        if dx * dx + dz * dz + dy * dy <= 5 and rng.random() < 0.8:
                            blocks.setdefault((x + dx, leaf_y + dy, z + dz), "minecraft:cherry_leaves")
            for _ in range(rng.randint(2, 5)):
                px, pz = x + rng.randint(-2, 2), z + rng.randint(-2, 2)
                blocks.setdefault((px, topY + 1, pz), "minecraft:pink_petals")

        # a single shrine lantern at the very peak (the tier-4 column
        # closest to center)
        peak_spots = [c for c in columns if tier_of.get((c[0], c[1]), 0) == 4]
        if peak_spots:
            x, z, topY, depth, r, localR = min(peak_spots, key=lambda c: c[4])
            blocks[(x, topY + 1, z)] = "minecraft:lantern"

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big cherry-blossom shrine island plus satellites and floating
    packed-mud debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:packed_mud")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:grass_block": "#5b8a3a",
    "minecraft:moss_block": "#5a7a2f",
    "minecraft:podzol": "#5b3d23",
    "minecraft:mud_bricks": "#8c6b52",
    "minecraft:packed_mud": "#9c7b5c",
    "minecraft:cherry_planks": "#e3b6c5",
    "minecraft:coarse_dirt": "#6b4a2b",
    "minecraft:stone": "#8a8a8a",
    "minecraft:hanging_roots": "#6b4a35",
    "minecraft:cherry_log": "#8a5a68",
    "minecraft:cherry_leaves": "#e5a3c0",
    "minecraft:pink_petals": "#f2b8d0",
    "minecraft:lantern": "#e8c15a",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a cherry-blossom shrine floating island for Minecraft.",
        out_default="cherry_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"cherry blossom shrine floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"cherry blossom shrine multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging root drips (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter petals, cherry trees and a shrine lantern on top (off by default)",
    )


if __name__ == "__main__":
    main()
