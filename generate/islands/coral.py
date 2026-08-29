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

# Pale reef-rock crust down to the plain rock core - solid, no dither, so
# the shelf reads as plain eroded rock and the coral (below) is what carries
# all the color.
GRADIENT = [
    "minecraft:sand",
    "minecraft:sandstone",
]

# Two accent colors per island (chosen once in generate_island, not per
# voxel) so each colony reads as one solid coral color, not confetti.
CORAL_COLOR_CHOICES = [
    "minecraft:tube_coral_block",
    "minecraft:brain_coral_block",
    "minecraft:fire_coral_block",
    "minecraft:horn_coral_block",
]

BRANCH_THRESHOLD = 0.45  # clumping-noise cutoff for where coral colonies grow
STUB_FRAC = 0.22  # how shallow the eroded (non-branch) columns become


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the sand
    crust, 1 = deepest rock). `jitter` (driven only by smooth per-column
    noise) nudges the whole column toward a neighboring shade so the band
    edge is wavy instead of a razor-straight ring, without per-voxel
    dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_reef_crust(rng):
    """Top-crust block: solid sand, no fleck - the crust is a flat platform."""
    return "minecraft:sand"


def _reef_branches(blocks, col_bottom, columns, size, half, seed, rng, max_depth, coral_colors):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside so it reads as a reef shelf with sparse coral colonies growing
    off it, instead of a solid tapering mass: a clumped noise field marks a
    patchwork of columns as "coral branches", while every other column - the
    eroded reef rock - is hard-capped to a shallow stub. The clumping
    (rather than an independent per-column chance) is what makes the coral
    read as colonies growing in patches, not salt-and-pepper speckle. Each
    branch column is filled with ONE solid color from `coral_colors` (chosen
    from the same coherent noise field, not re-rolled per voxel), and
    `coral_colors` itself is only 2 colors picked once for the whole island -
    so a colony reads as a single-color coral head, not a rainbow of static.

    Branch columns do NOT keep their full natural taper depth - that depth
    scales with max_depth (and so with diameter) without bound, which at
    large diameters turned the deepest colonies into unnaturally tall,
    dead-straight towers, and at small diameters let one coarse noise cell
    swallow almost the whole underside. Instead each branch column's extra
    depth (how much further it reaches past the stub) is capped to a
    per-column random amount scaled off max_depth - the same convention
    common.generate_drips uses for drip length - so a colony's reach stays
    proportionate at every diameter, and the per-column randomness gives the
    colony's underside a ragged, coral-like profile instead of a flat table.

    Like desert.py's mesa terracing, this only ever *removes* already-carved
    blocks (branch columns are recolored/trimmed, never extended) and keeps
    col_bottom/columns in sync (drips/rim decoration read those for each
    column's true bottom), and is deliberately local to coral.py rather than
    a carve_columns option, so no other theme is affected.
    """
    clump_grid = max(6, size // 9)
    clump_noise = common.value_noise_2d(size, clump_grid, seed + 51)
    stub_depth = max(3, int(max_depth * STUB_FRAC))
    extra_floor = max(3, round(max_depth * 0.18))
    extra_ceiling = max(extra_floor + 3, round(max_depth * 0.45))
    color_split = (BRANCH_THRESHOLD + 1.0) / 2
    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        noise_val = clump_noise[x + half, z + half]
        is_branch = noise_val > BRANCH_THRESHOLD
        if is_branch:
            bottomY, _, _, _ = col_bottom[(x, z)]
            # Extra depth tracks the noise value itself (deepest at the
            # patch's core, shallowing toward its edge where noise_val
            # nears BRANCH_THRESHOLD) rather than an independent per-column
            # roll, so a colony rises as one smooth mound instead of ragged
            # single-column needles poking out of a lower neighborhood.
            frac = min(1.0, max(0.0, (noise_val - BRANCH_THRESHOLD) / (1.0 - BRANCH_THRESHOLD)))
            extra = (extra_floor + frac * (extra_ceiling - extra_floor)) * rng.uniform(0.85, 1.15)
            colony_depth = min(depth, stub_depth + round(extra))
            new_bottomY = topY - colony_depth
            color = coral_colors[0] if noise_val > color_split else coral_colors[1]
            for y in range(new_bottomY, topY):
                blocks[(x, y, z)] = color
            for y in range(bottomY, new_bottomY):
                blocks.pop((x, y, z), None)
            col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
            new_columns.append((x, z, topY, colony_depth, r, localR))
            continue
        if depth <= stub_depth:
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
        return pick_gradient(rng, t_grad, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # erode most of the underside to a shelf, leaving sparse coral colonies
    # branching down further - see _reef_branches above. Two accent colors
    # for the whole island, picked once (not per voxel/column).
    coral_colors = rng.sample(CORAL_COLOR_CHOICES, 2)
    _reef_branches(blocks, col_bottom, columns, size, half, seed, rng, max_depth, coral_colors)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return coral_colors[0] if is_tip else "minecraft:sandstone"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # kelp fringe draped from the rim (replaces the other themes'
        # vines/icicles/roots)
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:kelp",
            r_frac_threshold=0.55, chance=0.12, length_range=(2, 4),
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
    "minecraft:tube_coral_block": "#2e6fd6",
    "minecraft:brain_coral_block": "#d15fa0",
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
