"""
Spire-Base Floating Island Generator for Minecraft
=====================================================

A deliberately plain, generic island: no veins, no vines, no drips, no
top scatter, no gradient - solid Thaumic Augmentation Void Stone
throughout, using the same shared taper shape every other theme uses.
Exists purely as the base spire.py's tower stands on (see
generate/scene.py) - the platform shouldn't compete visually with the
tower sitting on it, so this is the plainest palette/decoration of any
theme in generate/islands/, not a themed island of its own.

Shares its silhouette/taper machinery with the other island themes in
generate/islands/ (see common.py) - this file only supplies a single flat
void-stone block and skips every theme's usual optional decoration
(drips, rim vines, top scatter, depth gradient) entirely.

Usage:
    python spire_base.py --diameter 40
    python spire_base.py --diameter 40 --seed 7
"""

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

# One block, top to bottom - no gradient, no fleck: deliberately the least
# visually busy palette of any theme, so it reads as a neutral plinth.
BLOCK = "thaumicaugmentation:stone_void"

# Callers (scene.py, rollup.py) size max_depth the same way for every theme
# - roughly diameter / 2 - but a plain flat plinth reads better a bit
# shallower than that shared default, so this theme trims its own
# max_depth locally rather than changing the shared convention.
DEPTH_FRAC = 0.8


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
        return BLOCK

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        return BLOCK

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top, top_block, body_block,
    )

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """One plain black-concrete island plus satellites and floating debris."""
    return common.basic_scene(seed, generate_island, debris_block=BLOCK)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "thaumicaugmentation:stone_void": "#151020",
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
