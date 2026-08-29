"""
Crystal Geode Floating Island Generator for Minecraft
=========================================================

A crystal-cave island variant: pale calcite crust over neutral geode rock
(tuff, deepslate, smooth basalt), studded with amethyst growths breaking
through the top and hanging as crystal "icicles" off the underside instead
of the usual rocky root-drips. The amethyst is deliberately kept as sparse
decoration rather than bulk fill, so it reads as crystal growing out of
plain rock rather than the island being made of solid gemstone.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the crystal-
specific block choices and decoration.

Usage:
    python crystal.py --diameter 40
    python crystal.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Neutral geode-cave rock, pale at the surface and darkening with depth.
# Amethyst is handled separately (as the vein/spike/floor structural
# features below), not part of the bulk gradient - kept to 2 solid bands so
# the bulk rock reads as plain stone and the crystal reads as something
# growing THROUGH it, not speckled into it.
GRADIENT = [
    "minecraft:calcite",
    "minecraft:deepslate",
]


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    calcite crust, 1 = deepest rock). `jitter` (driven only by smooth
    per-column noise) nudges the whole column toward a neighboring shade so
    the band edge is wavy instead of a razor-straight ring, without
    per-voxel dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_calcite_crust(rng):
    """Top-crust block: solid calcite, no fleck - the crust is a flat platform."""
    return "minecraft:calcite"


SPIKE_RADIUS_FRAC = 0.3  # spikes only ever spawn this close to center


def _carve_geode_cavity(blocks, col_bottom, columns, rng, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside so the island reads as a broken-open geode - a wide, mostly
    flat crystal-lined floor - instead of a solid cone.

    A first attempt only flattened the central columns and left the outer
    ring's natural taper alone; that ring is *deeper* than the flattened
    center (the taper's natural depth peaks partway out, not at the very
    center), so it stood in front of the camera and hid the flattening
    completely. The fix: flatten almost every column to the same shallow
    floor depth, so there's no tall ring left anywhere to block the view of
    it - the whole underside reads as a flat crystal-studded floor. A
    handful of untouched central columns are left at their full natural
    (much deeper) depth to read as amethyst spikes still jutting down from
    that floor, like actual crystal points.

    Like desert.py's mesa terracing, this only ever *removes* already-carved
    blocks and keeps col_bottom/columns in sync (drips/rim decoration read
    those for each column's true bottom), and is deliberately local to
    crystal.py rather than a carve_columns option, so no other theme is
    affected.
    """
    floor_depth = max(6, int(max_depth * 0.3))

    candidates = [c for c in columns if (c[4] / c[5] if c[5] else 1.0) < SPIKE_RADIUS_FRAC]
    rng.shuffle(candidates)
    n_spikes = min(len(candidates), rng.randint(3, 6))
    spike_xy = {(c[0], c[1]) for c in candidates[:n_spikes]}

    new_columns = []
    for (x, z, topY, depth, r, localR) in columns:
        if (x, z) in spike_xy or depth <= floor_depth:
            new_columns.append((x, z, topY, depth, r, localR))
            continue
        bottomY, _, _, _ = col_bottom[(x, z)]
        new_bottomY = topY - floor_depth
        for y in range(bottomY, new_bottomY):
            blocks.pop((x, y, z), None)
        blocks[(x, new_bottomY, z)] = "minecraft:budding_amethyst"
        if rng.random() < 0.5:
            blocks[(x, new_bottomY + 1, z)] = "minecraft:amethyst_cluster"
        col_bottom[(x, z)] = (new_bottomY, topY, r, localR)
        new_columns.append((x, z, topY, floor_depth, r, localR))
    columns[:] = new_columns


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one crystal-geode
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of calcite-crust layers, before
                       the tuff/deepslate/basalt gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is an
                       amethyst crystal spike, not rock.
    decorate_top     - if True, scatters amethyst clusters and small
                       crystal-studded outcrops on top.
    decorate_underside - hanging amethyst spikes on the underside. On by
                       default.
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
        return pick_calcite_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_calcite_crust(rng)
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
    # scoop the central underside into a crystal-lined cavity - see
    # _carve_geode_cavity above.
    _carve_geode_cavity(blocks, col_bottom, columns, rng, max_depth)

    if decorate_underside:
        # crystal spikes are their own amethyst palette, distinct from the
        # neutral bulk rock - solid amethyst body, a cluster of "petals" at
        # the tip so it reads as a growing crystal rather than a rock icicle.
        def drip_block(rng, t, is_tip):
            return "minecraft:amethyst_cluster" if is_tip else "minecraft:amethyst_block"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # small bare crystal shards near the outer rim
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:amethyst_cluster",
            r_frac_threshold=0.55, chance=0.1, length_range=(1, 2),
        )

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
    "minecraft:calcite": "#e8e4d0",
    "minecraft:deepslate": "#393a3d",
    "minecraft:amethyst_block": "#8f5fd1",
    "minecraft:budding_amethyst": "#7c4fc0",
    "minecraft:amethyst_cluster": "#a875e0",
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
        num_drips_help=("number of hanging amethyst crystal spikes (default: auto-scales with "
                         "the island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter amethyst clusters and outcrops on top (off by default)",
    )


if __name__ == "__main__":
    main()
