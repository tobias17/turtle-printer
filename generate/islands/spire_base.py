"""
Spire-Base Floating Island Generator for Minecraft
=====================================================

A deliberately plain, generic dark-stone island: no veins, no vines, no
drips, no top scatter - just a flat dark stone crust tapering down into a
slightly different dark stone underneath, using the same shared taper
shape every other theme uses. Exists purely as the base spire.py's tower
stands on (see generate/scene.py) - the platform shouldn't compete
visually with the tower sitting on it, so this is the plainest palette/
decoration of any theme in generate/islands/, not a themed island of its
own.

Shares its silhouette/taper machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies a minimal
two-block dark-stone gradient and skips every theme's usual optional
decoration (drips, rim vines, top scatter) entirely.

Usage:
    python spire_base.py --diameter 40
    python spire_base.py --diameter 40 --seed 7
"""

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# Plain dark stone, crust down through a slightly lighter dark stone at the
# core - just 2 solid bands, no fleck/dither, no veins: deliberately the
# least visually busy palette of any theme, so it reads as a neutral plinth.
GRADIENT = [
    "minecraft:deepslate",
    "minecraft:cobbled_deepslate",
]

# Callers (scene.py, rollup.py) size max_depth the same way for every theme
# - roughly diameter / 2 - but a plain flat plinth reads better a bit
# shallower than that shared default, so this theme trims its own
# max_depth locally rather than changing the shared convention.
DEPTH_FRAC = 0.8


def pick_gradient(rng, t):
    """Picks a block for depth-fraction t in [0, 1] (0 = right at the
    crust, 1 = deepest). No jitter/noise here on purpose - a razor-straight
    band edge is fine, this theme isn't meant to draw the eye."""
    n = len(GRADIENT)
    idx = int(round(min(max(t, 0.0), 1.0) * (n - 1)))
    return GRADIENT[idx]


def pick_crust(rng):
    """Top-crust block: solid dark stone, no fleck - a flat, plain platform."""
    return "minecraft:deepslate"


def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one plain dark-
    stone island, positioned with its center at `offset`. Uses the same
    shared silhouette/taper carve as every other theme, but deliberately
    skips all optional decoration - no drips, no rim vines, no top
    scatter - so the shape and palette stay as plain as possible.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of crust layers, before the
                       gradient starts.
    num_drips / drip_density / decorate_top / decorate_underside - unused
                       by this theme (kept only so its generate_island
                       shares the same CLI/run_cli signature every other
                       theme's does).
    """
    max_depth = max(1, round(max_depth * DEPTH_FRAC))
    size, half, radius = common.grid_dims(diameter)

    def top_block(rng, x, z, xi, zi):
        return pick_crust(rng)

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        if y_offset < thickness:
            return pick_crust(rng)
        t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
        return pick_gradient(rng, t_grad)

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One plain dark-stone island plus satellites and floating debris."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:deepslate")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:deepslate": "#393a3d",
    "minecraft:cobbled_deepslate": "#46474b",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a plain dark-stone base floating island for Minecraft.",
        out_default="spire_base_island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"spire-base floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"spire-base multi-island demo scene (seed={seed})",
        num_drips_help="unused by this theme - deliberately no drips, kept only for CLI compatibility",
        decorate_top_help="unused by this theme - deliberately no top decoration",
    )


if __name__ == "__main__":
    main()
