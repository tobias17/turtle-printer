"""
Honeycomb Hive Floating Island Generator for Minecraft
=========================================================

A giant hardened-honeycomb island variant: golden honeycomb crust over a
waxy oak-frame core down to plain rock at the very center, dotted with wild
meadow flowers and beehives on top. Structurally the underside is not a
cone, dome, or platter like the other themes - it's tessellated into a
honeycomb of hexagonal cells (see `_honeycomb_cells`), each hanging down to
its own depth, frame-recolored along the cell walls, and capped with a
drop of honey at the tip - so the whole underside reads as a slab of comb
with cells of different lengths, not a single smooth shape.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the hive-
specific block choices and decoration.

Usage:
    python hive.py --diameter 40
    python hive.py --diameter 40 --seed 7
"""

import math
import random

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Honeycomb crust down through a waxy oak-plank frame to plain rock at the
# core - kept to 3 solid bands (no fleck/dither). Honey itself is reserved
# exclusively for the hex-cell tips and drips (see _honeycomb_cells), never
# part of the bulk gradient, so it reads as something dripping OUT of the
# comb rather than more bulk texture.
GRADIENT = [
    "minecraft:honeycomb_block",
    "minecraft:oak_planks",
    "minecraft:stone",
]

HEX_SIZE = 5.0  # world-space radius of one honeycomb cell, in blocks
SQRT3 = math.sqrt(3.0)
WALL_APOTHEM_FRAC = 0.8  # fraction of the hex apothem beyond which a column
                          # is treated as cell-wall frame instead of interior
SHELF_DEPTH_FRAC = 0.22  # base depth every cell starts from before its own
                          # per-cell extension
CELL_DEPTH_MIN_FRAC = 0.4
CELL_DEPTH_MAX_FRAC = 1.0
WALL_BAND_FRAC = 0.4  # fraction of a cell's own final depth, right at the
                       # cut surface, that gets recolored as visible frame


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    honeycomb crust, 1 = deepest rock). `jitter` (driven only by smooth
    per-column noise) nudges the whole column toward a neighboring shade so
    the band edge is wavy instead of a razor-straight ring, without
    per-voxel dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_comb_crust(rng):
    """Top-crust block: solid honeycomb, no fleck - the crust is a flat platform."""
    return "minecraft:honeycomb_block"


def _hex_cell_and_offset(x, z, size):
    """Maps a world (x, z) to its enclosing pointy-top hexagon, using the
    standard axial round (redblobgames' hex-grid algorithm). Returns
    ((cell_q, cell_r), offset) where offset is the Euclidean distance from
    (x, z) to that hex cell's own center - used as a cheap in/near-wall test
    (a circle inscribed near the hex's apothem approximates its edges close
    enough to read as cell walls at voxel resolution)."""
    q = (SQRT3 / 3 * x - 1.0 / 3 * z) / size
    r = (2.0 / 3 * z) / size
    cx, cy, cz = q, -q - r, r
    rx, ry, rz = round(cx), round(cy), round(cz)
    dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    cell = (int(rx), int(rz))
    cx_world = size * (SQRT3 * cell[0] + SQRT3 / 2 * cell[1])
    cz_world = size * (1.5 * cell[1])
    offset = math.hypot(x - cx_world, z - cz_world)
    return cell, offset


def _honeycomb_cells(blocks, col_bottom, columns, seed, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into a honeycomb: every column is assigned to one pointy-top
    hex cell (see _hex_cell_and_offset), and every column in the same cell
    is truncated down to that cell's own depth - a single value drawn once
    per cell from a hash of (seed, cell), not from any per-column noise -
    so each hex reads as one flat-bottomed cell of a distinct length,
    exactly like desert.py's mesa terraces quantize depth into shared bands,
    just partitioned spatially by hex membership instead of by depth.
    Columns near a cell's own edge (by the offset test) are recolored into
    the frame material near their cut surface, and the interior columns get
    a drop of honey at the tip, so the underside reads as a slab of dripping
    comb rather than a single smooth taper.

    Like desert.py's mesa terracing, this only ever *removes* already-
    carved blocks and keeps col_bottom/columns in sync (drips/rim decoration
    read those for each column's true bottom), and is deliberately local to
    hive.py rather than a carve_columns option, so no other theme is
    affected.
    """
    shelf_depth = max(3, int(max_depth * SHELF_DEPTH_FRAC))
    apothem = HEX_SIZE * SQRT3 / 2
    wall_threshold = apothem * WALL_APOTHEM_FRAC
    depth_cache = {}

    def cell_depth(cell):
        if cell not in depth_cache:
            frac = random.Random(f"{seed}:{cell[0]}:{cell[1]}").uniform(
                CELL_DEPTH_MIN_FRAC, CELL_DEPTH_MAX_FRAC)
            depth_cache[cell] = max(shelf_depth, int(max_depth * frac))
        return depth_cache[cell]

    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        cell, offset = _hex_cell_and_offset(x, z, HEX_SIZE)
        target = min(depth, cell_depth(cell))
        bottomY, _, _, _ = col_bottom[(x, z)]
        new_bottomY = topY - target
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)

        if offset >= wall_threshold:
            wall_band = max(1, int(target * WALL_BAND_FRAC))
            for y in range(new_bottomY, min(topY, new_bottomY + wall_band)):
                if (x, y, z) in blocks:
                    blocks[(x, y, z)] = "minecraft:oak_planks"
        else:
            blocks[(x, new_bottomY, z)] = "minecraft:honey_block"

        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, target, r, localR))
    columns[:] = new_columns


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one honeycomb-hive
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of honeycomb-crust layers,
                       before the oak-frame/rock gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       gob of honey, distinct from the hex-cell tips.
    decorate_top     - if True, scatters meadow flowers, beehives and small
                       birch trees on top.
    decorate_underside - hex-cell shaping, honey drips and fringe on the
                       underside. On by default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_comb_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_comb_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # tessellate the underside into hanging hex cells of varying depth,
    # framed at their walls, dripping honey at their tips - see
    # _honeycomb_cells above.
    _honeycomb_cells(blocks, col_bottom, columns, seed, max_depth)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:honey_block" if is_tip else "minecraft:honeycomb_block"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # a few bare honey droplets clinging near the outer rim
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:honey_block",
            r_frac_threshold=0.55, chance=0.14, length_range=(1, 2),
        )

    if decorate_top:
        # sparse wildflowers and a beehive or two on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.12:
                block = rng.choice(
                    ["minecraft:dandelion", "minecraft:poppy",
                     "minecraft:cornflower", "minecraft:oxeye_daisy", "minecraft:allium"]
                )
                blocks.setdefault((x, topY + 1, z), block)

        hive_spots = [c for c in columns if c[4] / c[5] < 0.6]
        rng.shuffle(hive_spots)
        for (x, z, topY, depth, r, localR) in hive_spots[: rng.randint(0, 2)]:
            blocks[(x, topY + 1, z)] = "minecraft:beehive"

        # a couple of small birch trees
        tree_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(tree_spots)
        for (x, z, topY, depth, r, localR) in tree_spots[: rng.randint(0, 2)]:
            trunk_h = rng.randint(3, 5)
            for dy in range(trunk_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:birch_log"
            leaf_y = topY + 1 + trunk_h
            for dx in range(-2, 3):
                for dz in range(-2, 3):
                    for dy in range(0, 3):
                        if dx * dx + dz * dz + dy * dy <= 5 and rng.random() < 0.85:
                            blocks.setdefault((x + dx, leaf_y + dy, z + dz), "minecraft:birch_leaves")

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big honeycomb-hive island plus satellites and floating wax debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:honeycomb_block")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:honeycomb_block": "#e8ab3f",
    "minecraft:oak_planks": "#b8853f",
    "minecraft:stone": "#8a8a8a",
    "minecraft:honey_block": "#f0a91f",
    "minecraft:beehive": "#d9a441",
    "minecraft:dandelion": "#e8c93a",
    "minecraft:poppy": "#c0392b",
    "minecraft:cornflower": "#4166f5",
    "minecraft:oxeye_daisy": "#e8e8d0",
    "minecraft:allium": "#b070d0",
    "minecraft:birch_log": "#d8cfa8",
    "minecraft:birch_leaves": "#7bab5e",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a honeycomb-hive floating island for Minecraft.",
        out_default="hive_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"honeycomb hive floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"honeycomb hive multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging honey drips (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter wildflowers, beehives and birch trees on top (off by default)",
    )


if __name__ == "__main__":
    main()
