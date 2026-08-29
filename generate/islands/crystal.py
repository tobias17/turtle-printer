"""
Crystal Geode Floating Island Generator for Minecraft
=========================================================

A crystal-cave island variant: pale calcite crust over neutral geode rock
(tuff, deepslate, smooth basalt), studded with amethyst growths breaking
through the top and hanging as crystal "icicles" off the underside instead
of the usual rocky root-drips. The amethyst is deliberately kept as sparse
decoration rather than bulk fill, so it reads as crystal growing out of
plain rock rather than the island being made of solid gemstone.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the crystal-
specific block choices and decoration.

Usage:
    python crystal.py --diameter 40
    python crystal.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Neutral geode-cave rock, pale at the surface and darkening with depth.
# Amethyst is handled separately (as decoration/drips), not part of the
# bulk gradient.
GRADIENT = [
    "minecraft:calcite",
    "minecraft:tuff",
    "minecraft:deepslate",
    "minecraft:smooth_basalt",
]

AMETHYST_FLECK_CHANCE = 0.015  # rare crystal breaking through the bulk rock


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    calcite crust, 1 = deepest rock). `jitter` blends toward a neighboring
    shade for per-column/per-voxel randomness instead of a perfectly smooth
    band."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    pos = min(max(pos, 0.0), n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    block = GRADIENT[hi] if rng.random() < frac else GRADIENT[lo]
    if rng.random() < AMETHYST_FLECK_CHANCE:
        block = "minecraft:amethyst_block"
    return block


def pick_calcite_crust(rng):
    """Top-crust / shallow-band block: calcite with a rare amethyst fleck
    already breaking the surface."""
    return "minecraft:amethyst_block" if rng.random() < 0.03 else "minecraft:calcite"


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one crystal-geode
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of calcite-crust layers, before
                       the tuff/deepslate/basalt gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is an
                       amethyst crystal spike, not rock.
    decorate_top     - if True, scatters amethyst clusters and small
                       crystal-studded outcrops on top.
    decorate_underside - hanging amethyst spikes on the underside. On by
                       default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_calcite_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_calcite_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter + rng.uniform(-0.9, 0.9))

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )

    if decorate_underside:
        # crystal spikes are their own amethyst palette, distinct from the
        # neutral bulk rock - solid amethyst body, a cluster of "petals" at
        # the tip so it reads as a growing crystal rather than a rock icicle.
        def drip_block(rng, t, is_tip):
            if is_tip:
                return "minecraft:amethyst_cluster" if rng.random() < 0.6 else "minecraft:budding_amethyst"
            return "minecraft:amethyst_block"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # small bare crystal shards near the outer rim
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:amethyst_cluster" if rng.random() < 0.5 else "minecraft:amethyst_block",
            r_frac_threshold=0.55, chance=0.1, length_range=(1, 2),
        )

    if decorate_top:
        # sparse individual crystal florets on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.1:
                blocks.setdefault((x, topY + 1, z), "minecraft:amethyst_cluster")

        # a couple of small budding-amethyst outcrops, bristling with clusters
        outcrop_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(outcrop_spots)
        for (x, z, topY, depth, r, localR) in outcrop_spots[: rng.randint(0, 3)]:
            mound_h = rng.randint(1, 2)
            for dy in range(mound_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:budding_amethyst"
            top_y = topY + 1 + mound_h
            for dx in range(-1, 2):
                for dz in range(-1, 2):
                    if dx == 0 and dz == 0:
                        continue
                    if rng.random() < 0.6:
                        blocks.setdefault((x + dx, top_y, z + dz), "minecraft:amethyst_cluster")

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big crystal island plus satellites and floating rock/crystal debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:amethyst_block")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:calcite": "#e8e4d0",
    "minecraft:tuff": "#6a6b64",
    "minecraft:deepslate": "#393a3d",
    "minecraft:smooth_basalt": "#4a484c",
    "minecraft:amethyst_block": "#8f5fd1",
    "minecraft:budding_amethyst": "#7c4fc0",
    "minecraft:amethyst_cluster": "#a875e0",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a crystal-geode floating island for Minecraft.",
        out_default="crystal_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"crystal floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"crystal multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging amethyst crystal spikes (default: auto-scales with "
                         "the island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter amethyst clusters and outcrops on top (off by default)",
    )


if __name__ == "__main__":
    main()
