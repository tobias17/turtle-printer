"""
Mesa / Badlands Floating Island Generator for Minecraft
============================================================

A badlands-mesa island variant: a red sand crust over a solid orange-
terracotta cap, then many thin bands of terracotta (like real badlands
cliffs) into the plain rock core every island theme shares underneath. The
color bands themselves are ported from vanilla Minecraft's actual
generation algorithm (decompiled BadlandsSurfaceBuilder.generateBands: a
plain terracotta backdrop peppered with single-block orange flecks, a
handful of randomly-placed yellow/brown/red runs, and a few thin white
lines each with a 50/50 chance of a light-gray fleck beside them - see
_generate_clay_bands), cycling every CLAY_BAND_HEIGHT blocks exactly like
vanilla's own 64-block-tall repeat. Picking that band from a column's
absolute depth below the crust (not its own local depth fraction) is what
makes every band line up into one consistent horizontal ring across the
whole formation regardless of how deep any one column's own taper reaches
- real cliff-band striping, not diagonal shading. The underside is
additionally quantized into a handful of bold stacked shelves (independent
of the fine color bands), so the silhouette itself reads as a stepped
canyon/plateau, and the terracotta occasionally exposes a fleck of gold
ore, a classic eroded-badlands detail. The top itself stays a clean flat
plateau (like every other theme) with nothing standing on it by default;
dead bushes and the occasional cactus only appear with --decorate-top. The
underside sheds bare terracotta shards instead of roots or icicles.

This is desert.py's dramatic sibling - see that file for the plain,
smoothly-tapered dune version of the same crust-to-core idea.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the mesa-
specific block choices, terracing, and decoration.

Usage:
    python mesa.py --diameter 40
    python mesa.py --diameter 40 --seed 7
"""

import random

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

CLAY_BAND_HEIGHT = 64  # vanilla's own clay-band array is 64 entries tall and
                        # repeats vertically forever - see _generate_clay_bands

ORANGE_CAP_RANGE = (3, 8)  # a solid orange-terracotta cap just under the
                            # crust, before the banded cycle starts - mirrors
                            # vanilla's own solid near-surface cap

GOLD_ORE_CHANCE = 0.01  # sparse exposed gold ore flecks, a real badlands trait
STONE_FADE_START = 0.82  # fraction of a column's own depth where it starts
                          # blending into the plain rock core near the bottom

NUM_TERRACES = 4  # how many BOLD shelves the silhouette steps through,
                   # regardless of size - independent of the fine color
                   # bands above, so the plateau still reads as a few big
                   # canyon-like steps rather than dozens of thin ones


def _generate_clay_bands(rng):
    """Builds one vertical cycle of the terracotta color lookup the same
    way vanilla Minecraft's real badlands surface builder does (ported from
    the decompiled BadlandsSurfaceBuilder.generateBands - see the module
    docstring). Only the *distributions* are carried over, not vanilla's
    exact bit-for-bit Random sequence, since this is seeded from the
    island's own per-column rng stream, not a Minecraft world seed.

    Returns a CLAY_BAND_HEIGHT-length list of block names: mostly plain
    terracotta, with single-block orange flecks scattered every 2-6 blocks,
    a handful of thicker yellow/brown/red runs dropped at random offsets
    (each can overlap and overwrite earlier ones, exactly like vanilla), and
    finally a few thin white accent lines with a 50/50 chance of a
    light-gray fleck immediately above and/or below each one."""
    bands = ["minecraft:terracotta"] * CLAY_BAND_HEIGHT

    y = 0
    while y < CLAY_BAND_HEIGHT:
        y += rng.randint(1, 5)
        if y < CLAY_BAND_HEIGHT:
            bands[y] = "minecraft:orange_terracotta"
        y += 1

    def scatter_runs(block, attempts_range, thickness_range):
        for _ in range(rng.randint(*attempts_range)):
            thickness = rng.randint(*thickness_range)
            offset = rng.randint(0, CLAY_BAND_HEIGHT - 1)
            for dy in range(thickness):
                if offset + dy < CLAY_BAND_HEIGHT:
                    bands[offset + dy] = block

    scatter_runs("minecraft:yellow_terracotta", (2, 5), (1, 3))
    scatter_runs("minecraft:brown_terracotta", (2, 5), (2, 4))
    scatter_runs("minecraft:red_terracotta", (2, 5), (1, 3))

    offset = 0
    for _ in range(rng.randint(3, 5)):
        offset += rng.randint(4, 19)
        if offset >= CLAY_BAND_HEIGHT:
            break
        bands[offset] = "minecraft:white_terracotta"
        if offset > 1 and rng.random() < 0.5:
            bands[offset - 1] = "minecraft:light_gray_terracotta"
        if offset < CLAY_BAND_HEIGHT - 1 and rng.random() < 0.5:
            bands[offset + 1] = "minecraft:light_gray_terracotta"

    return bands


def _terrace_columns(blocks, col_bottom, columns, band_size):
    """Post-processes an already-carved island (from the ordinary, unmodified
    common.carve_columns) so each column's underside depth snaps down to the
    nearest multiple of `band_size`, instead of the smooth continuous taper
    every other theme uses. This only ever *removes* already-carved blocks
    (never invents new ones) and keeps col_bottom/columns in sync, so drips
    and rim decoration - which read those to find each column's true bottom -
    still attach cleanly to the new, shallower surface.

    Deliberately local to mesa.py rather than a carve_columns option: this
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


def pick_gradient(clay_bands, depth_blocks, jitter=0.0):
    """Picks a stripe block for `depth_blocks` (0 = the layer right under
    the orange cap, growing downward), cycling through this island's own
    clay_bands (see _generate_clay_bands) every CLAY_BAND_HEIGHT blocks -
    exactly like vanilla's own bands repeat every 64 Y-levels. Using
    absolute depth-in-blocks - not a column's own depth *fraction* - is
    what makes every band line up into one consistent horizontal ring
    across the whole island regardless of how deep any one column's own
    taper happens to reach, matching how real badlands strata read from
    outside. `jitter` (smooth per-column noise, in blocks) nudges the
    boundary so it's wavy/eroded instead of a razor-straight ring."""
    idx = int(round(depth_blocks + jitter)) % len(clay_bands)
    return clay_bands[idx]


def pick_sand_crust(rng):
    """Top-crust block: solid red sand, no fleck - the crust is a flat platform."""
    return "minecraft:red_sand"


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one mesa
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of red-sand-crust layers, before
                       the terracotta gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       terracotta shard.
    decorate_top     - if True, scatters dead bushes and cacti on top.
    decorate_underside - hanging terracotta shards on the underside. On by
                       default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    # one-time setup, deliberately drawn from its own throwaway rng rather
    # than carve_columns' shared per-column one, so it's fixed for the whole
    # island (like vanilla's own bands, generated once per world) instead of
    # being redrawn - or perturbing carve_columns' own sequence - per column.
    setup_rng = random.Random(seed + 21)
    clay_bands = _generate_clay_bands(setup_rng)
    orange_cap = setup_rng.randint(*ORANGE_CAP_RANGE)

    # a handful of big shelves regardless of island size, so the terracing
    # always reads as a few bold mesa steps rather than many thin bands that
    # blur back into a smooth cone at larger diameters.
    band_size = max(2, max_depth // NUM_TERRACES)

    def top_block(rng, x, z, xi, zi):
        return pick_sand_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_sand_crust(rng)
        depth_blocks = y_offset - thickness
        if depth_blocks < orange_cap:
            return "minecraft:orange_terracotta"
        depth_blocks -= orange_cap
        jitter = gradient_noise[xi, zi] * 0.9 + speckle_noise[xi, zi] * 0.5
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        if t_grad > STONE_FADE_START:
            # blend into the plain rock core near the very bottom of this
            # column's own taper - a probability ramp (not a hard cutoff)
            # so the transition is a ragged edge, not a razor ring.
            fade = (t_grad - STONE_FADE_START) / (1 - STONE_FADE_START)
            if rng.random() < fade:
                return "minecraft:stone"
        if rng.random() < GOLD_ORE_CHANCE:
            return "minecraft:gold_ore"
        return pick_gradient(clay_bands, depth_blocks, jitter=jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # step the smooth taper this just produced down into a few bold mesa
    # shelves - see _terrace_columns above.
    _terrace_columns(blocks, col_bottom, columns, band_size)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:terracotta" if is_tip else "minecraft:orange_terracotta"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # bare eroded terracotta shards near the outer rim (no vines in a
        # badlands - just weathered rock hanging on)
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:terracotta",
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
    """One big mesa island plus satellites and floating terracotta debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:terracotta")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:red_sand": "#a8461c",
    "minecraft:red_terracotta": "#8f3728",
    "minecraft:orange_terracotta": "#b2551f",
    "minecraft:terracotta": "#9c5148",
    "minecraft:yellow_terracotta": "#d4bb3c",
    "minecraft:brown_terracotta": "#4a3222",
    "minecraft:white_terracotta": "#d9cfc0",
    "minecraft:light_gray_terracotta": "#8d8579",
    "minecraft:stone": "#8a8a8a",
    "minecraft:gold_ore": "#d4af37",
    "minecraft:dead_bush": "#8a6a3a",
    "minecraft:cactus": "#4a7a3a",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a mesa/badlands floating island for Minecraft.",
        out_default="mesa_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"mesa floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"mesa multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging terracotta shards (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter dead bushes and cacti on top (off by default)",
    )


if __name__ == "__main__":
    main()
