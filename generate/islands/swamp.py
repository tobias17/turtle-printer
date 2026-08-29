"""
Mangrove Bog Floating Island Generator for Minecraft
=====================================================

A swamp/bog island variant: mud and moss on top (with the occasional bog
pool), grading down through muddy mangrove roots and clay into the plain
rock core every island theme shares underneath. Structurally it's a
"platter", not a dome or spike: the CENTER is shallow (a floating marsh
raft), while a ring near the rim keeps its full natural depth and then
grows thick, curving mangrove-root trunks that drift outward and downward
past the island's own taper - roots reaching for water below, not just
another hanging drip.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the swamp-
specific block choices and decoration.

Usage:
    python swamp.py --diameter 40
    python swamp.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Mud/moss crust down through muddy mangrove roots and clay into the plain
# rock core.
GRADIENT = [
    "minecraft:mud",
    "minecraft:muddy_mangrove_roots",
    "minecraft:mangrove_roots",
    "minecraft:clay",
    "minecraft:stone",
]

FLECK_CHANCE = 0.02  # rare clay fleck at any depth, for banding variety
POOL_CHANCE = 0.06  # rare bog-water pool breaking through the mud crust
RIM_BAND = (0.5, 0.95)  # r/localR range that keeps full depth + grows roots


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the mud
    crust, 1 = deepest rock). `jitter` blends toward a neighboring shade for
    per-column/per-voxel randomness instead of a perfectly smooth band."""
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


def pick_bog_crust(rng):
    """Top-crust / shallow-band block: mud with the odd patch of moss, and a
    rare open bog pool breaking through."""
    if rng.random() < POOL_CHANCE:
        return "minecraft:water"
    return "minecraft:moss_block" if rng.random() < 0.25 else "minecraft:mud"


def _rim_skirt(blocks, col_bottom, columns, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into a "platter" instead of a dome: the whole center is
    hard-capped to a shallow shelf (a floating marsh raft), while a ring
    near the rim (RIM_BAND) is left completely untouched at its full
    natural depth. Every other theme so far exempts a *center* patch from
    flattening (mushroom's stem, crystal's spikes); this one flips it -
    exempting a *rim band* instead - so the silhouette reads as a shallow
    disc with a deep skirt around the edge, not a shallow disc with a
    point/spike in the middle.

    Like desert.py's mesa terracing, this only ever *removes* already-
    carved blocks and keeps col_bottom/columns in sync (drips/rim
    decoration read those for each column's true bottom), and is
    deliberately local to swamp.py rather than a carve_columns option, so
    no other theme is affected.
    """
    shelf_depth = max(4, int(max_depth * 0.35))
    lo, hi = RIM_BAND
    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        frac = r / localR if localR else 1.0
        if (lo <= frac <= hi) or depth <= shelf_depth:
            new_columns.append((x, z, topY, depth, r, localR))
            continue
        bottomY, _, _, _ = col_bottom[(x, z)]
        new_bottomY = topY - shelf_depth
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)
        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, shelf_depth, r, localR))
    columns[:] = new_columns


def _grow_root_trunks(blocks, columns, col_bottom, rng, max_depth):
    """Grows a handful of thick mangrove-root trunks down from the deep rim
    skirt left by _rim_skirt, each one drifting laterally as it descends -
    a curving root reaching outward and down past the island's own deepest
    point, instead of a straight vertical extension. Purely additive (like
    common.generate_drips' own dx/dz-offset splash, just wandering instead
    of centered) - it only ever places new blocks below/beside a rim
    column's existing bottom and never touches col_bottom/columns, so nothing
    downstream misattributes another column's true depth.
    """
    lo, hi = RIM_BAND
    candidates = [c for c in columns if lo <= ((c[4] / c[5]) if c[5] else 1.0) <= hi]
    rng.shuffle(candidates)
    n_trunks = min(len(candidates), rng.randint(4, 8))
    for (x, z, topY, depth, r, localR) in candidates[:n_trunks]:
        bottomY, _, _, _ = col_bottom[(x, z)]
        length = rng.randint(int(max_depth * 0.5), int(max_depth * 1.1) + 3)
        angle = rng.uniform(0, 2 * math.pi)
        dirx, dirz = math.cos(angle), math.sin(angle)
        fx, fz = float(x), float(z)
        for i in range(length):
            y = bottomY - 1 - i
            drift = rng.uniform(0.15, 0.45)
            fx += dirx * drift
            fz += dirz * drift
            bx, bz = round(fx), round(fz)
            block = "minecraft:muddy_mangrove_roots" if rng.random() < 0.55 else "minecraft:mangrove_roots"
            blocks.setdefault((bx, y, bz), block)


def generate_island(seed=0, diameter=40, top_thickness_range=(3, 5), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one mangrove-bog
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of mud-crust layers, before
                       the root/clay gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       clump of muck, distinct from the dedicated root
                       trunks grown from the rim skirt.
    decorate_top     - if True, scatters lily pads, mangrove propagules and
                       seagrass on top.
    decorate_underside - rim-skirt shaping, root trunks, hanging muck and
                       moss fringe on the underside. On by default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_bog_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_bog_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter + rng.uniform(-0.9, 0.9))

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # flatten the center into a shallow raft, leave a deep rim skirt - see
    # _rim_skirt above.
    _rim_skirt(blocks, col_bottom, columns, max_depth)

    if decorate_underside:
        # grow curving mangrove-root trunks down from the rim skirt
        _grow_root_trunks(blocks, columns, col_bottom, rng, max_depth)

        def drip_block(rng, t, is_tip):
            if is_tip:
                return "minecraft:mangrove_roots"
            return "minecraft:muddy_mangrove_roots" if rng.random() < 0.5 else "minecraft:mud"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # a bit of hanging moss near the outer rim
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:moss_carpet" if rng.random() < 0.4 else "minecraft:mangrove_roots",
            r_frac_threshold=0.55, chance=0.2, length_range=(2, 5),
        )

    if decorate_top:
        # sparse lily pads, mangrove propagules and seagrass on the top
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.12:
                block = rng.choice(["minecraft:lily_pad", "minecraft:fern", "minecraft:mangrove_propagule"])
                blocks.setdefault((x, topY + 1, z), block)

        # a couple of small mangrove trees
        tree_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(tree_spots)
        for (x, z, topY, depth, r, localR) in tree_spots[: rng.randint(0, 2)]:
            trunk_h = rng.randint(2, 4)
            for dy in range(trunk_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:mangrove_log"
            leaf_y = topY + 1 + trunk_h
            for dx in range(-2, 3):
                for dz in range(-2, 3):
                    for dy in range(0, 2):
                        if dx * dx + dz * dz + dy * dy <= 5 and rng.random() < 0.85:
                            blocks.setdefault((x + dx, leaf_y + dy, z + dz), "minecraft:mangrove_leaves")

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big mangrove-bog island plus satellites and floating muck debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:mud")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:mud": "#4d3d2d",
    "minecraft:moss_block": "#5a7a2f",
    "minecraft:water": "#3f76e4",
    "minecraft:muddy_mangrove_roots": "#5c4a3a",
    "minecraft:mangrove_roots": "#5a3d28",
    "minecraft:clay": "#9aa3ad",
    "minecraft:stone": "#8a8a8a",
    "minecraft:moss_carpet": "#4f7a2a",
    "minecraft:lily_pad": "#3f7a2f",
    "minecraft:fern": "#4f8f3f",
    "minecraft:mangrove_propagule": "#8a4a3a",
    "minecraft:mangrove_log": "#5c2a2a",
    "minecraft:mangrove_leaves": "#4a6b2a",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a mangrove-bog floating island for Minecraft.",
        out_default="swamp_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"mangrove bog floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"mangrove bog multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging muck clumps (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter lily pads and mangrove trees on top (off by default)",
    )


if __name__ == "__main__":
    main()
