"""
Fungal Floating Island Generator for Minecraft
===================================================

A mycelium/swamp island variant: a mycelium crust on top, grading down
through dirt, coarse dirt and mud into the plain rock core every island
theme shares underneath. Giant mushrooms grow on top instead of trees; the
underside grows hanging mangrove-root tendrils tipped with the occasional
glowing shroomlight instead of rocky drips.

Shares its silhouette/taper/drip machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies the fungal-
specific block choices and decoration.

Usage:
    python mushroom.py --diameter 40
    python mushroom.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Mycelium crust over solid dirt "cap flesh" - kept to just these two so the
# cap underside reads as one clean fleshy mass; the stem is recolored
# separately (see _cap_and_stem) so it reads as an actual stem, not more cap.
GRADIENT = [
    "minecraft:mycelium",
    "minecraft:dirt",
]

STEM_BLOCK = "minecraft:mushroom_stem"


def pick_gradient(rng, t, jitter=0.0):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    mycelium crust, 1 = deepest rock). `jitter` (driven only by smooth
    per-column noise) nudges the whole column toward a neighboring shade so
    the band edge is wavy instead of a razor-straight ring, without
    per-voxel dithering."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    idx = int(round(min(max(pos, 0.0), n - 1)))
    return GRADIENT[idx]


def pick_mycelium_crust(rng):
    """Top-crust block: solid mycelium, no fleck - a flat platform."""
    return "minecraft:mycelium"


def _cap_and_stem(blocks, col_bottom, columns, rng, max_depth):
    """Post-processes the already-carved (unmodified common.carve_columns)
    underside into an actual mushroom silhouette - a wide, shallow cap
    underside (roughly constant depth regardless of radius, like the flat
    gill surface under a real mushroom cap) with a single thick stem plunging
    down from the center - instead of the smooth cone every theme starts
    from. The stem columns are also recolored solid `STEM_BLOCK` (the real
    white mushroom-stem block) so the stem reads as an actual stem instead
    of just deeper dirt.

    Like desert.py's mesa terracing, this only ever *removes* already-carved
    blocks and keeps col_bottom/columns in sync (drips/rim decoration read
    those for each column's true bottom), and is deliberately local to
    mushroom.py rather than a carve_columns option, so no other theme is
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


GILL_COUNT = 26  # number of radiating gill lines traced across the cap underside


def _gill_texture(blocks, col_bottom, columns):
    """Traces thin radiating gill lines (in STEM_BLOCK, the same white as
    the stem) across the flat cap underside carved by _cap_and_stem -
    real mushroom gills are thin plates radiating out from the stem to the
    rim, not the random scattered vines/drips every other theme's
    underside decoration produces. Only recolors the single exposed bottom
    face of each cap column, so it's a texture on the existing flat
    surface, not a shape change.
    """
    for (x, z, topY, depth, r, localR) in columns:
        frac = r / localR if localR else 1.0
        if frac < 0.18:
            continue  # stem region, no gills
        theta = math.atan2(z, x) % (2 * math.pi)
        bucket = theta / (2 * math.pi) * GILL_COUNT
        if abs(bucket - round(bucket)) < 0.14:
            bottomY, _, _, _ = col_bottom[(x, z)]
            blocks[(x, bottomY, z)] = STEM_BLOCK


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.04, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one fungal
    island, positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of mycelium-crust layers,
                       before the dirt/mud gradient starts.
    num_drips / drip_density - see grass.py; here each "drip" is a sparse
                       hanging root tendril, occasionally glow-tipped.
    decorate_top     - if True, scatters small mushrooms and grows a couple
                       of giant mushrooms on top.
    decorate_underside - a few root tendrils plus a light rim moss fringe.
                       On by default. The cap's radiating gill lines
                       (_gill_texture) always run - they're the cap's basic
                       underside texture, not optional decoration.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    def top_block(rng, x, z, xi, zi):
        return pick_mycelium_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_mycelium_crust(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad, jitter=g_jitter)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
        # a cap-like taper: stays close to full width just under the rim
        # (like a mushroom cap's flesh) then narrows quickly further down -
        # both existing carve_columns parameters, no shared code touched.
        taper_strength=0.9, taper_exponent=1.6,
    )
    # reshape the smooth cone into a flat cap + central stem (recolored solid
    # white) - see _cap_and_stem above.
    _cap_and_stem(blocks, col_bottom, columns, rng, max_depth)
    # trace radiating gill lines across the flat cap underside - see
    # _gill_texture above. Unconditional, like _cap_and_stem: this is the
    # cap's basic underside texture, not optional decoration on top of it.
    _gill_texture(blocks, col_bottom, columns)

    if decorate_underside:
        # a few root tendrils plunging from the stem base, with a rare
        # glowing shroomlight tip - kept sparse so they read as a handful of
        # roots reaching for the ground, not a scatter of random bits
        # competing with the gill lines.
        def drip_block(rng, t, is_tip):
            return "minecraft:shroomlight" if is_tip else "minecraft:muddy_mangrove_roots"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # a light moss fringe at the true rim - sparse, like the other
        # themes' vine/root fringes, not a dense curtain fighting the gills
        # for attention.
        common.decorate_rim_underside(
            rng, blocks, columns, col_bottom,
            rim_block_fn=lambda rng: "minecraft:vine",
            r_frac_threshold=0.55, chance=0.12, length_range=(2, 4),
        )

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
    return common.basic_scene(seed, generate_island, debris_block="minecraft:mud")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:mycelium": "#6f5a6e",
    "minecraft:dirt": "#6b4a2b",
    "minecraft:mushroom_stem": "#e8e0d0",
    "minecraft:muddy_mangrove_roots": "#4a3828",
    "minecraft:shroomlight": "#f0a030",
    "minecraft:vine": "#3f6b2a",
    "minecraft:red_mushroom": "#c03030",
    "minecraft:brown_mushroom": "#8a6a48",
    "minecraft:red_mushroom_block": "#a83232",
    "minecraft:brown_mushroom_block": "#9c7a52",
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
        num_drips_help=("number of hanging root tendrils (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter mushrooms and grow giant mushrooms on top (off by default)",
    )


if __name__ == "__main__":
    main()
