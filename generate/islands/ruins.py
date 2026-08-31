"""
Overgrown Ruins Floating Island Generator for Minecraft
=========================================================

An ancient-temple island variant: cracked, moss-swallowed masonry instead
of natural rock or earth. A moss-and-stone-brick crust on top (broken
temple flooring reclaimed by jungle), grading down through stone brick
into mossy cobblestone at the core. Rather than a smooth tapering cone, the underside
collapses in blocky masonry tiers, with a couple of thick square "broken
pillar" stubs still hanging on - remnants of the temple's support columns -
all lightly mossed over.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the ruins-
specific block choices and decoration.

Usage:
    python ruins.py --diameter 40
    python ruins.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Mossy masonry crust down through stone brick into mossy cobblestone at the
# core - kept to 2 solid bands (no fleck/dither) so the terrace steps below
# read as clean masonry tiers.
GRADIENT = [
    "minecraft:mossy_stone_bricks",
    "minecraft:mossy_cobblestone",
]

NUM_TIERS = 3  # blocky masonry terraces, same quantize-the-natural-taper trick
                # as desert.py's mesa shelves - fewer and bolder than desert's
                # 5, so each step is a big, unmistakable drop instead of a
                # fine ledge, reading as a stepped ziggurat rather than a mesa
PILLAR_COUNT_RANGE = (2, 4)
PILLAR_RADIUS = 1  # half-width beyond the center block, so pillars are 3x3


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the mossy
    crust, 1 = deepest rock). `jitter` (driven only by smooth per-column
    noise) nudges the whole column toward a neighboring shade so the band
    edge is wavy instead of a razor-straight ring, without per-voxel
    dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_ruins_crust(rng):
    """Top-crust block: solid moss, no fleck - the crust is a flat platform."""
    return "minecraft:moss_block"


def _terrace_and_pillars(blocks, col_bottom, columns, rng, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into blocky collapsed-masonry tiers (same technique as
    desert.py's mesa terracing - snapping each column's depth down to the
    nearest shelf, floor-dividing its own natural taper depth by band_size)
    with a handful of thick 3x3 columns near the center exempted entirely,
    so they keep their full natural depth and read as the last standing
    support pillars of a collapsed temple - the same "flatten almost
    everything, exempt a few" trick crystal.py's geode floor uses, just
    with thick square pillars instead of thin spikes. NUM_TIERS is kept
    deliberately low (3, vs. desert's 5) so band_size - and therefore each
    step's height - is large: a handful of big, unmistakable drops that
    read as a stepped, upside-down ziggurat, not desert's finer mesa shelves.

    Like desert.py's mesa terracing, this only ever *removes* already-
    carved blocks (pillar columns are only recolored, never extended) and
    keeps col_bottom/columns in sync (drips/rim decoration read those for
    each column's true bottom), and is deliberately local to ruins.py
    rather than a carve_columns option, so no other theme is affected.
    """
    band_size = max(2, max_depth // NUM_TIERS)

    candidates = [c for c in columns if (c[4] / c[5] if c[5] else 1.0) < 0.3]
    rng.shuffle(candidates)
    n_pillars = min(len(candidates), rng.randint(*PILLAR_COUNT_RANGE))
    pillar_xy = set()
    for (cx, cz, *_rest) in candidates[:n_pillars]:
        for dx in range(-PILLAR_RADIUS, PILLAR_RADIUS + 1):
            for dz in range(-PILLAR_RADIUS, PILLAR_RADIUS + 1):
                pillar_xy.add((cx + dx, cz + dz))

    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        bottomY, _, _, _ = col_bottom[(x, z)]
        if (x, z) in pillar_xy:
            for y in range(bottomY, topY):
                blocks[(x, y, z)] = ("minecraft:mossy_stone_bricks" if rng.random() < 0.5
                                      else "minecraft:mossy_cobblestone")
            new_columns.append((x, z, topY, depth, r, localR))
            continue
        new_depth = band_size * (depth // band_size)
        if new_depth == 0:
            new_depth = depth  # already thinner than one shelf - leave it
        new_bottomY = topY - new_depth
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)
        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, new_depth, r, localR))
    columns[:] = new_columns
    return band_size


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one overgrown-
    ruins island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of moss-crust layers, before
                       the stone-brick gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       chunk of rubble.
    decorate_top     - if True, scatters jungle saplings and broken-pillar
                       stumps on top.
    decorate_underside - terraced masonry, broken pillars, hanging rubble
                       and mossy accents on the underside. On by default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1
    band_size_guess = max(2, max_depth // NUM_TIERS)  # matches _terrace_and_pillars

    def top_block(rng, x, z, xi, zi):
        return pick_ruins_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_ruins_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        depth_bands = max(1, (thickness - 1 + max_depth) // band_size_guess)
        band_t = math.floor(min(max(t_grad, 0.0), 0.999999) * depth_bands) / depth_bands
        return pick_gradient(rng, band_t, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # step the taper into collapsed masonry tiers, leaving a few thick
    # broken-pillar stubs at full depth - see _terrace_and_pillars above.
    _terrace_and_pillars(blocks, col_bottom, columns, rng, max_depth)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:mossy_cobblestone" if is_tip else "minecraft:mossy_stone_bricks"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # light mossy-brick cover near the rim only - an accent, not a
        # curtain, so the stepped masonry tiers stay the visual focus. A
        # plain solid block, not vine: nothing in this project's turtle-
        # build pipeline resolves an attachment face the way vine needs
        # (see common.decorate_rim_underside's own docstring)
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:mossy_stone_bricks",
            r_frac_threshold=0.5, chance=0.12, length_range=(2, 4),
        )

        # the occasional mossy-brick outcrop just under the top edge, over
        # the cliff face
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR > 0.75 and rng.random() < 0.08:
                blocks.setdefault((x, topY - 1, z), "minecraft:mossy_stone_bricks")

    if decorate_top:
        # sparse jungle saplings and moss carpet on the top surface - fern/
        # sapling weighted over moss_carpet so moss reads as an accent
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.1:
                block = rng.choice(
                    ["minecraft:fern", "minecraft:fern",
                     "minecraft:jungle_sapling", "minecraft:moss_carpet"]
                )
                blocks.setdefault((x, topY + 1, z), block)

        # a couple of broken-pillar stumps poking up from the floor
        stump_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(stump_spots)
        for (x, z, topY, depth, r, localR) in stump_spots[: rng.randint(0, 3)]:
            stump_h = rng.randint(1, 3)
            for dy in range(stump_h):
                blocks[(x, topY + 1 + dy, z)] = ("minecraft:mossy_stone_bricks" if rng.random() < 0.6
                                                  else "minecraft:mossy_cobblestone")

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big ruins island plus satellites and floating rubble debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:mossy_cobblestone")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:moss_block": "#5a7a2f",
    "minecraft:mossy_stone_bricks": "#6a7a5a",
    "minecraft:mossy_cobblestone": "#748266",
    "minecraft:moss_carpet": "#4f7a2a",
    "minecraft:fern": "#4f8f3f",
    "minecraft:jungle_sapling": "#5f9f3f",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate an overgrown-ruins floating island for Minecraft.",
        out_default="ruins_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"overgrown ruins floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"overgrown ruins multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging rubble chunks (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter jungle saplings and pillar stumps on top (off by default)",
    )


if __name__ == "__main__":
    main()
