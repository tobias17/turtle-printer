"""
Frozen Floating Island Generator for Minecraft
===============================================

A frozen/tundra island variant: a snow crust on top, grading down through
packed ice and blue ice, then into the plain rock core every island theme
shares underneath (stone/andesite) - like a chunk of frozen tundra torn
free of the ground, ice near the surface, bare rock deeper down. The
underside grows actual icicles (ice/packed ice, blue ice tips) rather than
the rocky root-drips the other themes use.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the frozen-
specific block choices and decoration.

Usage:
    python snow.py --diameter 40
    python snow.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Icy crust down to a bare rock core - deliberately doesn't stay ice all the
# way down, so the underside reads as "frozen chunk of ground", not a solid
# iceberg.
GRADIENT = [
    "minecraft:snow_block",
    "minecraft:packed_ice",
    "minecraft:blue_ice",
    "minecraft:stone",
    "minecraft:andesite",
]

SPARKLE_CHANCE = 0.02  # rare blue-ice fleck at any depth, for a bit of glint


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the snow
    crust, 1 = deepest rock). `jitter` blends toward a neighboring shade for
    per-column/per-voxel randomness instead of a perfectly smooth band."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    pos = min(max(pos, 0.0), n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    block = GRADIENT[hi] if rng.random() < frac else GRADIENT[lo]
    if rng.random() < SPARKLE_CHANCE:
        block = "minecraft:blue_ice"
    return block


def pick_snow_crust(rng):
    """Top-crust / shallow-band block: snow with a rare packed-ice fleck
    breaking through."""
    return "minecraft:packed_ice" if rng.random() < 0.05 else "minecraft:snow_block"


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one frozen
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of snow-crust layers, before
                       the ice/rock gradient starts. Varies smoothly.
    num_drips / drip_density - see grass.py; same auto-scaling behavior,
                       but here each "drip" is an icicle (see below).
    decorate_top     - if True, scatters snow layers + spruce trees on top.
    decorate_underside - hanging icicles on the underside. On by default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    # coarse + fine noise so the ice/rock banding isn't a smooth gradient
    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    # a coarse noise field whose zero-crossings trace thin, web-like lines
    # across the top - read as frost cracks in the ice sheet breaking
    # through the snow, instead of the same random single-block fleck every
    # other theme uses for its crust.
    crack_noise = common.value_noise_2d(size, grid_for(3, 6), seed + 21)
    CRACK_THRESHOLD = 0.05

    def top_block(rng, x, z, xi, zi):
        if abs(crack_noise[xi, zi]) < CRACK_THRESHOLD:
            return "minecraft:blue_ice" if rng.random() < 0.6 else "minecraft:packed_ice"
        return pick_snow_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_snow_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter + rng.uniform(-0.9, 0.9))

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
        # a steeper, more concave taper than the other themes' (these are
        # both existing carve_columns parameters - no shared code touched) -
        # glacial undersides are sharply undercut, not a gentle dome.
        taper_strength=0.95, taper_exponent=0.5,
    )

    if decorate_underside:
        # icicles are their own small ice palette, distinct from the rocky
        # gradient the island's body ends in - they read as ice growing off
        # the frozen underside, not more of the core rock.
        def drip_block(rng, t, is_tip):
            if is_tip:
                return "minecraft:blue_ice"
            return "minecraft:ice" if rng.random() < 0.35 else "minecraft:packed_ice"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # short bare icicle shards near the outer rim
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:ice" if rng.random() < 0.7 else "minecraft:packed_ice",
            r_frac_threshold=0.55, chance=0.15, length_range=(1, 4),
        )

    if decorate_top:
        # sparse snow-layer decoration on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.14:
                blocks.setdefault((x, topY + 1, z), "minecraft:snow")

        # a couple of small spruce trees
        tree_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(tree_spots)
        for (x, z, topY, depth, r, localR) in tree_spots[: rng.randint(0, 2)]:
            trunk_h = rng.randint(3, 6)
            for dy in range(trunk_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:spruce_log"
            leaf_base = topY + 1 + max(1, trunk_h - 3)
            for dy in range(0, 4):
                leaf_r = max(0, 2 - dy // 2)
                for dx in range(-leaf_r, leaf_r + 1):
                    for dz in range(-leaf_r, leaf_r + 1):
                        if dx * dx + dz * dz <= leaf_r * leaf_r + 1 and rng.random() < 0.9:
                            blocks.setdefault((x + dx, leaf_base + dy, z + dz), "minecraft:spruce_leaves")

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big frozen island plus satellites and floating ice debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:packed_ice")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:snow_block": "#eef4fa",
    "minecraft:snow": "#ffffff",
    "minecraft:packed_ice": "#a8d2e8",
    "minecraft:blue_ice": "#74b9e0",
    "minecraft:ice": "#9fd0e8",
    "minecraft:stone": "#8a8a8a",
    "minecraft:andesite": "#a3a3a0",
    "minecraft:spruce_log": "#3b2a1a",
    "minecraft:spruce_leaves": "#3a5a45",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a frozen floating island for Minecraft.",
        out_default="snow_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"frozen floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"frozen multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging icicles (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter snow + spruce trees on top (off by default)",
    )


if __name__ == "__main__":
    main()
