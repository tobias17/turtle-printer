"""
Fungal Floating Island Generator for Minecraft
===================================================

A mushroom-cap island variant: red concrete speckled with scattered white
spots (mimicking the actual red mushroom block's texture) all the way
through, top to underside, shaped into a flat mushroom cap with a single
thick white stem plunging down from the center - no gradient, no gill
texture, no hanging drips or rim fringe. Giant mushrooms can grow on top
instead of trees.

Shares its silhouette/taper machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the fungal-
specific block choices and the cap/stem shape.

Usage:
    python mushroom.py --diameter 40
    python mushroom.py --diameter 40 --seed 7
"""

import random

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

STEM_BLOCK = "minecraft:mushroom_stem"

# Mostly red concrete with scattered white-concrete spots, mimicking the
# actual red mushroom block's own dot texture. The cap is carved fully
# solid CAP_BLOCK first (see generate_island/_cap_and_stem); spots are then
# scattered across its real outer surface as a separate pass
# (_scatter_cap_spots below) - a dart-throwing / blue-noise placement over
# the cap's actual exposed skin (top, underside, AND the rounded rim wall
# between them), not a flat (x, z) plane - so spots read as small dots
# wherever the surface is actually visible, never as a streak drilled
# straight down through a column's full depth regardless of which face
# that depth is facing. A deliberate, explicit exception to this project's
# usual "one solid top color" rule for these islands, since the whole
# point here is to read as that specific block's own pattern rather than a
# flat color.
CAP_BLOCK = "minecraft:red_concrete"
CAP_SPOT_BLOCK = "minecraft:white_concrete"
CAP_SPOT_MIN_DIST = 5.0  # minimum 3D spacing (along the surface) kept between two spots


def _cap_surface_voxels(blocks, columns, col_bottom):
    """Returns every cap voxel (x, y, z) that is exposed to air on at least
    one of its 6 faces - the cap's actual outer skin. This is the topology
    fix over picking spot columns by (x, z) alone: a column near the rim is
    mostly SIDE wall (its "depth" faces sideways, not down), so a naive
    per-column pick painted a vertical white streak down that side wall.
    Working voxel-by-voxel against real exposure means a rim spot paints
    only the handful of actually-visible side-wall voxels around it, same
    as a top or underside spot only paints the visible cap surface there -
    the shape decides where the skin is, not a flat XZ grid.
    """
    surface = []
    for (x, z, topY, depth, r, localR) in columns:
        frac = r / localR if localR else 1.0
        if frac < 0.18:
            continue  # stem column - no spots
        bottomY, _, _, _ = col_bottom[(x, z)]
        for y in range(bottomY, topY + 1):
            if blocks.get((x, y, z)) != CAP_BLOCK:
                continue
            exposed = (
                blocks.get((x + 1, y, z)) is None or blocks.get((x - 1, y, z)) is None or
                blocks.get((x, y, z + 1)) is None or blocks.get((x, y, z - 1)) is None or
                blocks.get((x, y + 1, z)) is None or blocks.get((x, y - 1, z)) is None
            )
            if exposed:
                surface.append((x, y, z))
    return surface


def _scatter_cap_spots(blocks, columns, col_bottom, rng):
    """Post-process pass over the already-solid cap (see generate_island:
    the whole shape is carved plain CAP_BLOCK first, reshaped into the flat
    cap + stem by _cap_and_stem, THEN this runs): visits the cap's real
    exposed surface (see _cap_surface_voxels) in random order and paints a
    single white voxel wherever a surface voxel ends up at least
    CAP_SPOT_MIN_DIST from every spot already placed. Single voxels, not a
    multi-block blob - a 7-voxel plus-shaped blob at every spot read as far
    too much white overall, closer to a checkerboard than scattered dots.

    This is simple dart-throwing (rejection-sampled blue noise): visiting
    surface voxels in shuffled order and only ever rejecting a candidate
    for being too close to an existing spot means spots keep getting
    proposed in whatever open red surface is left until one lands, so they
    end up well spread across top, underside, and rim alike, while never
    clustering closer than CAP_SPOT_MIN_DIST apart.
    """
    surface = _cap_surface_voxels(blocks, columns, col_bottom)
    order = list(range(len(surface)))
    rng.shuffle(order)

    spot_centers = []
    min_dist_sq = CAP_SPOT_MIN_DIST ** 2
    for i in order:
        x, y, z = surface[i]
        if any((x - sx) ** 2 + (y - sy) ** 2 + (z - sz) ** 2 < min_dist_sq
               for sx, sy, sz in spot_centers):
            continue
        spot_centers.append((x, y, z))
        blocks[(x, y, z)] = CAP_SPOT_BLOCK


def _cap_and_stem(blocks, col_bottom, columns, rng, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into an actual mushroom silhouette - a wide, shallow cap
    underside (roughly constant depth regardless of radius, like the flat
    gill surface under a real mushroom cap) with a single thick stem plunging
    down from the center - instead of the smooth cone every theme starts
    from. The stem columns are also recolored solid `STEM_BLOCK` (the real
    white mushroom-stem block) so the stem reads as an actual stem instead
    of just more purple cap.

    Like desert.py's mesa terracing, this only ever *removes* already-carved
    blocks and keeps col_bottom/columns in sync, and is deliberately local
    to mushroom.py rather than a carve_columns option, so no other theme is
    affected.
    """
    cap_depth = max(4, int(max_depth * 0.35))
    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        frac = r / localR if localR else 1.0
        if frac >= 0.18 and depth > cap_depth:
            bottomY, _, _, _ = col_bottom[(x, z)]
            new_bottomY = topY - cap_depth
            for y in range(bottomY, new_bottomY):
                blocks.pop((x, y, z), None)
            col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
            new_columns.append((x, z, topY, cap_depth, r, localR))
        else:
            if frac < 0.18:
                bottomY, _, _, _ = col_bottom[(x, z)]
                for y in range(bottomY, topY):
                    blocks[(x, y, z)] = STEM_BLOCK
            new_columns.append((x, z, topY, depth, r, localR))
    columns[:] = new_columns


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.04, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one fungal
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - unused by this theme; the whole cap is solid
                       red mushroom block regardless of depth (kept only
                       for CLI/run_cli signature compatibility).
    num_drips / drip_density - unused by this theme; the underside is just
                       the flat solid mushroom-block cap and stem, no
                       drips (kept only for CLI/run_cli signature
                       compatibility).
    decorate_top     - if True, scatters small mushrooms and grows a couple
                       of giant mushrooms on top.
    decorate_underside - unused by this theme; the cap has no underside
                       decoration (kept only for CLI/run_cli signature
                       compatibility).
    """
    size, half, radius = common.grid_dims(diameter)

    def top_block(rng, x, z, xi, zi):
        return CAP_BLOCK

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        return CAP_BLOCK

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
        # a cap-like taper: stays close to full width just under the rim
        # (like a mushroom cap's flesh) then narrows quickly further down -
        # both existing carve_columns parameters, no shared code touched.
        taper_strength=0.9, taper_exponent=1.6,
    )
    # reshape the smooth cone into a flat cap + central stem (recolored solid
    # white) - see _cap_and_stem above. Everything carved is still plain
    # solid CAP_BLOCK at this point, so this is the only underside shaping
    # this theme does.
    _cap_and_stem(blocks, col_bottom, columns, rng, max_depth)
    # now scatter white spots across the finished, solid-red shape - see
    # _scatter_cap_spots above. A separate rng from carve_columns' own (same
    # convention as the other themes' throwaway secondary RNGs) so spot
    # placement doesn't shift when unrelated carve-side randomness changes.
    _scatter_cap_spots(blocks, columns, col_bottom, random.Random(seed + 31))

    if decorate_top:
        # sparse small mushrooms on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.12:
                block = rng.choice(["minecraft:red_mushroom", "minecraft:brown_mushroom"])
                blocks.setdefault((x, topY + 1, z), block)

        # a couple of giant mushrooms
        mushroom_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(mushroom_spots)
        for (x, z, topY, depth, r, localR) in mushroom_spots[: rng.randint(0, 2)]:
            stem_h = rng.randint(4, 6)
            for dy in range(stem_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:mushroom_stem"
            cap_y = topY + 1 + stem_h
            cap_block = rng.choice(["minecraft:red_mushroom_block", "minecraft:brown_mushroom_block"])
            for dx in range(-2, 3):
                for dz in range(-2, 3):
                    for dy in range(0, 3):
                        if dx * dx + dz * dz + dy * dy <= 5 and rng.random() < 0.85:
                            blocks.setdefault((x + dx, cap_y + dy, z + dz), cap_block)

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big fungal island plus satellites and floating boggy debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:red_mushroom_block")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:mushroom_stem": "#e8e0d0",
    "minecraft:red_mushroom": "#c03030",
    "minecraft:brown_mushroom": "#8a6a48",
    "minecraft:red_mushroom_block": "#a83232",
    "minecraft:brown_mushroom_block": "#9c7a52",
    "minecraft:red_concrete": "#8f2213",
    "minecraft:white_concrete": "#e2e5e6",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a fungal floating island for Minecraft.",
        out_default="mushroom_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"fungal floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"fungal multi-island demo scene (seed={seed})",
        num_drips_help="unused by this theme - the underside is just the flat solid mushroom-block "
                        "cap and stem, kept only for CLI compatibility",
        decorate_top_help="scatter mushrooms and grow giant mushrooms on top (off by default)",
    )


if __name__ == "__main__":
    main()
