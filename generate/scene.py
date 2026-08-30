"""
Grand Scene Composer
=====================
Combines Sauron's spire (spire.py) with one island of every theme this
project has (13: grass, volcano, snow, desert, mushroom, bones, crystal,
coral, ruins, swamp, prismarine, hive, gearworks), each sized within
DIAMETER_RANGE. The spire doesn't get a dedicated island of its own: it's
planted on top of the HOST_THEME (volcano) island, fixed at the origin.

The other twelve are arranged in a ring around the host - evenly spaced by
angle, at a common radius and height (roughly halfway up the spire) - then
each gets its own independent Gaussian jitter on angle, radius, and height,
so the ring reads as organic rather than a mechanical spoke pattern.

The ring ORDER (which theme sits at which position around the circle) is
not random: each theme's top-platform block has a color (see TOP_BLOCK,
sourced straight from that theme's own BLOCK_COLORS), and a short local
search spreads the order out so two similarly-colored tops - e.g. grass's
green and ruins' moss green - rarely end up next to each other. It's a
cosmetic nudge, not a hard constraint, so the eventual order still looks
hand-shuffled rather than color-sorted.

Outputs (into --out-dir, default generate/out):
    <out>.npz    canonical Structure (numpy voxel array + Atlas) - the same
                 format every other generator in this project produces.
    <out>.png    preview render, two panels side by side: isometric on the
                 left, top-down on the right.
    <out>.schem  WorldEdit schematic (only with --schem, if mcschematic is
                 installed)

generate/out/scene.png is the STANDARD location to look at this scene -
running the script with no arguments always (re)writes exactly that path,
so that's where to look (or diff against) rather than a one-off render
elsewhere. Point --out/--out-dir at a scratch location for throwaway
experiments instead of overwriting it.

Usage:
    python generate/scene.py                # generate with the default seed
    python generate/scene.py --seed 7        # different random layout
"""

import argparse
import math
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))               # utils.py, spire.py
sys.path.insert(0, str(HERE / "islands"))   # common.py + theme modules

from utils import render_screenshot, _add_title_bar, _load_font, BG_COLOR  # noqa: E402
import spire  # noqa: E402
import common  # noqa: E402
import grass, volcano, snow, desert, mushroom, bones  # noqa: E402
import crystal, coral, ruins, swamp, prismarine, hive, gearworks  # noqa: E402

THEME_MODULES = {
    "grass": grass, "volcano": volcano, "snow": snow, "desert": desert,
    "mushroom": mushroom, "bones": bones, "crystal": crystal, "coral": coral,
    "ruins": ruins, "swamp": swamp, "prismarine": prismarine, "hive": hive,
    "gearworks": gearworks,
}
ALL_THEMES = list(THEME_MODULES)
HOST_THEME = "volcano"  # whichever island the spire is planted on, fixed at the origin

# Each theme's flat top surface is always one fixed block (checked directly
# against every theme module's own top_block function) - used only to look
# up that theme's representative color for the ring-order color spread.
TOP_BLOCK = {
    "grass": "minecraft:grass_block", "volcano": "minecraft:blackstone",
    "snow": "minecraft:snow_block", "desert": "minecraft:sand",
    "mushroom": "minecraft:mycelium", "bones": "minecraft:bone_block",
    "crystal": "minecraft:calcite", "coral": "minecraft:sand",
    "ruins": "minecraft:moss_block", "swamp": "minecraft:mud",
    "prismarine": "minecraft:prismarine_bricks", "hive": "minecraft:honeycomb_block",
    "gearworks": "minecraft:copper_block",
}

DIAMETER_RANGE = (100, 120)

# Ring layout: 12 satellites (everything but the host) spaced 30 degrees
# apart at RING_RADIUS, each independently perturbed by Gaussian noise
# rather than placed exactly on the ideal spoke - RADIUS_STD/ANGLE_STD_DEG
# are kept well under half the nominal spacing so jitter reads as organic
# variation, not overlap. RING_RADIUS itself is sized for the *tangential*
# fit (neighbors at the mean diameter, 30 degrees apart, need to clear each
# other), which needs far more room than simply clearing the host.
N_RING = len(ALL_THEMES) - 1
ANGLE_STEP_DEG = 360 / N_RING
_MEAN_RADIUS = sum(DIAMETER_RANGE) / 4  # mean island radius = mean diameter / 2
RING_RADIUS = _MEAN_RADIUS / math.sin(math.radians(ANGLE_STEP_DEG / 2)) + _MEAN_RADIUS
RADIUS_STD = 15
ANGLE_STD_DEG = 4
HEIGHT_STD = 20  # islands sit around halfway up the spire, +/- this (see build_scene)


# ---------------------------------------------------------------------------
# Ring order: spread similarly-colored tops apart
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _color_dist(hex_a, hex_b):
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    return math.sqrt((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2)


def _order_by_color_spread(rng, themes, colors, iterations=2000):
    """Circular ordering of `themes` that keeps similarly-colored neighbors
    apart: starts from a random shuffle, then hill-climbs by swapping random
    pairs whenever it doesn't increase the total "closeness" penalty (a
    lower-is-better sum of 1/(distance+1) over adjacent pairs). Stays random
    rather than fully color-sorted - it only ever takes swaps that are as
    good or better than what it had, from a random starting point."""
    order = list(themes)
    rng.shuffle(order)
    n = len(order)

    def penalty():
        return sum(
            1.0 / (_color_dist(colors[order[i]], colors[order[(i + 1) % n]]) + 1.0)
            for i in range(n)
        )

    current = penalty()
    for _ in range(iterations):
        i, j = rng.randrange(n), rng.randrange(n)
        if i == j:
            continue
        order[i], order[j] = order[j], order[i]
        p = penalty()
        if p <= current:
            current = p
        else:
            order[i], order[j] = order[j], order[i]  # revert
    return order


# ---------------------------------------------------------------------------
# Scene assembly
# ---------------------------------------------------------------------------

def structure_to_blocks(structure, offset=(0, 0, 0)):
    """Converts a Structure back into the {(x, y, z): block_name} dict
    format the island generators use, so it can be merged into one scene."""
    ox, oy, oz = offset
    data = structure.data
    xs, ys, zs = np.nonzero(data)
    names = np.array(structure.atlas.names, dtype=object)[data[xs, ys, zs]]
    return {
        (int(x) + ox, int(y) + oy, int(z) + oz): name
        for x, y, z, name in zip(xs.tolist(), ys.tolist(), zs.tolist(), names.tolist())
    }


def build_scene(seed=1):
    rng = random.Random(seed)
    blocks = {}

    host_diameter = round(rng.uniform(*DIAMETER_RANGE))
    host_max_depth = max(6, host_diameter // 2)
    blocks.update(THEME_MODULES[HOST_THEME].generate_island(
        seed=seed, diameter=host_diameter, max_depth=host_max_depth,
        decorate_top=False, decorate_underside=True, offset=(0, 0, 0),
    ))
    print(f"host {HOST_THEME} island (spire): d={host_diameter}")

    print("generating spire...")
    grid = spire.generate_spire(seed=seed)
    spire_structure = spire.grid_to_structure(grid)
    spire.hollow_out(spire_structure.data, 2)
    spire_height = int(np.nonzero(spire_structure.data)[1].max())
    # spire's own (X, Z) center is (CX, CY); its Y=0 is its flat base, which
    # needs to land right on the buildable surface just above the host
    # island's flat top (topY=0, so the surface to build on is y=1).
    spire_offset = (-spire.CX, 1, -spire.CY)
    blocks.update(structure_to_blocks(spire_structure, offset=spire_offset))
    half_height = spire_offset[1] + spire_height / 2

    ring_themes = [t for t in ALL_THEMES if t != HOST_THEME]
    top_colors = {theme: THEME_MODULES[theme].BLOCK_COLORS[TOP_BLOCK[theme]] for theme in ring_themes}
    order = _order_by_color_spread(rng, ring_themes, top_colors)
    rotation = rng.uniform(0, 360)

    for i, theme in enumerate(order):
        module = THEME_MODULES[theme]
        diameter = round(rng.uniform(*DIAMETER_RANGE))
        angle = rotation + i * ANGLE_STEP_DEG + rng.gauss(0, ANGLE_STD_DEG)
        dist = RING_RADIUS + rng.gauss(0, RADIUS_STD)
        y = round(half_height + rng.gauss(0, HEIGHT_STD))
        x = dist * math.cos(math.radians(angle))
        z = dist * math.sin(math.radians(angle))
        offset = (round(x), y, round(z))
        max_depth = max(6, diameter // 2)

        island_blocks = module.generate_island(
            seed=seed * 1000 + i + 1, diameter=diameter, max_depth=max_depth,
            decorate_top=False, decorate_underside=True, offset=offset,
        )
        blocks.update(island_blocks)
        print(f"  {theme:<10} d={diameter:<4} pos=({offset[0]:>5}, {offset[1]:>4}, {offset[2]:>5})  "
              f"dist={dist:.0f} angle={angle:.0f}deg")

    return blocks


BLOCK_COLORS = {}
for _mod in list(THEME_MODULES.values()) + [spire]:
    BLOCK_COLORS.update(_mod.BLOCK_COLORS)


# ---------------------------------------------------------------------------
# Two-panel preview: isometric | top-down
# ---------------------------------------------------------------------------

def _compose_views(view_paths, labels, out_path, title):
    """Lays out the given rendered view images left-to-right on one shared
    background, each captioned, under one title bar."""
    from PIL import Image, ImageDraw

    imgs = [Image.open(p).convert("RGB") for p in view_paths]
    h = max(img.height for img in imgs)

    def fit_h(img):
        if img.height == h:
            return img
        w = round(img.width * h / img.height)
        return img.resize((w, h), Image.LANCZOS)

    imgs = [fit_h(img) for img in imgs]

    gap, label_h = 24, 34
    font = _load_font(22)
    body_w = sum(img.width for img in imgs) + gap * (len(imgs) - 1)
    body = Image.new("RGB", (body_w, label_h + h), BG_COLOR)
    draw = ImageDraw.Draw(body)
    x = 0
    for img, label in zip(imgs, labels):
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((x + (img.width - tw) / 2, 6), label, fill=(26, 26, 26), font=font)
        body.paste(img, (x, label_h))
        x += img.width + gap

    _add_title_bar(body, title, bg_color=BG_COLOR).save(out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Generate the full spire + floating-islands scene.")
    ap.add_argument("--seed", type=int, default=1, help="random seed")
    ap.add_argument("--out", type=str, default="scene", help="output file prefix")
    ap.add_argument("--out-dir", type=Path, default=HERE / "out", dest="out_dir",
                     help="directory for outputs (default: generate/out)")
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
        width=1600, height=1600,
    )
    _compose_views(view_paths, ["isometric", "top-down"], out_path, title=f"grand scene (seed={args.seed})")
    for p in view_paths:
        Path(p).unlink(missing_ok=True)
    print(f"Saved preview image to {out_path}")

    if args.schem:
        structure.to_schematic(args.out_dir, args.out)


if __name__ == "__main__":
    main()
