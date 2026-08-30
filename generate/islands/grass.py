"""
Floating Island Generator for Minecraft (grass / stone / nature theme)
=========================================================================

Procedurally generates floating rock islands (irregular grassy top,
tapering rocky underside, hanging "root" stalactites, moss/vine
decoration) in the style of concept-art floating islands.

This is the original nature-themed island. It now lives alongside other
biome variants in generate/islands/ (see volcano.py, snow.py, desert.py,
crystal.py, mushroom.py) - the shared silhouette/taper/drip machinery is
factored out into generate/islands/common.py; this file only supplies the
grass/stone/tree-specific block choices and decoration.

Outputs (into --out-dir, default generate/output/tmp):
  1. A .npz Structure (block-index array + Atlas legend) in the same
     canonical format used by tree.py - see generate/utils.py.
  2. A 3D preview image rendered as full shaded blocks so you can check
     the shape BEFORE building anything in-game.
  3. Optionally (--schem) a WorldEdit schematic, to see it live in a
     creative-mode save.

No external world/game connection is needed to preview - this is pure
geometry + a plotting library.

Usage:
    python grass.py --diameter 40           # single island, flat 40-block-wide top
    python grass.py --diameter 40 --seed 7  # different random variation, same size
    python grass.py --scene                 # old multi-island demo composition

By default the island has a perfectly FLAT top (single Y level) so it's
easy to build on, but the outline is irregular (not a perfect circle) and
the underside tapers down into rock with hanging root/stalactite drips.
"""

import common

# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

def generate_island(seed=0, diameter=40, top_thickness_range=(4, 6), max_depth=14,
                     num_drips=None, drip_density=0.05, flat_top=True, decorate_top=False,
                     decorate_underside=True, offset=(0, 0, 0)):
    """Returns dict {(x, y, z): "minecraft:block_id"} for one island,
    positioned with its center at `offset`.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level, so you get a clean buildable circle. The
                       OUTLINE is still irregular (not a perfect circle) so
                       it reads as natural rock rather than a disc.
    top_thickness_range - (min, max) number of grass+dirt layers. Varies
                       smoothly across the island (via noise) rather than
                       being a constant, so the grass/dirt boundary looks
                       natural instead of a perfectly flat band.
    num_drips       - number of hanging root/stalactite drips. If None
                       (default), the count is derived from the island's
                       own rim geometry via `drip_density` rather than any
                       diameter formula, so it scales automatically at any
                       size. Pass an explicit int to override.
    drip_density     - fraction of eligible rim columns that grow a drip
                       (only used when num_drips is None). Individual drip
                       length/thickness are randomized per-drip (each gets
                       its own cap, scaled off max_depth), so drips vary in
                       size instead of clustering near one shared maximum.
    decorate_top     - if True, scatters grass/flowers/trees on top. Off by
                       default so the surface stays clear to build on.
    decorate_underside - hanging root drips + vines + moss on the rock
                       underside. On by default for the floating-island look;
                       doesn't affect the top surface at all.
    """
    def top_block(rng, x, z, xi, zi):
        return "minecraft:grass_block"

    def body_block(rng, x, z, xi, zi, y_offset, thickness, total_depth):
        return "minecraft:dirt" if y_offset < thickness else "minecraft:stone"

    def bottom_face(rng, blocks, x, z, bottomY, r, localR):
        # occasional moss cap on the very bottom face near the edge
        if r / localR > 0.65 and rng.random() < 0.35:
            blocks[(x, bottomY, z)] = "minecraft:mossy_cobblestone"

    blocks, col_bottom, columns, rng, size, half, radius = common.carve_columns(
        seed, diameter, top_thickness_range, max_depth, flat_top,
        top_block, body_block, bottom_face_fn=bottom_face,
        # a touch gentler/rounder than volcano.py's sharper, more concave
        # taper (both pre-existing carve_columns parameters, no shared code
        # touched) - reads as a softer earthy mound instead of the same
        # pointed rocky mass.
        taper_strength=0.8, taper_exponent=0.75,
    )

    if decorate_underside:
        def drip_block(rng, t, is_tip):
            return "minecraft:mossy_cobblestone" if is_tip else "minecraft:stone"

        def after_drip(rng, blocks, x, tip_y, z):
            if rng.random() < 0.6:
                blocks[(x, tip_y, z)] = "minecraft:vine"

        common.generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                               num_drips, drip_density, drip_block, after_drip_fn=after_drip)

        # vines draped down from the underside near the outer rim
        common.decorate_rim_underside(rng, blocks, columns, col_bottom,
                                       rim_block_fn=lambda rng: "minecraft:vine",
                                       r_frac_threshold=0.55, chance=0.18, length_range=(2, 6))

    if decorate_top:
        # sparse grass/flower decoration on the top surface
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR < 0.9 and rng.random() < 0.12:
                block = rng.choice(
                    ["minecraft:short_grass", "minecraft:short_grass",
                     "minecraft:fern", "minecraft:poppy", "minecraft:dandelion"]
                )
                blocks.setdefault((x, topY + 1, z), block)

        # a couple of small trees
        tree_spots = [c for c in columns if c[4] / c[5] < 0.55]
        rng.shuffle(tree_spots)
        for (x, z, topY, depth, r, localR) in tree_spots[: rng.randint(0, 2)]:
            trunk_h = rng.randint(3, 5)
            for dy in range(trunk_h):
                blocks[(x, topY + 1 + dy, z)] = "minecraft:oak_log"
            leaf_y = topY + 1 + trunk_h
            for dx in range(-2, 3):
                for dz in range(-2, 3):
                    for dy in range(0, 3):
                        if dx * dx + dz * dz + dy * dy <= 5 and rng.random() < 0.85:
                            blocks.setdefault((x + dx, leaf_y + dy, z + dz), "minecraft:oak_leaves")

    # apply world offset
    ox, oy, oz = offset
    return {(x + ox, y + oy, z + oz): b for (x, y, z), b in blocks.items()}


def generate_scene(seed=0):
    """Builds one big island plus several smaller satellite islands and
    floating debris chunks, echoing the reference composition."""
    return common.basic_scene(seed, generate_island, debris_block="minecraft:stone")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

BLOCK_COLORS = {
    "minecraft:grass_block": "#5b8a3a",
    "minecraft:dirt": "#6b4a2b",
    "minecraft:stone": "#8a8a8a",
    "minecraft:andesite": "#a3a3a0",
    "minecraft:mossy_cobblestone": "#5e6b4a",
    "minecraft:vine": "#3f6b2a",
    "minecraft:oak_log": "#5a3d1f",
    "minecraft:oak_leaves": "#3f7a2f",
    "minecraft:short_grass": "#6fae3f",
    "minecraft:fern": "#4f8f3f",
    "minecraft:poppy": "#c0392b",
    "minecraft:dandelion": "#e8c93a",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    common.run_cli(
        description="Generate a floating island for Minecraft.",
        out_default="island",
        generate_island_fn=generate_island,
        generate_scene_fn=generate_scene,
        block_colors=BLOCK_COLORS,
        single_title_fn=lambda diameter, seed: f"floating island (d={diameter}, seed={seed})",
        scene_title_fn=lambda seed: f"multi-island demo scene (seed={seed})",
        num_drips_help=("number of hanging root/stalactite drips (default: auto-scales with the "
                         "island's rim geometry - see --drip-density)"),
        decorate_top_help="scatter grass/flowers/trees on top (off by default so it stays buildable)",
    )


if __name__ == "__main__":
    main()
