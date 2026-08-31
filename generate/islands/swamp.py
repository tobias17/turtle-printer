"""
Mangrove Bog Floating Island Generator for Minecraft
=====================================================

A swamp/bog island variant: mottled swamp stone and moss on top (with the
occasional bog pool), grading down through gnarled mangrove roots into
the plain rock core every island theme shares underneath. Structurally it's a
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

# Swamp stone crust down to plain rock at the core - kept to 2 solid bands (no
# fleck/dither); the mangrove-root colors are reserved exclusively for the
# rim skirt's root trunks (see _grow_root_trunks) so roots read as a
# distinct material growing off the island, not more bulk texture.
GRADIENT = [
    "botania:biomestonea_swamp",
    "minecraft:stone",
]

RIM_BAND = (0.5, 0.95)  # r/localR range that keeps full depth + grows roots


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    swamp-stone crust, 1 = deepest rock). `jitter` (driven only by smooth per-column
    noise) nudges the whole column toward a neighboring shade so the band
    edge is wavy instead of a razor-straight ring, without per-voxel
    dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_bog_crust(rng):
    """Top-crust block: solid swamp stone, no fleck - the crust is a flat platform."""
    return "botania:biomestonea_swamp"


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


def _grow_one_root(blocks, rng, x, z, bottomY, length, root_r0, taper_power, angle):
    """Grows a single gnarled root of `length` voxels starting at (x, z,
    bottomY), curving via a slow random walk in `angle` (rather than a
    fixed direction) so it reads as a gnarled root groping downward, not a
    straight spike. Returns the (fx, fz, y, radius) state at its tip, for
    optional offshoot branches."""
    fx, fz = float(x), float(z)
    for i in range(length):
        y = bottomY - 1 - i
        angle += rng.uniform(-0.5, 0.5)
        drift = rng.uniform(0.2, 0.5)
        fx += math.cos(angle) * drift
        fz += math.sin(angle) * drift
        bx, bz = round(fx), round(fz)
        t = i / max(1, length - 1)
        radius = root_r0 * max(0.0, 1 - t) ** taper_power
        ir = math.floor(radius)
        for dx in range(-ir, ir + 1):
            for dz in range(-ir, ir + 1):
                if dx * dx + dz * dz <= radius * radius:
                    blocks.setdefault((bx + dx, y, bz + dz), "minecraft:mangrove_roots")
    return fx, fz, bottomY - length, angle


def _grow_root_trunks(blocks, columns, col_bottom, rng, max_depth):
    """Grows a handful of short, gnarled mangrove-root clumps down from the
    deep rim skirt left by _rim_skirt - stubby roots groping down and
    forking, kept close to the island's own natural depth, instead of a
    straight vertical extension. Purely additive (like common.generate_drips'
    own dx/dz-offset splash, just wandering instead of centered) - it only
    ever places new blocks below/beside a rim column's existing bottom and
    never touches col_bottom/columns, so nothing downstream misattributes
    another column's true depth.

    Kept deliberately short (scaled like common.generate_drips' own drip
    lengths) and bent via a random walk in direction rather than a fixed
    heading - a long, nearly-straight root reads as an out-of-place spike
    poking away from the island, not part of its shape. Each main root
    forks partway down into 1-2 thinner offshoots so it reads as a root
    clump, not a single tendril.
    """
    lo, hi = RIM_BAND
    candidates = [c for c in columns if lo <= ((c[4] / c[5]) if c[5] else 1.0) <= hi]
    rng.shuffle(candidates)
    n_trunks = min(len(candidates), rng.randint(6, 11))
    len_floor = max(2, round(max_depth * 0.12))
    len_ceiling = max(len_floor + 2, round(max_depth * 0.35))
    for (x, z, topY, depth, r, localR) in candidates[:n_trunks]:
        bottomY, _, _, _ = col_bottom[(x, z)]
        length = rng.randint(len_floor, len_ceiling)
        angle = rng.uniform(0, 2 * math.pi)
        root_r0 = rng.uniform(1.3, 1.9)
        taper_power = rng.uniform(1.1, 1.6)
        fx, fz, fork_y, fork_angle = _grow_one_root(
            blocks, rng, x, z, bottomY, length, root_r0, taper_power, angle)

        for _ in range(rng.randint(1, 2)):
            branch_len = rng.randint(len_floor, max(len_floor, int(length * 0.6)))
            branch_angle = fork_angle + rng.uniform(-1.4, 1.4)
            _grow_one_root(
                blocks, rng, round(fx), round(fz), fork_y, branch_len,
                root_r0 * 0.6, taper_power, branch_angle)


def generate_island(seed=0, diameter=40, top_thickness_range=(3, 5), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one mangrove-bog
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of swamp-stone crust layers, before
                       the root/clay gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a hanging
                       clump of muck, distinct from the dedicated root
                       trunks grown from the rim skirt.
    decorate_top     - if True, scatters moss patches and mangrove trees on top.
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
        return pick_gradient(rng, t_grad, jitter=g_jitter)

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
            return "minecraft:mangrove_roots" if is_tip else "botania:biomestonea_swamp"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # a bit of hanging root debris near the outer rim - moss_carpet
        # can't be used here even as a solid-looking accent: carpet only
        # stays placed with a solid block directly BELOW it, not above,
        # so a "hanging" chain of it (this decoration stacks new blocks
        # downward into open air) would just pop off - see
        # common.decorate_rim_underside's own docstring
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:mangrove_roots",
            r_frac_threshold=0.55, chance=0.2, length_range=(2, 5),
        )

    if decorate_top:
        # sparse moss patches on the top surface - not lily pads, which
        # only exist floating on water and this dry build never has any
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.12:
                blocks.setdefault((x, topY + 1, z), "minecraft:moss_carpet")

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
    return common.basic_scene(seed, generate_island, debris_block="botania:biomestonea_swamp")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "botania:biomestonea_swamp": "#5a6b4d",
    "minecraft:mangrove_roots": "#5a3d28",
    "minecraft:stone": "#8a8a8a",
    "minecraft:moss_carpet": "#4f7a2a",
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
        decorate_top_help="scatter moss patches and mangrove trees on top (off by default)",
    )


if __name__ == "__main__":
    main()
