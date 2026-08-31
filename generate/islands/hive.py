"""
Honeycomb Hive Floating Island Generator for Minecraft
=========================================================

A giant hardened-honeycomb island variant: a spruce-plank crust over a
waxy honey-block core, dotted with wild meadow flowers and beehives on
top. Structurally the underside is a perfectly regular hexagon grid (see
`_honeycomb_cells`) of hollow tubes extending straight down from the
platform - open shafts with uniform, single-material honey-block walls,
not filled comb blocks - with NO per-cell noise or randomness anywhere in
the pattern itself: every wall is exactly one voxel thick (an exact
hex-edge test, not a rounded approximation) and one uniform color top to
bottom.
The only thing that varies from cell to cell is how far down each tube
reaches, and that's set by a smooth, deterministic function of the cell's
own distance from the island's center (deepest at the center, shortest at
the rim), so the ensemble is cut off into roughly the same upside-down
mound silhouette while the grid underneath it stays perfectly uniform.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the hive-
specific block choices and decoration.

Usage:
    python hive.py --diameter 40
    python hive.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Spruce-plank crust for the platform itself. The tube walls below it are a
# single uniform frame material (see _honeycomb_cells) rather than a
# depth-based gradient - there's deliberately no third/deeper band here,
# since every below-crust column is either that one wall material or empty
# air, never a smooth color transition.
GRADIENT = [
    "minecraft:spruce_planks",
    "biomesoplenty:honey_block",
]

HEX_SIZE = 5.0  # world-space radius of one honeycomb cell, in blocks
SQRT3 = math.sqrt(3.0)
TAPER_POWER = 1.0  # exponent on (1 - radius_fraction) used to set each
                    # cell's tube length - a smooth, deterministic falloff
                    # from center to rim (tapering to nothing right at the
                    # rim - see cell_depth), with no per-cell noise anywhere


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    spruce-plank crust, 1 = deepest rock). `jitter` (driven only by smooth
    per-column noise) nudges the whole column toward a neighboring shade so
    the band edge is wavy instead of a razor-straight ring, without
    per-voxel dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_comb_crust(rng):
    """Top-crust block: solid spruce plank, no fleck - the crust is a flat platform."""
    return "minecraft:spruce_planks"


def _hex_cell(x, z, size):
    """Maps a world (x, z) to its enclosing pointy-top hexagon cell (q, r),
    using the standard axial round (redblobgames' hex-grid algorithm)."""
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
    return (int(rx), int(rz))


def _is_wall(x, z, size):
    """A column is a wall column iff moving to any orthogonal neighbor
    crosses into a different hex cell - i.e. it sits exactly on a cell
    boundary. This traces the TRUE hexagon edges to voxel resolution
    instead of the previous approach (a circle-from-center distance
    threshold, which only approximated the edges and rounded unevenly), so
    every wall comes out an exact, uniform single voxel thick everywhere."""
    cell = _hex_cell(x, z, size)
    return (_hex_cell(x + 1, z, size) != cell or _hex_cell(x - 1, z, size) != cell or
            _hex_cell(x, z + 1, size) != cell or _hex_cell(x, z - 1, size) != cell)


def _honeycomb_cells(blocks, col_bottom, columns, max_depth, crust_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into a perfectly regular hex-tube grid: every column is
    assigned to one pointy-top hex cell (see _hex_cell), and every column
    in the same cell is set to exactly that cell's own tube length - a
    smooth, purely deterministic function of the cell's average distance
    from the island's own center (TAPER_POWER), with NO per-cell or
    per-column randomness anywhere. Cutting each cell to its own length is
    additive as well as subtractive (blocks are added if the column's
    natural carve_columns depth was shallower than the target, removed if
    deeper), which guarantees every column in a cell ends at exactly the
    same Y - a level, uniform tube floor, never a jagged one - the same
    "cut a regular grid down to a silhouette" idea as prismarine.py's
    towers or gearworks.py's circuit grid, just applied to every cell
    instead of a sparse symmetric subset.

    Wall columns (see _is_wall) are solid, recolored one uniform frame
    material top to bottom - no gradient, no accent, no randomness.
    Interior columns - and any wall whose cell tapers to less than
    crust_depth this close to the rim (see cell_depth) - are cleared
    entirely below the shared crust cap (crust_depth - the minimum
    top-crust thickness every column is guaranteed to have), so a cell
    with no meaningful tube length just sits flush with the platform,
    never hanging a wall stub past the crust's own edge, and each real
    tube reads as an open shaft - air inside, walls only - rather than a
    filled comb block.

    Unlike desert.py's mesa terracing (subtractive only), this is
    deliberately also additive so every wall in a cell lines up exactly;
    it keeps col_bottom/columns in sync (top decoration reads those for
    each column's true bottom) and is deliberately local to hive.py rather
    than a carve_columns option, so no other theme is affected.
    """
    cell_members = {}
    for c in columns:
        cell = _hex_cell(c[0], c[1], HEX_SIZE)
        cell_members.setdefault(cell, []).append(c)

    depth_cache = {}

    def cell_depth(cell):
        if cell not in depth_cache:
            members = cell_members[cell]
            # the MAX (not average) member radius fraction - a cell that
            # only partially overlaps the island (straddling the rim) has
            # at least one member right at the edge, so this correctly
            # taps that whole cell down to zero along with truly-interior
            # rim cells, instead of a partial-overlap cell getting a full
            # wall out of its few members that happen to sit further in
            frac = max((m[4] / m[5] if m[5] else 1.0) for m in members)
            taper = max(0.0, 1.0 - frac) ** TAPER_POWER
            raw = round(taper * max_depth)
            # a tube shorter than the crust itself isn't a tube at all -
            # treat it as zero so that cell sits flush with the platform
            # instead of hanging a short wall stub past its own edge
            depth_cache[cell] = raw if raw >= crust_depth else 0
        return depth_cache[cell]

    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        cell = _hex_cell(x, z, HEX_SIZE)
        target = cell_depth(cell)
        bottomY, _, _, _ = col_bottom[(x, z)]
        new_bottomY = topY - target
        crust_bottom = topY - crust_depth + 1

        if target > 0 and _is_wall(x, z, HEX_SIZE):
            # trim any natural excess below the tube's own cutoff, then
            # (re)fill the whole tube one uniform material - this also
            # ADDS blocks where the natural taper was shallower than the
            # target, so every wall in the cell ends at the same exact Y
            for y in range(bottomY, new_bottomY):
                blocks.pop((x, y, z), None)
            for y in range(new_bottomY, crust_bottom):
                blocks[(x, y, z)] = "biomesoplenty:honey_block"
        else:
            # hollow interior, OR a wall whose cell has zero tube length
            # this close to the rim - either way, clear the whole shaft
            # below the shared crust cap so nothing hangs past the crust
            for y in range(bottomY, crust_bottom):
                blocks.pop((x, y, z), None)
            new_bottomY = crust_bottom

        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, topY - new_bottomY, r, localR))
    columns[:] = new_columns


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one honeycomb-hive
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of spruce-plank crust layers,
                       before the oak-frame/rock gradient starts.
    num_drips / drip_density - unused by this theme (kept only so every
                       theme's generate_island shares the same CLI/run_cli
                       signature) - the hex tubes are the whole underside
                       shape, not a base taper with separate hanging drips.
    decorate_top     - if True, scatters meadow flowers, beehives and small
                       birch trees on top.
    decorate_underside - unused by this theme, for the same reason as
                       num_drips above - the hex-tube tessellation always
                       runs; there's no separate underside decoration to
                       toggle.
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
    # tessellate the underside into hollow hex tubes stepping down with the
    # island's own radius-based taper - see _honeycomb_cells above. This is
    # the theme's whole shape, not an optional flourish, so it always runs
    # regardless of decorate_underside - there are no separate hanging
    # drips/rim spikes layered on top of it (the hex tubes themselves are
    # the "shape", not dripstone-style stalactites).
    _honeycomb_cells(blocks, col_bottom, columns, max_depth, top_thickness_range[0])

    if decorate_top:
        # sparse wildflowers and a beehive or two on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.12:
                block = rng.choice(["minecraft:dandelion", "minecraft:cornflower"])
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
    """One big honeycomb-hive island plus satellites and floating plank debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:spruce_planks")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:spruce_planks": "#7a5c38",
    "biomesoplenty:honey_block": "#e8ab3f",
    "minecraft:beehive": "#d9a441",
    "minecraft:dandelion": "#e8c93a",
    "minecraft:cornflower": "#4166f5",
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
        num_drips_help="unused by this theme - the hex-tube grid is the whole underside shape",
        decorate_top_help="scatter wildflowers, beehives and birch trees on top (off by default)",
    )


if __name__ == "__main__":
    main()
