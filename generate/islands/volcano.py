"""
Volcanic Floating Island Generator for Minecraft
=================================================

A volcanic-themed island variant: dark igneous stone instead of
grass/dirt/stone. The top crust is solid black (blackstone, with rare
obsidian flecks), then color gradually shifts to a darker grey with depth
- basalt, deepslate, cobbled deepslate, tuff - as you move down toward the
underside, with per-column/per-voxel noise so the banding isn't a
perfectly smooth gradient. Mostly pure stone-color grading, kept dark top
to bottom (no light greys or white stone), but with sparse glowing magma
veins running through the body and a slightly sharper underside taper than
grass.py's - a rocky mass still cooling from underneath, not just a
recolored copy of the same shape.
Meant to sit around spire.py's dark tower.

Shares its silhouette/taper/drip machinery with the other island themes
in generate/islands/ (see common.py) - this file only supplies the
volcanic-specific block choices and gradient logic.

Outputs (into --out-dir, default generate/out):
  1. A .npz Structure (block-index array + Atlas legend) in the same
     canonical format used by tree.py/grass.py - see generate/utils.py.
  2. A 3D preview image rendered as full shaded blocks so you can check
     the shape BEFORE building anything in-game.
  3. Optionally (--schem) a WorldEdit schematic, to see it live in a
     creative-mode save.

Usage:
    python volcano.py --diameter 40
    python volcano.py --diameter 40 --seed 7
"""

import math

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Dark-to-less-dark stone gradient, in order from the black crust down to
# the (still dark) grey found deep underneath / at drip tips. Deliberately
# stays in the black/dark-grey range - no light or white stone.
GRADIENT = [
    "minecraft:blackstone",
    "minecraft:deepslate",
    "minecraft:basalt",
    "minecraft:cobbled_deepslate",
    "minecraft:tuff",
]

OBSIDIAN_CHANCE = 0.025  # rare dark fleck, at any depth, for a bit of randomness


def pick_gradient(rng, t, jitter=0.0):
    """Picks a stone block for depth-fraction t in [0, 1] (0 = right at the
    black crust, 1 = deepest/lightest). `jitter` (in gradient-index units,
    can be negative) blends the pick toward a neighboring shade for
    per-column/per-voxel randomness instead of a perfectly smooth band."""
    n = len(GRADIENT)
    pos = min(max(t, 0.0), 1.0) * (n - 1) + jitter
    pos = min(max(pos, 0.0), n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    block = GRADIENT[hi] if rng.random() < frac else GRADIENT[lo]
    if rng.random() < OBSIDIAN_CHANCE:
        block = "minecraft:obsidian"
    return block


def pick_black(rng):
    """Top-crust / shallow-band block: solid black with a rare obsidian
    fleck for a touch of randomness."""
    return "minecraft:obsidian" if rng.random() < 0.04 else "minecraft:blackstone"


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one volcanic
    island, positioned with its center at `offset`. Same silhouette/taper/
    drip machinery as the other island themes, but re-themed: solid black
    crust on top, gradually lightening (but staying dark) stone body as
    depth increases, and dark root-drips on the underside.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of crust layers, forced solid
                       black, before the color gradient starts. Varies
                       smoothly across the island.
    num_drips / drip_density - see grass.py; same auto-scaling behavior.
    decorate_top     - if True, scatters small basalt columns on top. Off
                       by default so the surface stays buildable.
    decorate_underside - hanging root drips on the rock underside. On by
                       default.
    """
    size, half, radius = common.grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    # per-column offset (in gradient-index units) so the dark->light
    # transition isn't a perfectly smooth function of depth alone - a
    # coarse field for broad blotches plus a finer one for speckle
    gradient_noise = common.value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = common.value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    # a per-column vein-phase field, same trick as crystal.py's amethyst
    # veins: combined with a sine of y_offset it traces wavy seams of magma
    # through the bulk rock (a still-cooling volcano) instead of independent
    # single-voxel flecks.
    lava_vein_noise = common.value_noise_2d(size, grid_for(3, 7), seed + 23)
    LAVA_VEIN_THRESHOLD = 0.93

    def top_block(rng, x, z, xi, zi):
        return pick_black(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_black(rng)
        g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        vein_phase = math.sin(y_offset * 0.6 + lava_vein_noise[xi, zi] * 5.0)
        if vein_phase > LAVA_VEIN_THRESHOLD:
            return "minecraft:magma_block"
        return pick_gradient(rng, t_grad, jitter=g_jitter + rng.uniform(-0.9, 0.9))

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
        # a bit sharper/more concave than grass.py's default taper (both
        # pre-existing carve_columns parameters, no shared code touched) -
        # reads as a rockier, more pointed mass instead of the same rounded
        # dome shape.
        taper_strength=0.9, taper_exponent=0.5,
    )

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            # drips hang below the island's own deepest point, so they sit
            # at the pale end of the gradient, with the usual randomness
            return pick_gradient(rng, 0.8 + 0.2 * t, jitter=rng.uniform(-0.6, 0.6))

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block)

        # a few bare hanging dark "icicles" near the outer rim (replaces
        # grass.py's draped vines)
        common.decorate_rim_underside(rng, blocks, columns, col_bottom,
                                       rim_block_fn=lambda rng: pick_gradient(rng, 0.9),
                                       r_frac_threshold=0.55, chance=0.12, length_range=(1, 3))

    if decorate_top:
        # a couple of small basalt columns (replaces grass.py's trees)
        column_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(column_spots)
        for (x, z, topY, depth, r, localR) in column_spots[: rng.randint(0, 2)]:
            col_h = rng.randint(2, 4)
            for dy in range(col_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:polished_basalt"

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """Ring of volcanic islands plus a couple of floating debris chunks,
    meant to sit around a central spire."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:blackstone")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:blackstone": "#2b2626",
    "minecraft:obsidian": "#161022",
    "minecraft:deepslate": "#393a3d",
    "minecraft:basalt": "#4a484c",
    "minecraft:polished_basalt": "#5a5760",
    "minecraft:cobbled_deepslate": "#55565a",
    "minecraft:tuff": "#6a6b64",
    "minecraft:magma_block": "#c9591a",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a volcanic floating island for Minecraft.",
        out_default="volcano_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"volcanic floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"volcanic multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging basalt drips (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter small basalt columns on top (off by default)",
    )


if __name__ == "__main__":
    main()
