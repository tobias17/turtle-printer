"""
Gearworks Floating Island Generator for Minecraft
=====================================================

A copper-and-redstone machine island variant: weathered copper crust over
plain andesite, grading to deepslate at the very core. Structurally it
reads as a slab of circuit board hanging in the sky rather than any kind
of natural rock: the underside is quantized by an orthogonal cartesian
grid (not a radial pattern like prismarine's towers, not a hex tessellation
like hive's comb, not a random walk like swamp's roots) into a shallow
open shelf, copper-walled wiring trenches running in straight lines, and
deeper intersection "sockets" capped with lit redstone lamps wherever two
trenches cross - see `_circuit_grid`. The single intersection nearest the
island's own center additionally grows one extra copper shaft straight
down past the rest of the machine, capped with a lone lodestone, reading
as the engine core the whole board is wired into.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the gearworks-
specific block choices and decoration.

Usage:
    python gearworks.py --diameter 40
    python gearworks.py --diameter 40 --seed 7
"""

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Copper crust down through plain andesite to deepslate at the core - kept
# to 3 solid bands (no fleck/dither). Redstone block, redstone lamp and
# lodestone are reserved exclusively for the circuit grid's wires,
# intersections and core (see _circuit_grid), never part of the bulk
# gradient, so they read as deliberate machine parts rather than more bulk
# texture.
GRADIENT = [
    "minecraft:copper_block",
    "minecraft:andesite",
    "minecraft:deepslate",
]

GRID_SPACING = 9.0  # world-space distance between wiring trenches, in blocks
WIRE_HALF_WIDTH = 1.1  # a column within this of a grid line counts as "wire"
SHELF_DEPTH_FRAC = 0.12  # base depth for open circuit-board shelf columns -
                          # kept thin so the board reads as a flat plate
TRENCH_DEPTH_FRAC = 0.65  # much deeper band for columns on a single wire
                           # line, so trenches read as slots cut through the
                           # plate rather than a subtle dimple
NODE_DEPTH_FRAC = 0.85  # deeper still where two wire lines cross
WIRE_BAND_FRAC = 0.5  # fraction of a wire/node column's own final depth,
                       # right at the cut surface, recolored as copper wall
CORE_EXTRA_FRAC = 0.6  # extra shaft length (relative to max_depth) the
                        # single central-most intersection grows past its
                        # own socket depth, down to the lodestone core


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    copper crust, 1 = deepest rock). `jitter` (driven only by smooth
    per-column noise) nudges the whole column toward a neighboring shade so
    the band edge is wavy instead of a razor-straight ring, without
    per-voxel dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_machine_crust(rng):
    """Top-crust block: solid copper, no fleck - the crust is a flat platform."""
    return "minecraft:copper_block"


def _grid_offset(v, phase):
    """Distance from world coordinate v to the nearest wiring line, where
    lines run every GRID_SPACING starting at `phase`."""
    m = (v - phase) % GRID_SPACING
    return min(m, GRID_SPACING - m)


def _circuit_grid(blocks, col_bottom, columns, rng, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into a circuit board: every column is classified by how close
    it sits to an orthogonal cartesian grid of wiring lines (see
    _grid_offset) into one of three depth bands - open shelf, single-wire
    trench, or two-wire intersection socket - and truncated down to that
    band's shared depth, exactly like desert.py's mesa terraces quantize
    depth into bands, just partitioned by grid-line distance instead of by
    radius. Trench and socket columns get their cut walls recolored copper
    and their floor capped with redstone (plain redstone block on a wire,
    a lit redstone lamp at a socket), so the underside reads as wiring
    grooved into the board rather than a smooth taper.

    A cartesian grid (as opposed to hive.py's hex tessellation, prismarine's
    radial towers, or swamp.py's random-walk roots) is what makes this read
    as manufactured circuitry rather than anything organic or radially
    symmetric.

    The single socket column nearest the island's own center then grows one
    extra copper shaft straight down past its own socket depth (purely
    additive, the same "exempt one deep feature and extend it further than
    its own natural taper" trick prismarine.py's towers use), capped with a
    lone lodestone - the engine core the rest of the board wires into. Since
    that shaft is a single straight vertical column, each stamped block sits
    directly above the next with no horizontal drift, so it can never come
    disconnected the way a curved/angled path could.

    Like desert.py's mesa terracing, the quantizing pass only ever *removes*
    already-carved blocks and keeps col_bottom/columns in sync (drips/rim
    decoration read those for each column's true bottom), and is
    deliberately local to gearworks.py rather than a carve_columns option,
    so no other theme is affected.
    """
    shelf_depth = max(3, int(max_depth * SHELF_DEPTH_FRAC))
    trench_depth = max(shelf_depth + 2, int(max_depth * TRENCH_DEPTH_FRAC))
    node_depth = max(trench_depth + 2, int(max_depth * NODE_DEPTH_FRAC))
    core_extra = max(4, int(max_depth * CORE_EXTRA_FRAC))

    phase_x = rng.uniform(0, GRID_SPACING)
    phase_z = rng.uniform(0, GRID_SPACING)

    new_columns = []
    node_candidates = []
    for (x, z, topY, depth, r, localR) in columns:
        is_wire_x = _grid_offset(x, phase_x) <= WIRE_HALF_WIDTH
        is_wire_z = _grid_offset(z, phase_z) <= WIRE_HALF_WIDTH

        if is_wire_x and is_wire_z:
            kind, target = "node", min(depth, node_depth)
        elif is_wire_x or is_wire_z:
            kind, target = "wire", min(depth, trench_depth)
        else:
            kind, target = "shelf", min(depth, shelf_depth)

        bottomY, _, _, _ = col_bottom[(x, z)]
        new_bottomY = topY - target
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)

        if kind != "shelf":
            band = max(1, int(target * WIRE_BAND_FRAC))
            for y in range(new_bottomY, min(topY, new_bottomY + band)):
                if (x, y, z) in blocks:
                    blocks[(x, y, z)] = "minecraft:copper_block"
            floor = "minecraft:redstone_lamp" if kind == "node" else "minecraft:redstone_block"
            blocks[(x, new_bottomY, z)] = floor

        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, target, r, localR))
        if kind == "node":
            node_candidates.append(len(new_columns) - 1)

    columns[:] = new_columns

    if node_candidates:
        ci = min(node_candidates, key=lambda i: columns[i][4])
        cx, cz, ctopY, cdepth, cr, clocalR = columns[ci]
        core_bottom = ctopY - cdepth
        new_core_bottom = core_bottom - core_extra
        for y in range(new_core_bottom, core_bottom):
            blocks[(cx, y, cz)] = "minecraft:copper_block"
        blocks[(cx, new_core_bottom, cz)] = "minecraft:lodestone"
        col_bottom[(cx, cz)] = (new_core_bottom, ctopY, cr, clocalR)
        columns[ci] = (cx, cz, ctopY, cdepth + core_extra, cr, clocalR)


def generate_island(seed=0, diameter=40, top_thickness_range=(3, 5), max_depth=14,
                     num_drips=None, drip_density=0.02, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one gearworks
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of copper-crust layers, before
                       the andesite/deepslate gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       chain with a lit redstone-lamp bulb at its tip,
                       distinct from the main wiring grid.
    decorate_top     - if True, scatters loose machine parts on top.
    decorate_underside - the circuit-grid shaping, hanging cables and
                       fringe on the underside. On by default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_machine_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_machine_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # quantize the underside into a wiring grid with a hanging engine core -
    # see _circuit_grid above.
    _circuit_grid(blocks, col_bottom, columns, rng, max_depth)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:redstone_lamp" if is_tip else "minecraft:chain"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # a few loose iron brackets clinging near the outer rim
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:iron_bars",
            r_frac_threshold=0.55, chance=0.14, length_range=(1, 2),
        )

    if decorate_top:
        # sparse loose machine parts on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.06:
                blocks.setdefault((x, topY + 1, z), "minecraft:observer")

        rod_spots = [c for c in columns if c[4] / c[5] < 0.6]
        rng.shuffle(rod_spots)
        for (x, z, topY, depth, r, localR) in rod_spots[: rng.randint(0, 3)]:
            blocks[(x, topY + 1, z)] = "minecraft:lightning_rod"

        # a couple of small copper pipe stacks
        pipe_spots = [c for c in columns if c[4] / c[5] < 0.5]
        rng.shuffle(pipe_spots)
        for (x, z, topY, depth, r, localR) in pipe_spots[: rng.randint(0, 2)]:
            pipe_h = rng.randint(2, 4)
            for dy in range(pipe_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:copper_block"

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big gearworks island plus satellites and floating copper debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:copper_block")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:copper_block": "#c06f4a",
    "minecraft:andesite": "#888a8c",
    "minecraft:deepslate": "#393a3d",
    "minecraft:redstone_block": "#a91e1e",
    "minecraft:redstone_lamp": "#f7e2a0",
    "minecraft:lodestone": "#8f8b7a",
    "minecraft:chain": "#5b5b5b",
    "minecraft:iron_bars": "#c6c6c6",
    "minecraft:observer": "#6b6b4f",
    "minecraft:lightning_rod": "#a56b45",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a gearworks floating island for Minecraft.",
        out_default="gearworks_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"gearworks floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"gearworks multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging chains with lit bulbs (default: auto-scales with "
                         "the island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter loose machine parts on top (off by default)",
    )


if __name__ == "__main__":
    main()
