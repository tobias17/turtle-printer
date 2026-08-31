"""
Crystal Geode Floating Island Generator for Minecraft
=========================================================

A crystal-cave island variant, built to match a real geode photo rather
than reusing this project's usual dripstone-shaped underside: the whole
underside is ONE dense crystal MASS spanning nearly the entire island - the
reference geode photo itself, scaled up to the island's diameter and
flipped upside down (the rock matrix on top, the crystal fan hanging
point-down below it), not a normal island with a few small crystal patches
bolted on. The mass is many individual hexagonal crystal points - a
straight-sided shaft topped with a hexagonal pyramid point, not a cone that
tapers along its whole length - packed edge to edge over a jittered hex
lattice, tallest near the center and shorter/leaning outward toward the
rim. Deliberately a consolidated two-block palette: solid purpur for the
whole rock platform, solid purple stained glass for every crystal point,
nothing else.
See _crystal_mass/_carve_crystal_point below for the shape itself; only the
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

# Consolidated two-block palette: solid purpur for the whole rock platform
# (top crust and body alike, no gradient/vein/fleck), solid purple stained
# glass for every crystal point in the underside mass (see
# _carve_crystal_point) - nothing else is used anywhere in this theme.
BLOCK = "minecraft:purpur_block"
CRYSTAL_BLOCK = "minecraft:purple_stained_glass"


def pick_crust(rng):
    """Top-crust/body block: solid purpur, no fleck - the whole rock mass is
    this one block."""
    return BLOCK


# ---------------------------------------------------------------------------
# Underside: a shallow rock floor with one dense hexagonal-crystal mass
# ---------------------------------------------------------------------------
#
# Built from scratch off the reference geode photo, not by reusing/tuning
# this project's dripstone-drip machinery:
#   1. A shallow flat rock floor - the exposed matrix a real geode splits
#      open along.
#   2. ONE dense crystal MASS covering nearly the whole floor - the
#      reference photo's entire crystal fan, scaled to the island and
#      flipped upside down, not a handful of small patches. It's many
#      individual hexagonal crystal points (see _carve_crystal_point)
#      packed edge to edge over a jittered hex lattice, tallest near the
#      mass's center and shorter toward its (irregular, noise-warped) rim,
#      each leaning outward the further it is from center - together
#      that's what makes it read as one huge radiating bouquet instead of
#      a forest of parallel rods.
#   3. A pale stone "rind" ring around the mass plus fine druse speckle at
#      the crystals' bases, where the reference photo's crystals meet the
#      surrounding rock.

FLOOR_DEPTH_RANGE = (5, 7)          # the flat rock floor the crystal mass grows from

MASS_FOOTPRINT_FRAC = (0.80, 0.94)  # crystal mass radius, as a fraction of the island's radius
MASS_OUTLINE_AMP = 0.12             # +/- fractional wobble in the mass's outline per angle
# A real amethyst point's shaft radius, as a fraction of the island's diameter - scaled off the
# island rather than fixed, so bigger islands grow chunkier, more clearly-faceted crystals instead
# of the same tiny points just packed in denser. Clamped to POINT_RADIUS_MIN/MAX so this stays a
# handful of large, individually-readable crystals rather than a fuzz of tiny ones (the previous,
# too-dense look) at either end of the size range.
POINT_RADIUS_FRAC = (0.022, 0.05)
POINT_RADIUS_MIN = 2.2
POINT_RADIUS_MAX = 7.0
# A crystal's height as a multiple of its own width (2x radius) - real quartz/amethyst points read
# as a stout hexagonal prism, not a thin needle, so this stays a modest multiple instead of scaling
# height off the island independently of how thick the point actually is.
HEIGHT_TO_WIDTH_RANGE = (3.5, 6.0)
# Target center-to-center spacing between points, as a multiple of their radius - the main knob for
# "how many crystals": wide spacing means fewer, clearly separate points instead of a packed hedge.
POINT_SPACING_FACTOR = 2.6
TIP_FRAC = 0.4                      # fraction of a point's height spent narrowing to its tip
LEAN_STRENGTH = 0.6                 # max sideways drift per block of height, at the mass's outer edge


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
    """Carves one hexagonal purple-glass crystal point growing down from
    (cx, cz, top_y): a straight hexagonal shaft at constant radius for
    (1 - TIP_FRAC) of its height, then narrowing in a hexagonal pyramid to
    a point over the last TIP_FRAC - the actual shape of a quartz/amethyst
    crystal, not a cone that tapers along its entire length. Drifts
    sideways by (lean_x, lean_z) per block of descent so points near a
    patch's edge can radiate outward instead of hanging dead-parallel.
    Solid CRYSTAL_BLOCK throughout - no shaft/tip material distinction."""
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
        ir = max(0, math.ceil(r))
        ix, iz = round(x), round(z)
        for dx in range(-ir, ir + 1):
            for dz in range(-ir, ir + 1):
                if _hex_radius(dx, dz) <= r + 1e-6:
                    blocks[(ix + dx, y, iz + dz)] = CRYSTAL_BLOCK
        x += lean_x
        z += lean_z


def _outline_fn(rng, base_radius, amp, n_harmonics=3):
    """Returns a callable theta -> radius tracing an irregular, lumpy
    outline around `base_radius` (a few random sine harmonics, like
    common.carve_columns' own island silhouette) - used so the crystal
    mass's own rim is organically warped instead of a perfect circle,
    matching the reference photo's ragged crystal crown."""
    harmonics = [(rng.randint(2, 5), rng.uniform(0, 2 * math.pi)) for _ in range(n_harmonics)]

    def outline(theta):
        r = base_radius
        for k, phase in harmonics:
            r *= 1 + (amp / n_harmonics) * math.sin(k * theta + phase)
        return r

    return outline


def _crystal_mass(blocks, rng, size, half, diameter, col_bottom):
    """Grows ONE dense crystal mass spanning nearly the whole underside:
    many individual hexagonal points (_carve_crystal_point), each solid
    CRYSTAL_BLOCK, packed edge to edge over a jittered hex lattice within an
    irregular (_outline_fn) footprint, tallest near the island's center and
    shorter/leaning outward toward the rim - this is the reference geode
    photo's entire crystal fan, not a small bolted-on patch.

    Each point attaches at its own column's actual floor height (read
    straight from col_bottom, already flattened by _flatten_floor), so the
    mass follows the floor's natural unevenness near the island's ragged
    edge instead of assuming one constant floor level.
    """
    approx_radius = max(1.0, (size - 6) / 2.0)
    footprint = approx_radius * rng.uniform(*MASS_FOOTPRINT_FRAC)
    outline = _outline_fn(rng, footprint, MASS_OUTLINE_AMP)
    base_radius = min(POINT_RADIUS_MAX, max(POINT_RADIUS_MIN, diameter * rng.uniform(*POINT_RADIUS_FRAC)))
    point_spacing = base_radius * POINT_SPACING_FACTOR
    height_noise = common.value_noise_2d(size, max(6, size // 10), rng.randint(0, 1_000_000))

    def floor_y_at(px, pz):
        key = (round(px), round(pz))
        entry = col_bottom.get(key)
        if entry is not None:
            return entry[0]
        for rr in range(1, 4):
            for ddx in range(-rr, rr + 1):
                for ddz in range(-rr, rr + 1):
                    if max(abs(ddx), abs(ddz)) != rr:
                        continue
                    entry = col_bottom.get((key[0] + ddx, key[1] + ddz))
                    if entry is not None:
                        return entry[0]
        return None

    # Jittered hex lattice over the footprint disc: tiles it evenly with far
    # fewer points than random sampling would need for full coverage, then
    # each point is trimmed to (and shaded by its distance within) the
    # actual irregular outline.
    row_h = point_spacing * 0.8660254037844386
    n_rows = int(2 * (footprint * (1 + MASS_OUTLINE_AMP)) / row_h) + 2
    n_cols = int(2 * (footprint * (1 + MASS_OUTLINE_AMP)) / point_spacing) + 2
    jitter_mag = point_spacing * 0.3

    n_placed = 0
    for ri in range(-n_rows // 2, n_rows // 2 + 1):
        pz0 = ri * row_h
        row_offset = (point_spacing / 2) if ri % 2 else 0.0
        for ci in range(-n_cols // 2, n_cols // 2 + 1):
            px0 = ci * point_spacing + row_offset
            px = px0 + rng.uniform(-jitter_mag, jitter_mag)
            pz = pz0 + rng.uniform(-jitter_mag, jitter_mag)

            rad = math.hypot(px, pz)
            theta = math.atan2(pz, px)
            local_footprint = outline(theta)
            if rad > local_footprint:
                continue

            floor_y = floor_y_at(px, pz)
            if floor_y is None:
                continue

            xi = min(max(round(px) + half, 0), size - 1)
            zi = min(max(round(pz) + half, 0), size - 1)
            n = 0.5 + 0.5 * height_noise[xi, zi]  # smooth per-region variation, 0..1
            centrality = 1.0 - rad / max(local_footprint, 1e-6)

            # Radius first (real crystals vary noticeably in girth too, not just height),
            # then height as a proportional multiple of that radius - keeps every point looking
            # like a normal stout crystal prism instead of a thin needle, whatever size it lands at.
            radius = base_radius * (0.6 + 0.5 * centrality) * rng.uniform(0.75, 1.25)
            aspect = rng.uniform(*HEIGHT_TO_WIDTH_RANGE)
            height = max(5, round(
                radius * 2 * aspect * (0.55 + 0.45 * centrality + 0.3 * n)
            ))

            lean_mag = LEAN_STRENGTH * (1.0 - centrality) * rng.uniform(0.6, 1.0)
            if rad > 0.5:
                lean_x = px / rad * lean_mag
                lean_z = pz / rad * lean_mag
            else:
                lean_x = lean_z = 0.0

            _carve_crystal_point(blocks, rng, px, pz, floor_y, height, radius, lean_x, lean_z)
            n_placed += 1


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


def _crystal_underside(blocks, col_bottom, columns, size, half, diameter, rng):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into a shallow rock floor with one dense hexagonal-crystal
    mass covering nearly all of it (see _crystal_mass), instead of the
    icicle-shaped drip skirt every other theme's underside uses.
    """
    _flatten_floor(blocks, col_bottom, columns, rng)
    _crystal_mass(blocks, rng, size, half, diameter, col_bottom)


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one crystal-geode
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of purple-crust layers, before
                       the body - kept only for CLI/run_cli signature
                       compatibility; the whole rock mass is solid BLOCK
                       regardless of depth.
    num_drips / drip_density - unused by this theme; the underside's
                       crystal patches are shaped by _crystal_underside
                       instead of common.generate_drips (kept only for
                       CLI/run_cli signature compatibility).
    decorate_top     - if True, scatters small purple-glass crystal florets and
                       outcrops on top.
    decorate_underside - if True (default), grows the dense hexagonal
                       crystal patches on the underside; if False, the
                       underside is just the plain flattened rock floor.
    """
    size, half, radius = common.grid_dims(diameter)

    def top_block(rng, x, z, xi, zi):
        return pick_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        return pick_crust(rng)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )
    if decorate_underside:
        # break the underside open into a shallow rock floor with one dense
        # hexagonal crystal mass growing out of it - see _crystal_underside
        # above. Deliberately does not reuse common.generate_drips or any
        # curved/round taper - see the module docstring.
        _crystal_underside(blocks, col_bottom, columns, size, half, diameter, rng)
    else:
        _flatten_floor(blocks, col_bottom, columns, rng)

    if decorate_top:
        # sparse individual purple-glass crystal florets on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.1:
                blocks.setdefault((x, topY + 1, z), CRYSTAL_BLOCK)

        # a couple of small glass outcrops
        outcrop_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(outcrop_spots)
        for (x, z, topY, depth, r, localR) in outcrop_spots[: rng.randint(0, 3)]:
            mound_h = rng.randint(1, 2)
            for dy in range(mound_h):
                blocks[(x, topY + 1 + dy, z)] = CRYSTAL_BLOCK
            top_y = topY + 1 + mound_h
            for dx in range(-1, 2):
                for dz in range(-1, 2):
                    if dx == 0 and dz == 0:
                        continue
                    if rng.random() < 0.6:
                        blocks.setdefault((x + dx, top_y, z + dz), CRYSTAL_BLOCK)

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One big crystal island plus satellites and floating glass/purpur debris."""
    return common.basic_scene(seed, generate_island, debris_block=CRYSTAL_BLOCK)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:purpur_block": "#a884b0",
    "minecraft:purple_stained_glass": "#8f5fd1",
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
        decorate_top_help="scatter small glass crystal florets and outcrops on top (off by default)",
    )


if __name__ == "__main__":
    main()
