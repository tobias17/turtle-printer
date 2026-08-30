"""
Tiny Test Scene Composer
==========================
A stripped-down, fast-to-generate cousin of scene.py: a center island
(spire_base themed, ~20 diameter) topped with a small placeholder tower,
plus 3 small islands (~20 diameter, SATELLITE_THEMES below - grass, snow,
mesa) packed tightly around it - same "closest legal spot, spread apart by
top color" placement rule scene.py uses (see _place_closest below), just
with much smaller constants so the whole cluster stays tiny.

The center tower is deliberately NOT spire.py's Sauron spire: that
generator has no size knob (its ~150-block-tall tiered profile, floor
spacing, crown geometry etc. are all fixed module-level constants sized
for a full island cluster) and its ~43-block base would swallow a
20-diameter island whole. This is instead a plain tapering blackstone
spike with a small wool accent on top - a placeholder that marks "this is
where the spire goes" without pretending to be the real thing.

Height is a simple per-island random jitter (small, capped by
HEIGHT_FRAC_MAX) rather than scene.py's smooth 2D noise field - with only
4 islands total there's nothing for a "flow across the cluster" to read
against, so the extra machinery isn't worth it here.

Outputs (into --out-dir, default generate/output):
    <out>.npz    canonical Structure (numpy voxel array + Atlas)
    <out>.png    preview render, isometric | top-down
    <out>.schem  WorldEdit schematic (only with --schem, if mcschematic is
                 installed)

generate/output/scene_tiny.png is the STANDARD location to look at this
scene - running the script with no arguments always (re)writes exactly
that path. Point --out/--out-dir at a scratch location (e.g.
generate/output/tmp/) for throwaway experiments instead of overwriting it.

Usage:
    python generate/scene_tiny.py                # generate with the default seed
    python generate/scene_tiny.py --seed 7        # different random layout
"""

import argparse
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))               # utils.py, scene.py
sys.path.insert(0, str(HERE / "islands"))   # common.py + theme modules

from utils import render_screenshot  # noqa: E402
import spire_base  # noqa: E402
import common  # noqa: E402
import grass, volcano, snow, desert, mesa, mushroom, bones  # noqa: E402
import crystal, coral, ruins, swamp, prismarine, hive  # noqa: E402
from scene import _compose_views  # noqa: E402 - reuse the isometric|top-down layout helper

THEME_MODULES = {
    "grass": grass, "volcano": volcano, "snow": snow, "desert": desert, "mesa": mesa,
    "mushroom": mushroom, "bones": bones, "crystal": crystal, "coral": coral,
    "ruins": ruins, "swamp": swamp, "prismarine": prismarine, "hive": hive,
}
ALL_THEMES = list(THEME_MODULES)
HOST_MODULE = spire_base

TOP_BLOCK = {
    "grass": "minecraft:grass_block", "volcano": "minecraft:blackstone",
    "snow": "minecraft:snow_block", "desert": "minecraft:sand", "mesa": "minecraft:red_sand",
    "mushroom": "minecraft:mycelium", "bones": "minecraft:bone_block",
    "crystal": "minecraft:purpur_block", "coral": "minecraft:sand",
    "ruins": "minecraft:moss_block", "swamp": "minecraft:mud",
    "prismarine": "minecraft:prismarine_bricks", "hive": "minecraft:honeycomb_block",
}
HOST_TOP_COLOR = spire_base.BLOCK_COLORS["minecraft:deepslate"]

SATELLITE_THEMES = ["grass", "snow", "mesa"]
DIAMETER_RANGE = (18, 22)
GAP = 4  # minimum clear void every pair of islands (host included) must keep between their footprints

RADIUS_SEARCH_STEP = 2      # how far the search radius grows per failed sweep of _place_closest
ANGLE_SAMPLES_PER_STEP = 32  # random angles probed at each search radius

HEIGHT_FRAC_MAX = 0.3  # each satellite lands between 0 and this fraction of the tower's height above the host top

TOWER_HEIGHT = 14
TOWER_BASE_R = 4.0
TOWER_TOP_R = 1.2
TOWER_BLOCK = "minecraft:blackstone"
TOWER_ACCENT = "minecraft:orange_wool"

TOWER_BLOCK_COLORS = {
    "minecraft:blackstone": "#2b2530",   # matches spire.py's own palette
    "minecraft:orange_wool": "#d2691e",
}


def build_placeholder_tower(seed):
    """A plain tapering column (base radius TOWER_BASE_R -> top radius
    TOWER_TOP_R over TOWER_HEIGHT blocks) with four small corner nubs near
    the top and a wool accent orb - a light nod to the real spire's crown
    claws and eye, without any of its geometry. Centered at (0, *, 0), flat
    base at y=0. Returns (blocks, top_y) where top_y is the height of the
    accent orb, for offset/height-budget math."""
    rng = random.Random(seed)
    blocks = {}
    for y in range(TOWER_HEIGHT):
        t = y / max(1, TOWER_HEIGHT - 1)
        r = TOWER_BASE_R * (1 - t) + TOWER_TOP_R * t
        ir = int(math.ceil(r))
        for x in range(-ir, ir + 1):
            for z in range(-ir, ir + 1):
                if math.hypot(x, z) <= r + 1e-9:
                    blocks[(x, y, z)] = TOWER_BLOCK

    nub_y = TOWER_HEIGHT - 2
    nub_r = TOWER_TOP_R + 1.0
    for ang in (0, 90, 180, 270):
        rad = math.radians(ang + rng.uniform(-5, 5))
        nx, nz = round(nub_r * math.cos(rad)), round(nub_r * math.sin(rad))
        blocks[(nx, nub_y, nz)] = TOWER_BLOCK
        blocks[(nx, nub_y + 1, nz)] = TOWER_BLOCK

    blocks[(0, TOWER_HEIGHT, 0)] = TOWER_ACCENT
    return blocks, TOWER_HEIGHT


# ---------------------------------------------------------------------------
# Closest-legal-spot placement, spread apart by top color - same rule
# scene.py uses (see its _place_closest for the full rationale), just with
# this module's own (much smaller) GAP/search constants.
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _color_dist(hex_a, hex_b):
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    return math.sqrt((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2)


def _color_similarity(hex_a, hex_b):
    return 1.0 / (_color_dist(hex_a, hex_b) + 1.0)


def _place_closest(rng, radius_extent, color, placed):
    """`placed` entries are (x, z, radius_extent, color_hex). Returns
    (x, z, angle, dist)."""
    dist = radius_extent + GAP + max(pr for _, _, pr, _ in placed)
    while True:
        candidates = []
        for _ in range(ANGLE_SAMPLES_PER_STEP):
            angle = rng.uniform(0, 360)
            x, z = dist * math.cos(math.radians(angle)), dist * math.sin(math.radians(angle))
            if all(math.hypot(x - px, z - pz) >= radius_extent + pr + GAP for px, pz, pr, _ in placed):
                candidates.append((x, z, angle))
        if candidates:
            def color_badness(candidate):
                cx, cz, _ = candidate
                return sum(
                    _color_similarity(color, pc) / max(1.0, math.hypot(cx - px, cz - pz))
                    for px, pz, _, pc in placed
                )
            return min(candidates, key=color_badness) + (dist,)
        dist += RADIUS_SEARCH_STEP


# ---------------------------------------------------------------------------
# Scene assembly
# ---------------------------------------------------------------------------

def build_scene(seed=1):
    rng = random.Random(seed)
    blocks = {}
    placed = []  # (x, z, radius_extent, top_color) for every island placed so far, host included

    top_colors = {theme: THEME_MODULES[theme].BLOCK_COLORS[TOP_BLOCK[theme]] for theme in ALL_THEMES}

    host_diameter = round(rng.uniform(*DIAMETER_RANGE))
    host_max_depth = max(4, host_diameter // 2)
    blocks.update(HOST_MODULE.generate_island(
        seed=seed, diameter=host_diameter, max_depth=host_max_depth,
        decorate_top=False, decorate_underside=True, offset=(0, 0, 0),
    ))
    placed.append((0.0, 0.0, host_diameter / 2.0, HOST_TOP_COLOR))
    print(f"host island (spire_base): d={host_diameter}")

    tower_blocks, tower_top_y = build_placeholder_tower(seed)
    tower_offset = (0, 1, 0)  # host top surface is topY=0, so the buildable surface is y=1
    blocks.update({(x + tower_offset[0], y + tower_offset[1], z + tower_offset[2]): b
                   for (x, y, z), b in tower_blocks.items()})
    print(f"placeholder tower: height={tower_top_y}")

    height_lo = tower_offset[1]
    height_span = tower_top_y * HEIGHT_FRAC_MAX

    for i, theme in enumerate(SATELLITE_THEMES):
        module = THEME_MODULES[theme]
        diameter = round(rng.uniform(*DIAMETER_RANGE))
        radius_extent = diameter / 2.0

        x, z, angle, dist = _place_closest(rng, radius_extent, top_colors[theme], placed)

        placed.append((x, z, radius_extent, top_colors[theme]))
        y = round(height_lo + rng.uniform(0, height_span))
        offset = (round(x), y, round(z))
        max_depth = max(4, diameter // 2)

        island_blocks = module.generate_island(
            seed=seed * 1000 + i + 1, diameter=diameter, max_depth=max_depth,
            decorate_top=False, decorate_underside=True, offset=offset,
        )
        blocks.update(island_blocks)
        print(f"  {theme:<10} d={diameter:<4} pos=({offset[0]:>4}, {offset[1]:>3}, {offset[2]:>4})  "
              f"dist={dist:.0f} angle={angle:.0f}deg")

    return blocks


BLOCK_COLORS = dict(TOWER_BLOCK_COLORS)
for _mod in list(THEME_MODULES.values()) + [spire_base]:
    BLOCK_COLORS.update(_mod.BLOCK_COLORS)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Generate a tiny test scene: a spire-topped center "
                                               "island plus 3 small satellite islands.")
    ap.add_argument("--seed", type=int, default=1, help="random seed")
    ap.add_argument("--out", type=str, default="scene_tiny", help="output file prefix")
    ap.add_argument("--out-dir", type=Path, default=HERE / "output", dest="out_dir",
                     help="directory for outputs (default: generate/output)")
    ap.add_argument("--schem", action="store_true",
                     help="also export a .schem for WorldEdit (requires mcschematic)")
    args = ap.parse_args()

    blocks = build_scene(seed=args.seed)
    print(f"total blocks: {len(blocks)}")

    structure = common.blocks_to_structure(blocks)
    print(f"structure shape: {structure.shape}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = structure.save(args.out_dir / f"{args.out}.npz")
    print(f"Wrote structure to {npz_path}")

    palette = {
        name: (
            int(color.lstrip("#")[0:2], 16) / 255.0,
            int(color.lstrip("#")[2:4], 16) / 255.0,
            int(color.lstrip("#")[4:6], 16) / 255.0,
        )
        for name, color in BLOCK_COLORS.items()
    }
    out_path = args.out_dir / f"{args.out}.png"
    view_paths = render_screenshot(
        structure, out_path, title=None, palette=palette,
        views=[dict(suffix="_iso", elev=11, azim=-55), dict(suffix="_top", elev=89, azim=-55)],
        width=1000, height=1000,
    )
    _compose_views(view_paths, out_path)
    for p in view_paths:
        Path(p).unlink(missing_ok=True)
    print(f"Saved preview image to {out_path}")

    if args.schem:
        structure.to_schematic(args.out_dir, args.out)


if __name__ == "__main__":
    main()
