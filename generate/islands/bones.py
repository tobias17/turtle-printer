"""
Ossuary Ribcage Floating Island Generator for Minecraft
===========================================================

A bleached bone-wasteland island variant: pale bone crust over charred
coal, grading to plain deepslate at the very core. Structurally it inverts
every other theme's idea: instead of a solid mass with one deep feature
exempted (crystal's spikes, prismarine's towers), the ENTIRE underside is
first hollowed out to a thin ceiling right under the crust, and only a
handful of thick bone ribs are added back in - deterministic, non-random
spokes that curve down and inward from evenly-spaced points on the
island's own irregular rim until they all converge on one shared point,
capped with a lone soul lantern like a glowing sternum. The result reads
as a hollow ribcage hanging in open air, not a tapering cone.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the bone-
specific block choices and decoration.

Usage:
    python bones.py --diameter 40
    python bones.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Bone crust down through charred coal to plain deepslate at the core -
# kept to 3 solid bands (no fleck/dither). The soul lantern is reserved
# exclusively for the ribcage's convergence point (see _rib_cage), never
# part of the bulk gradient, so it reads as one deliberate glowing feature
# rather than more bulk texture.
GRADIENT = [
    "minecraft:bone_block",
    "minecraft:coal_block",
    "minecraft:deepslate",
]

CEILING_DEPTH_FRAC = 0.15  # how much of a shallow ceiling every column
                            # keeps before the underside is hollowed out
N_RIBS = 6
RIB_LEN_FRAC = 0.9  # how far the ribs reach relative to max_depth
RIB_RADIUS = 1  # half-width beyond the rib's own center line at its base
RIB_TAPER_EXP = 1.4  # how sharply each rib's radius shrinks toward the tip
RIM_CANDIDATE_FRAC = 0.85  # r/localR threshold for a column to count as
                            # "on the rim" when anchoring a rib's start


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the bone
    crust, 1 = deepest rock). `jitter` (driven only by smooth per-column
    noise) nudges the whole column toward a neighboring shade so the band
    edge is wavy instead of a razor-straight ring, without per-voxel
    dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_bone_crust(rng):
    """Top-crust block: solid bone, no fleck - the crust is a flat platform."""
    return "minecraft:bone_block"


def _grow_rib(blocks, y0, length, start_r, angle):
    """Grows one deterministic rib: a straight radial spoke that starts at
    radius `start_r` right under the ceiling (y0) and tapers down and
    inward, its radius shrinking smoothly to 0 by the final step so every
    rib converges on the exact same central point regardless of where
    around the rim it started. Unlike swamp.py's root growth (a random
    walk, different every time), this path is a fixed formula - every rib
    is the identical shape, just rotated by `angle` - which is what makes
    it read as a built skeleton instead of something organically grown.

    The radius shrinks fastest right at the start (large `start_r`, steep
    part of the (1-t)**RIB_TAPER_EXP curve), so a naive one-sample-per-Y-
    layer walk can move horizontally by more than the rib's own thickness
    between consecutive layers, leaving disconnected fragments floating
    behind - invisible from outside the rendered mesh but a real broken
    connection. Supersampling `t` (many samples per Y layer, not just one)
    keeps every consecutive pair of stamped discs overlapping regardless of
    `start_r`, so the rib is one unbroken tube from rim to tip.

    Returns the Y of the rib's final (tip) step."""
    samples = max(length, int(math.ceil(RIB_TAPER_EXP * start_r)) + 10)
    tip_y = y0
    for i in range(samples):
        t = i / max(1, samples - 1)
        r = start_r * (1 - t) ** RIB_TAPER_EXP
        x, z = r * math.cos(angle), r * math.sin(angle)
        y = round(y0 - t * (length - 1))
        ix, iz = round(x), round(z)
        # never let this drop to 0: a zero-radius disc is a single voxel,
        # and a chain of single voxels drifting diagonally through 3D space
        # can lose face-adjacency between consecutive samples even when
        # finely supersampled (a purely diagonal step is never face-
        # connected). Floors at a solid 3x3 disc instead, so ribs converge
        # into a small solid clump at the tip rather than a fragile point.
        thickness = max(1, round(RIB_RADIUS * (1 - 0.6 * t)))
        for dx in range(-thickness, thickness + 1):
            for dz in range(-thickness, thickness + 1):
                if dx * dx + dz * dz <= thickness * thickness:
                    blocks[(ix + dx, y, iz + dz)] = "minecraft:bone_block"
        tip_y = y
    return tip_y


def _rib_cage(blocks, col_bottom, columns, rng, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into a hollow ribcage. First EVERY column is truncated down
    to a thin shared ceiling just under the crust, so the entire underside
    starts out as open air rather than solid rock. Then N_RIBS thick bone
    spokes are grown back in additively (see _grow_rib) from points spaced
    evenly around the island's own irregular rim, each one curving straight
    down and inward until every rib meets at one shared point on the
    center line, which gets capped with a lone soul lantern - a glowing
    sternum where the ribs converge.

    Every other theme so far keeps the underside mostly SOLID and exempts
    one deep feature from flattening (crystal's spikes, prismarine's
    towers, this file's own hive.py cousin's hex cells); this one inverts
    that - the underside starts EMPTY and only the ribs themselves are
    added back, which is what makes it read as a hollow cage instead of a
    solid mass with some bumps.

    Like desert.py's mesa terracing, the ceiling pass only ever *removes*
    already-carved blocks and keeps col_bottom/columns in sync (drips/rim
    decoration read those for each column's true bottom); the rib geometry
    itself is purely additive and deliberately local to bones.py rather
    than a carve_columns option, so no other theme is affected.
    """
    ceiling_depth = max(2, int(max_depth * CEILING_DEPTH_FRAC))
    rib_len = max(4, int(max_depth * RIB_LEN_FRAC))
    phase = rng.uniform(0, 2 * math.pi)

    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        target = min(depth, ceiling_depth)
        bottomY, _, _, _ = col_bottom[(x, z)]
        new_bottomY = topY - target
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)
        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, target, r, localR))
    columns[:] = new_columns

    if not columns:
        return

    # topY is identical for every column (rule 1: the top is always
    # perfectly flat). Most columns get truncated down to exactly
    # ceiling_depth, but a column whose own NATURAL taper was already
    # shallower than that (true right at the rim, where the taper is
    # closing off) keeps its own shallower depth instead (see `target =
    # min(depth, ceiling_depth)` above) - its ceiling doesn't reach the
    # common ceiling_y at all. Rib candidates are deliberately chosen near
    # the rim (RIM_CANDIDATE_FRAC), so they're exactly the columns likely
    # to hit that case - anchoring every rib to one shared, assumed-uniform
    # ceiling_y left a gap between a shallow candidate's real bottom and
    # the rib's attachment point, orphaning the whole rib. Each rib must
    # anchor to ITS OWN candidate's actual post-flatten bottom instead.
    default_ceiling_y = columns[0][2] - ceiling_depth

    candidates = [c for c in columns if (c[4] / c[5] if c[5] else 0) > RIM_CANDIDATE_FRAC] or columns
    tip_y = default_ceiling_y
    for k in range(N_RIBS):
        target_angle = phase + k * (2 * math.pi / N_RIBS)
        best = min(candidates, key=lambda c: abs(
            ((math.atan2(c[1], c[0]) - target_angle + math.pi) % (2 * math.pi)) - math.pi))
        # anchor the rib to the candidate's OWN actual angle, not the
        # idealized target_angle - the island's silhouette is irregular, so
        # start_r (this candidate's real radius) paired with target_angle
        # can land just outside the real ceiling at that exact bearing,
        # orphaning the entire rib from the moment it's grown. Using the
        # candidate's real (r, angle) together guarantees the rib's first
        # sample coincides with a real ceiling column; ribs still land at
        # approximately evenly-spaced bearings since candidates are chosen
        # nearest each target_angle.
        actual_angle = math.atan2(best[1], best[0])
        best_topY, best_depth = best[2], best[3]
        rib_y0 = best_topY - best_depth
        tip_y = _grow_rib(blocks, rib_y0, rib_len, best[4], actual_angle)

    blocks[(0, tip_y, 0)] = "minecraft:soul_lantern"


def generate_island(seed=0, diameter=40, top_thickness_range=(3, 5), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one ossuary-
    ribcage island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of bone-crust layers, before
                       the coal/deepslate gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a small
                       hanging bone spur off the thin ceiling, distinct
                       from the main ribs.
    decorate_top     - if True, scatters wither roses, bone cairns and the
                       occasional skull on top.
    decorate_underside - the ribcage shaping, hanging spurs and fringe on
                       the underside. On by default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_bone_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_bone_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    # hollow the underside into open air, add back a converging bone
    # ribcage - see _rib_cage above.
    _rib_cage(blocks, col_bottom, columns, rng, max_depth)

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:bone_block" if is_tip else "minecraft:coal_block"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # a few bare coal crumbs clinging near the outer rim
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:coal_block",
            r_frac_threshold=0.55, chance=0.14, length_range=(1, 2),
        )

    if decorate_top:
        # sparse wither roses on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.08:
                blocks.setdefault((x, topY + 1, z), "minecraft:wither_rose")

        # a couple of small bone cairns, and rarely a bare skull on top of one
        cairn_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(cairn_spots)
        for (x, z, topY, depth, r, localR) in cairn_spots[: rng.randint(0, 3)]:
            cairn_h = rng.randint(1, 3)
            for dy in range(cairn_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:bone_block"
            if rng.random() < 0.3:
                blocks[(x, topY + 1 + cairn_h, z)] = "minecraft:skeleton_skull"

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big ossuary island plus satellites and floating bone debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:bone_block")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:bone_block": "#e4dcc0",
    "minecraft:coal_block": "#1c1c1c",
    "minecraft:deepslate": "#393a3d",
    "minecraft:soul_lantern": "#5fd6cf",
    "minecraft:wither_rose": "#2e2015",
    "minecraft:skeleton_skull": "#d8d4c0",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate an ossuary-ribcage floating island for Minecraft.",
        out_default="bones_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"ossuary ribcage floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"ossuary ribcage multi-island demo scene (seed={seed})",
        num_drips_help=("number of small hanging bone spurs (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter wither roses, bone cairns and skulls on top (off by default)",
    )


if __name__ == "__main__":
    main()
