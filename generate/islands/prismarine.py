"""
Ocean Monument Floating Island Generator for Minecraft
=======================================================

An ocean-monument island variant: prismarine instead of natural rock or
earth. Structurally it's deliberately ENGINEERED-looking rather than
organic: most of the underside is a shallow, uniform shelf, but four
evenly-spaced (rotationally symmetric, not noise-clumped) towers of dark
prismarine punch down through it at fixed 90-degree intervals, studded
with glowing sea lanterns - guard-tower pillars holding up a sunken
temple, not a randomly eroded natural shape. Every other theme so far
places its "exempted" deep bits via noise/clumping/randomness; this one
places them via explicit rotational symmetry, which is what makes it read
as built rather than grown.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the monument-
specific block choices and decoration.

Usage:
    python prismarine.py --diameter 40
    python prismarine.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Prismarine crust down to dark prismarine at the core - kept to 2 solid
# bands (no fleck/dither) so the shelf reads as clean masonry.
GRADIENT = [
    "minecraft:prismarine_bricks",
    "minecraft:dark_prismarine",
]

N_TOWERS = 4  # evenly-spaced guard towers, not noise-driven
TOWER_RADIUS_FRAC = 0.5  # r/localR band the towers sit in
TOWER_RADIUS_TOL = 0.12  # radial tolerance around TOWER_RADIUS_FRAC
TOWER_HALF_WIDTH = 0.16  # radians of angular tolerance per tower - narrow, so
                          # clear gaps of bare shelf separate the four towers
TOWER_EXTRA_DEPTH_FRAC = 0.6  # towers punch this much further past their own
                               # natural bottom, so they read as protruding
                               # pillars regardless of where the taper ends
LANTERN_SPACING = 7  # blocks between sea-lantern accents up a tower


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    prismarine crust, 1 = deepest rock). `jitter` (driven only by smooth
    per-column noise) nudges the whole column toward a neighboring shade so
    the band edge is wavy instead of a razor-straight ring, without
    per-voxel dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_monument_crust(rng):
    """Top-crust block: solid prismarine bricks, no fleck - a flat platform."""
    return "minecraft:prismarine_bricks"


def _temple_towers(blocks, col_bottom, columns, rng, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into a shallow shelf punctuated by N_TOWERS dark-prismarine
    towers placed at exact 90-degree (for N_TOWERS=4) intervals around a
    fixed radius band, with a single random phase offset shared by all of
    them so the whole set rotates together per seed but stays perfectly
    symmetric. Columns inside a tower wedge keep their full natural depth
    (recolored to dark prismarine, with sea-lantern accents at regular
    intervals) instead of being flattened like every other column - the
    same "flatten almost everything, exempt a few" trick crystal.py's geode
    floor and ruins.py's pillars use, but the exempted set is chosen by
    exact angle/radius symmetry instead of noise-clumping or randomness,
    which is what reads as "built" instead of "grown" or "eroded."

    Like desert.py's mesa terracing, this only ever *removes* already-
    carved blocks (tower columns are only recolored, never extended) and
    keeps col_bottom/columns in sync (drips/rim decoration read those for
    each column's true bottom), and is deliberately local to prismarine.py
    rather than a carve_columns option, so no other theme is affected.
    """
    shelf_depth = max(4, int(max_depth * 0.3))
    tower_extra = max(6, int(max_depth * TOWER_EXTRA_DEPTH_FRAC))
    phase = rng.uniform(0, 2 * math.pi / N_TOWERS)
    target_angles = [phase + i * (2 * math.pi / N_TOWERS) for i in range(N_TOWERS)]

    def recolor(y):
        if (topY - y) % LANTERN_SPACING == 0:
            blocks[(x, y, z)] = "minecraft:sea_lantern"
        else:
            blocks[(x, y, z)] = "minecraft:dark_prismarine"

    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        frac = r / localR if localR else 1.0
        theta = math.atan2(z, x)
        is_tower = False
        if abs(frac - TOWER_RADIUS_FRAC) < TOWER_RADIUS_TOL:
            for ta in target_angles:
                d = (theta - ta + math.pi) % (2 * math.pi) - math.pi
                if abs(d) < TOWER_HALF_WIDTH:
                    is_tower = True
                    break

        if is_tower:
            bottomY, _, _, _ = col_bottom[(x, z)]
            new_bottomY = bottomY - tower_extra
            for y in range(bottomY, topY):
                recolor(y)
            for y in range(new_bottomY, bottomY):
                recolor(y)
            col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
            new_columns.append((x, z, topY, topY - new_bottomY, r, localR))
            continue

        if depth <= shelf_depth:
            new_columns.append((x, z, topY, depth, r, localR))
            continue

        bottomY, _, _, _ = col_bottom[(x, z)]
        new_bottomY = topY - shelf_depth
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)
        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, shelf_depth, r, localR))
    columns[:] = new_columns


def generate_island(seed=0, diameter=40, top_thickness_range=(3, 5), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one ocean-monument
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of prismarine-crust layers,
                       before the dark-prismarine/rock gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       chunk of masonry rubble.
    decorate_top     - if True, scatters sea pickles and kelp on top.
    decorate_underside - tower shaping, hanging rubble and kelp fringe on
                       the underside. On by default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_monument_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_monument_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # flatten to a shelf, punch four symmetric guard towers through it - see
    # _temple_towers above.
    _temple_towers(blocks, col_bottom, columns, rng, max_depth)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:sea_lantern" if is_tip else "minecraft:dark_prismarine"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # kelp fringe draped from the rim
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:kelp",
            r_frac_threshold=0.55, chance=0.15, length_range=(2, 5),
        )

    if decorate_top:
        # sparse sea pickle clusters and kelp stalks on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.1:
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
    """One big ocean-monument island plus satellites and floating prismarine
    debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:prismarine")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:prismarine_bricks": "#6fc2ad",
    "minecraft:dark_prismarine": "#2f5a4a",
    "minecraft:sea_lantern": "#d6f0e0",
    "minecraft:kelp": "#3f7a3f",
    "minecraft:sea_pickle": "#a8c93a",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate an ocean-monument floating island for Minecraft.",
        out_default="prismarine_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"ocean monument floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"ocean monument multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging masonry rubble chunks (default: auto-scales with "
                         "the island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter sea pickles and kelp on top (off by default)",
    )


if __name__ == "__main__":
    main()
