"""
Coral Reef Floating Island Generator for Minecraft
====================================================

A coral-reef island variant: a pale sandy reef-rock crust on top, grading
down through sandstone and calcite into the plain rock core every island
theme shares underneath. Rather than a solid tapering mass, the underside
is mostly eroded down to a shallow shelf, with clumped patches of vividly
colored coral blocks branching down further than the surrounding rock -
like real coral colonies growing off a reef shelf, not a uniform cone.
Sea pickles glow among the coral; kelp fringes hang from the rim.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the reef-
specific block choices and decoration.

Usage:
    python coral.py --diameter 40
    python coral.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Pale reef-rock crust down to the plain rock core. Coral itself is handled
# separately (as a post-process over sparse branch columns), not part of
# the bulk gradient.
GRADIENT = [
    "minecraft:sand",
    "minecraft:sandstone",
    "minecraft:calcite",
    "minecraft:clay",
    "minecraft:stone",
]

CORAL_BLOCKS = [
    "minecraft:tube_coral_block",
    "minecraft:brain_coral_block",
    "minecraft:bubble_coral_block",
    "minecraft:fire_coral_block",
    "minecraft:horn_coral_block",
]

FLECK_CHANCE = 0.02  # rare clay fleck at any depth, for banding variety
BRANCH_THRESHOLD = 0.45  # clumping-noise cutoff for where coral colonies grow
STUB_FRAC = 0.22  # how shallow the eroded (non-branch) columns become


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
        block = "minecraft:clay"
    return block


def pick_reef_crust(rng):
    """Top-crust / shallow-band block: sand with a rare coral head already
    poking through the sea floor."""
    return "minecraft:tube_coral_block" if rng.random() < 0.04 else "minecraft:sand"


def _reef_branches(blocks, col_bottom, columns, rng, size, half, seed, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside so it reads as a reef shelf with sparse coral colonies growing
    off it, instead of a solid tapering mass: a clumped noise field marks a
    patchwork of columns as "coral branches" that keep their full natural
    depth (recolored as vivid coral), while every other column - the eroded
    reef rock - is hard-capped to a shallow stub. The clumping (rather than
    an independent per-column chance) is what makes the coral read as
    colonies growing in patches, not salt-and-pepper speckle.

    Like desert.py's mesa terracing, this only ever *removes* already-carved
    blocks (branch columns are recolored, never extended) and keeps
    col_bottom/columns in sync (drips/rim decoration read those for each
    column's true bottom), and is deliberately local to coral.py rather than
    a carve_columns option, so no other theme is affected.
    """
    clump_noise = common.value_noise_2d(size, max(3, size // 12), seed + 51)
    stub_depth = max(3, int(max_depth * STUB_FRAC))
    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        is_branch = clump_noise[x + half, z + half] > BRANCH_THRESHOLD
        if is_branch or depth <= stub_depth:
            if is_branch:
                bottomY, _, _, _ = col_bottom[(x, z)]
                for y in range(bottomY, topY):
                    if rng.random() < 0.8:
                        blocks[(x, y, z)] = rng.choice(CORAL_BLOCKS)
            new_columns.append((x, z, topY, depth, r, localR))
            continue
        bottomY, _, _, _ = col_bottom[(x, z)]
        new_bottomY = topY - stub_depth
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)
        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, stub_depth, r, localR))
    columns[:] = new_columns


def generate_island(seed=0, diameter=40, top_thickness_range=(3, 5), max_depth=14,
                     num_drips=None, drip_density=0.08, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one coral-reef
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of sand-crust layers, before
                       the sandstone/calcite/clay gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       coral spur.
    decorate_top     - if True, scatters sea pickles and kelp on top.
    decorate_underside - coral-branch shaping plus hanging coral spurs and
                       kelp fringe on the underside. On by default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_reef_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_reef_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter + rng.uniform(-0.9, 0.9))

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # erode most of the underside to a shelf, leaving sparse coral colonies
    # branching down further - see _reef_branches above.
    _reef_branches(blocks, col_bottom, columns, rng, size, half, seed, max_depth)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            if is_tip:
                return rng.choice(CORAL_BLOCKS)
            return "minecraft:tube_coral_block" if rng.random() < 0.4 else "minecraft:sandstone"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # kelp/sea-pickle fringe draped from the rim (replaces the other
        # themes' vines/icicles/roots)
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:sea_pickle" if rng.random() < 0.3 else "minecraft:kelp",
            r_frac_threshold=0.5, chance=0.3, length_range=(2, 6),
        )

    if decorate_top:
        # sparse sea pickle clusters and kelp stalks on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.12:
                blocks.setdefault((x, topY + 1, z), "minecraft:sea_pickle")

        kelp_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(kelp_spots)
        for (x, z, topY, depth, r, localR) in kelp_spots[: rng.randint(0, 4)]:
            kelp_h = rng.randint(2, 5)
            for dy in range(kelp_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:kelp"

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big coral-reef island plus satellites and floating sandstone/
    coral debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:sandstone")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:sand": "#e3d2a0",
    "minecraft:sandstone": "#d8c98a",
    "minecraft:calcite": "#e8e4d0",
    "minecraft:clay": "#9aa3ad",
    "minecraft:stone": "#8a8a8a",
    "minecraft:tube_coral_block": "#2e6fd6",
    "minecraft:brain_coral_block": "#d15fa0",
    "minecraft:bubble_coral_block": "#a83fd1",
    "minecraft:fire_coral_block": "#d1372e",
    "minecraft:horn_coral_block": "#d1c62e",
    "minecraft:kelp": "#3f7a3f",
    "minecraft:sea_pickle": "#a8c93a",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a coral-reef floating island for Minecraft.",
        out_default="coral_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"coral reef floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"coral reef multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging coral spurs (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter sea pickles and kelp on top (off by default)",
    )


if __name__ == "__main__":
    main()
