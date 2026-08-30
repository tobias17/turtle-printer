"""
Crystal Geode Floating Island Generator for Minecraft
=========================================================

A crystal-cave island variant, built to match a real geode photo rather
than reusing this project's usual dripstone-shaped underside: a lavender-
purple stone crust on top, and a handful of dense amethyst crystal PATCHES
hanging underneath, each one a tight bouquet of many individual hexagonal
crystal points - a straight-sided shaft topped with a hexagonal pyramid
point, not a cone that tapers along its whole length - fanned out from a
shared base with a pale "rind" ring and druse fuzz where they meet the
surrounding rock, the way an actual amethyst geode looks. See
_crystal_patch/_carve_crystal_point below for the shape itself; only the
island's overall taper/silhouette comes from common.carve_columns.

Usage:
    python crystal.py --diameter 40
    python crystal.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Neutral geode-cave rock, tinted purple at the surface and settling into
# plain dark stone with depth - the crust itself should already read as
# "amethyst-infused stone", not plain grey rock with crystals bolted on
# after the fact. Kept to solid bands (no fleck/dither) so the bulk rock
# reads as clean strata; the clustered crystal growths below are what
# carries the sparkle.
GRADIENT = [
    "minecraft:purpur_block",
    "minecraft:tuff",
    "minecraft:deepslate",
]

# Two near-identical purple stones, alternated for the crust so it isn't a
# flat, uniform color - both read as the same "purple stone", just enough
# texture variance to avoid looking painted.
CRUST_BLOCKS = ["minecraft:purpur_block", "minecraft:purpur_pillar"]


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    purple crust, 1 = deepest rock). `jitter` (driven only by smooth
    per-column noise) nudges the whole column toward a neighboring shade so
    the band edge is wavy instead of a razor-straight ring, without
    per-voxel dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_crust(rng):
    """Top-crust block: purple geode stone, lightly varied between two
    near-identical purple blocks - the crust is a flat platform."""
    return CRUST_BLOCKS[0] if rng.random() < 0.8 else CRUST_BLOCKS[1]


# ---------------------------------------------------------------------------
# Underside: a shallow rock floor with dense hexagonal-crystal patches
# ---------------------------------------------------------------------------
#
# Built from scratch off the reference geode photo, not by reusing/tuning
# this project's dripstone-drip machinery:
#   1. A shallow flat rock floor - the exposed matrix a real geode splits
#      open along.
#   2. A handful of dense crystal PATCHES on that floor. Each patch is many
#      individual hexagonal crystal points (see _carve_crystal_point)
#      packed close together, tallest at the patch's center and shorter
#      toward its edge, each leaning slightly outward the further it is
#      from center - together that's what makes a patch read as one
#      radiating bouquet instead of a forest of parallel rods.
#   3. A pale stone "rind" ring around each patch plus fine druse speckle
#      at the crystals' bases, where the reference photo's crystals meet
#      the surrounding rock.

FLOOR_DEPTH_RANGE = (5, 7)          # the flat rock floor the patches grow from

PATCH_COUNT_RANGE = (5, 8)          # number of crystal patches on the island
PATCH_RADIUS_FRAC = (0.15, 0.68)    # patches sit within this band of the island's radius
PATCH_FOOTPRINT_RANGE = (6.0, 10.0) # footprint radius of one patch
PATCH_HEIGHT_RANGE = (11, 20)       # tallest crystal point at a patch's center
POINT_RADIUS_RANGE = (1.1, 2.4)     # a single crystal point's shaft radius
TIP_FRAC = 0.4                      # fraction of a point's height spent narrowing to its tip
LEAN_STRENGTH = 0.55                # max sideways drift per block of height, at a patch's outer edge
RIND_BLOCK = "minecraft:calcite"    # pale stone ring around a patch, like a geode's outer shell


def _hex_radius(dx, dz):
    """Distance from (0, 0) in a regular-hexagon metric: the set of points
    with _hex_radius(dx, dz) <= R is a flat-sided hexagon of "radius" R
    (center to vertex). Three axes 60 degrees apart, take the largest
    projection - this is what gives crystal points their angular, faceted
    cross-section instead of a round icicle or a plain square block."""
    d1 = abs(dx)
    d2 = abs(0.5 * dx + 0.8660254037844386 * dz)
    d3 = abs(-0.5 * dx + 0.8660254037844386 * dz)
    return max(d1, d2, d3)


def _carve_crystal_point(blocks, rng, cx, cz, top_y, height, radius, lean_x, lean_z):
    """Carves one hexagonal amethyst crystal point growing down from
    (cx, cz, top_y): a straight hexagonal shaft at constant radius for
    (1 - TIP_FRAC) of its height, then narrowing in a hexagonal pyramid to
    a point over the last TIP_FRAC - the actual shape of a quartz/amethyst
    crystal, not a cone that tapers along its entire length. Drifts
    sideways by (lean_x, lean_z) per block of descent so points near a
    patch's edge can radiate outward instead of hanging dead-parallel."""
    tip_len = max(2, round(height * TIP_FRAC))
    shaft_len = max(1, height - tip_len)
    x, z = cx, cz
    for dl in range(height):
        y = top_y - dl
        if dl < shaft_len:
            r = radius
        else:
            t = (dl - shaft_len) / max(1, height - 1 - shaft_len)
            r = radius * (1 - t)
        in_tip = dl >= shaft_len
        ir = max(0, math.ceil(r))
        ix, iz = round(x), round(z)
        for dx in range(-ir, ir + 1):
            for dz in range(-ir, ir + 1):
                if _hex_radius(dx, dz) <= r + 1e-6:
                    if in_tip or rng.random() < 0.08:
                        block = "minecraft:amethyst_cluster"
                    else:
                        block = "minecraft:amethyst_block"
                    blocks[(ix + dx, y, iz + dz)] = block
        x += lean_x
        z += lean_z


def _crystal_patch(blocks, rng, cx0, cz0, floor_y):
    """Grows one dense crystal patch: many individual hexagonal points
    (_carve_crystal_point) scattered within a circular footprint, tallest
    near the middle and shorter toward the edge so the whole patch reads as
    one domed, radiating bouquet - plus a pale rind ring and druse speckle
    where it meets the surrounding rock, matching the reference photo's
    geode shell/base."""
    footprint = rng.uniform(*PATCH_FOOTPRINT_RANGE)
    max_height = rng.uniform(*PATCH_HEIGHT_RANGE)
    n_points = rng.randint(26, 44)

    for _ in range(n_points):
        angle = rng.uniform(0, 2 * math.pi)
        rad_frac = math.sqrt(rng.random())  # uniform over the disc
        rad = footprint * rad_frac
        px = cx0 + rad * math.cos(angle)
        pz = cz0 + rad * math.sin(angle)
        centrality = 1.0 - rad_frac  # 1.0 at the patch center, 0.0 at its rim

        height = max(5, round(max_height * (0.35 + 0.65 * centrality) * rng.uniform(0.85, 1.15)))
        radius = rng.uniform(*POINT_RADIUS_RANGE) * (0.7 + 0.3 * centrality)

        lean_mag = LEAN_STRENGTH * (1.0 - centrality) * rng.uniform(0.5, 1.0)
        if rad > 0.5:
            lean_x = (px - cx0) / rad * lean_mag
            lean_z = (pz - cz0) / rad * lean_mag
        else:
            lean_x = lean_z = 0.0

        _carve_crystal_point(blocks, rng, px, pz, floor_y, height, radius, lean_x, lean_z)

    # pale rind ring, like a geode's outer shell, marking where the patch
    # meets the plain rock floor around it
    for a in range(64):
        angle = a / 64 * 2 * math.pi
        for rr in (footprint * 0.92, footprint * 1.08, footprint * 1.22):
            bx = round(cx0 + rr * math.cos(angle))
            bz = round(cz0 + rr * math.sin(angle))
            if rng.random() < 0.8:
                blocks[(bx, floor_y, bz)] = RIND_BLOCK

    # druse: fine crystal fuzz filling the floor between the big points
    for _ in range(n_points * 2):
        angle = rng.uniform(0, 2 * math.pi)
        rad = footprint * math.sqrt(rng.random())
        bx, bz = round(cx0 + rad * math.cos(angle)), round(cz0 + rad * math.sin(angle))
        block = "minecraft:amethyst_cluster" if rng.random() < 0.5 else "minecraft:budding_amethyst"
        blocks.setdefault((bx, floor_y, bz), block)


def _flatten_floor(blocks, col_bottom, columns, rng):
    """Flattens the whole underside to one shallow, flat rock floor - the
    exposed matrix the crystal patches grow from. Like desert.py's mesa
    terracing, this only ever *removes* already-carved blocks and keeps
    col_bottom/columns in sync. Returns the floor_depth chosen."""
    floor_depth = rng.randint(*FLOOR_DEPTH_RANGE)
    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        if depth <= floor_depth:
            new_columns.append((x, z, topY, depth, r, localR))
            continue
        bottomY, _, _, _ = col_bottom[(x, z)]
        new_bottomY = topY - floor_depth
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)
        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, floor_depth, r, localR))
    columns[:] = new_columns
    return floor_depth


def _crystal_underside(blocks, col_bottom, columns, size, rng):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into a shallow rock floor with several dense hexagonal-
    crystal patches (see _crystal_patch) spread roughly evenly around the
    island, instead of the icicle-shaped drip skirt every other theme's
    underside uses.
    """
    floor_depth = _flatten_floor(blocks, col_bottom, columns, rng)
    approx_radius = max(1.0, (size - 6) / 2.0)

    n_patches = rng.randint(*PATCH_COUNT_RANGE)
    angle_offset = rng.uniform(0, 2 * math.pi)
    for i in range(n_patches):
        # one sector per patch, each with its own jitter, so patches spread
        # evenly around the island instead of clumping to one side
        angle = angle_offset + (i + rng.uniform(-0.25, 0.25)) * (2 * math.pi / n_patches)
        rfrac = rng.uniform(*PATCH_RADIUS_FRAC)
        tx = rfrac * approx_radius * math.cos(angle)
        tz = rfrac * approx_radius * math.sin(angle)
        nearest = min(columns, key=lambda c: (c[0] - tx) ** 2 + (c[1] - tz) ** 2)
        cx, cz, topY = nearest[0], nearest[1], nearest[2]
        _crystal_patch(blocks, rng, cx, cz, topY - floor_depth)


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one crystal-geode
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of purple-crust layers, before
                       the tuff/deepslate gradient starts.
    num_drips / drip_density - unused by this theme; the underside's
                       crystal patches are shaped by _crystal_underside
                       instead of common.generate_drips (kept only for
                       CLI/run_cli signature compatibility).
    decorate_top     - if True, scatters amethyst clusters and small
                       crystal-studded outcrops on top.
    decorate_underside - if True (default), grows the dense hexagonal
                       crystal patches on the underside; if False, the
                       underside is just the plain flattened rock floor.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    # a coarse per-column phase field so each column's veins snake through
    # depth on their own wavy schedule rather than forming perfect rings -
    # combined with a sine of y_offset, this traces actual vein bands of
    # crystal running through the bulk rock instead of independent random
    # single-voxel flecks, which is what made the geode read as "painted".
    vein_phase_noise = common.value_noise_2d(size, grid_for(3, 7), seed + 17)
    VEIN_THRESHOLD = 0.8

    def top_block(rng, x, z, xi, zi):
        return pick_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        vein_phase = math.sin(y_offset * 0.8 + vein_phase_noise[xi, zi] * 6.0)
        if vein_phase > VEIN_THRESHOLD:
            # solid amethyst so the vein reads as one clean seam, not a
            # speckled streak
            return "minecraft:amethyst_block"
        return pick_gradient(rng, t_grad, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    if decorate_underside:
        # break the underside open into a shallow rock floor with dense
        # hexagonal crystal patches growing out of it - see
        # _crystal_underside above. Deliberately does not reuse
        # common.generate_drips or any curved/round taper - see the module
        # docstring.
        _crystal_underside(blocks, col_bottom, columns, size, rng)
    else:
        _flatten_floor(blocks, col_bottom, columns, rng)

    if decorate_top:
        # sparse individual crystal florets on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.1:
                blocks.setdefault((x, topY + 1, z), "minecraft:amethyst_cluster")

        # a couple of small budding-amethyst outcrops, bristling with clusters
        outcrop_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(outcrop_spots)
        for (x, z, topY, depth, r, localR) in outcrop_spots[: rng.randint(0, 3)]:
            mound_h = rng.randint(1, 2)
            for dy in range(mound_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:budding_amethyst"
            top_y = topY + 1 + mound_h
            for dx in range(-1, 2):
                for dz in range(-1, 2):
                    if dx == 0 and dz == 0:
                        continue
                    if rng.random() < 0.6:
                        blocks.setdefault((x + dx, top_y, z + dz), "minecraft:amethyst_cluster")

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big crystal island plus satellites and floating rock/crystal debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:amethyst_block")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:purpur_block": "#a884b0",
    "minecraft:purpur_pillar": "#ab87b3",
    "minecraft:tuff": "#6d6a63",
    "minecraft:deepslate": "#393a3d",
    "minecraft:amethyst_block": "#8f5fd1",
    "minecraft:budding_amethyst": "#7c4fc0",
    "minecraft:amethyst_cluster": "#a875e0",
    "minecraft:calcite": "#e8e4d0",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a crystal-geode floating island for Minecraft.",
        out_default="crystal_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"crystal floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"crystal multi-island demo scene (seed={seed})",
        num_drips_help="unused by this theme - underside crystal clusters are shaped by "
                        "clumped noise instead, kept only for CLI compatibility",
        decorate_top_help="scatter amethyst clusters and outcrops on top (off by default)",
    )


if __name__ == "__main__":
    main()
