"""
Grand Scene Composer
=====================
Combines Sauron's spire (spire.py) with one island of every theme this
project has (13: grass, volcano, snow, desert, mushroom, bones, crystal,
coral, ruins, swamp, prismarine, hive, gearworks), each sized within
DIAMETER_RANGE. The spire doesn't get a dedicated island of its own: it's
planted on top of the HOST_THEME (volcano) island, fixed at the origin.

The other twelve are packed as close to the host as they can get (see
_place_closest): each is dropped in at the smallest radius, and a random
angle at that radius, that clears a minimum distance (island radius +
neighbor's radius + GAP) from every island already placed - so the whole
group pulls in tight around the spire rather than sitting at some
precomputed ring radius, while the random angle search (several candidate
angles are tried at each radius, and one of the valid ones is picked at
random rather than always the first) keeps it from looking like a rigid
spiral. Height is drawn uniformly between the spire's base and 20% of its
height, so islands sit low, near the spire's foot.

The ORDER islands get placed in isn't random: each theme's top-platform
block has a color (see TOP_BLOCK, sourced straight from that theme's own
BLOCK_COLORS), and _order_by_color_spread arranges the placement sequence
so similarly-colored islands (e.g. grass's green and ruins' moss green)
place several turns apart rather than back to back - since each new island
packs in wherever is currently closest, islands placed nearby in time tend
to end up nearby in space, so spacing them out in time is a cheap proxy for
spacing them out in the final layout. That search runs with its own fixed
internal seed, not --seed, so the order is identical across seeds - only
each island's exact packed position changes with --seed.

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

from utils import render_screenshot, BG_COLOR  # noqa: E402
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
GAP = 18  # minimum clear void every pair of islands (host included) must keep between their footprints

RADIUS_SEARCH_STEP = 6      # how far the search radius grows per failed sweep of _place_closest
ANGLE_SAMPLES_PER_STEP = 32  # random angles probed at each search radius

ASSIGNMENT_SEED = 12345  # fixed on purpose - see _order_by_color_spread


def _place_closest(rng, radius_extent, placed):
    """Finds a spot for a new island of this radius as close to the origin
    as the min-distance rule (>= its radius + a neighbor's radius + GAP,
    against every already-placed island) allows: starting from a radius
    that could at best clear the single largest already-placed neighbor, it
    probes ANGLE_SAMPLES_PER_STEP random angles, collects every one that
    actually clears ALL of them, and randomly picks among those - only
    stepping the search radius out by RADIUS_SEARCH_STEP and trying again
    if none of them do. So islands end up as close in as the packing
    genuinely allows, with the randomness coming from which valid angle (of
    however many exist at that radius) gets picked, not from overshooting
    outward. Always terminates - a large enough radius trivially clears
    everything already placed."""
    dist = radius_extent + GAP + max(pr for _, _, pr in placed)
    while True:
        candidates = []
        for _ in range(ANGLE_SAMPLES_PER_STEP):
            angle = rng.uniform(0, 360)
            x, z = dist * math.cos(math.radians(angle)), dist * math.sin(math.radians(angle))
            if all(math.hypot(x - px, z - pz) >= radius_extent + pr + GAP for px, pz, pr in placed):
                candidates.append((x, z, angle))
        if candidates:
            return rng.choice(candidates) + (dist,)
        dist += RADIUS_SEARCH_STEP


# ---------------------------------------------------------------------------
# Placement order: spread similarly-colored tops apart in time
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _color_dist(hex_a, hex_b):
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    return math.sqrt((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2)


def _order_by_color_spread(themes, colors, iterations=4000):
    """Sequence order for `themes` that keeps similarly-colored ones apart
    in placement order: starts from a fixed shuffle, then hill-climbs by
    swapping random pairs whenever it doesn't increase the total "nearby
    closeness" penalty (lower is better - a sum of 1/(distance+1) over
    every pair within 3 positions of each other in the sequence). Runs with
    its own fixed ASSIGNMENT_SEED, not the scene's --seed, so the order is
    always the same; only each island's exact packed position (see
    _place_closest) is controlled by --seed."""
    rng = random.Random(ASSIGNMENT_SEED)
    order = list(themes)
    rng.shuffle(order)
    n = len(order)
    window = min(3, n - 1)

    def penalty():
        return sum(
            1.0 / (_color_dist(colors[order[i]], colors[order[(i + d) % n]]) + 1.0)
            for i in range(n) for d in range(1, window + 1)
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
    placed = []  # (x, z, radius_extent) for every island placed so far, host included

    host_diameter = round(rng.uniform(*DIAMETER_RANGE))
    host_max_depth = max(6, host_diameter // 2)
    blocks.update(THEME_MODULES[HOST_THEME].generate_island(
        seed=seed, diameter=host_diameter, max_depth=host_max_depth,
        decorate_top=False, decorate_underside=True, offset=(0, 0, 0),
    ))
    placed.append((0.0, 0.0, host_diameter / 2.0))
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
    height_lo, height_hi = spire_offset[1], spire_offset[1] + spire_height * 0.2

    ring_themes = [t for t in ALL_THEMES if t != HOST_THEME]
    top_colors = {theme: THEME_MODULES[theme].BLOCK_COLORS[TOP_BLOCK[theme]] for theme in ring_themes}
    order = _order_by_color_spread(ring_themes, top_colors)

    for i, theme in enumerate(order):
        module = THEME_MODULES[theme]
        diameter = round(rng.uniform(*DIAMETER_RANGE))
        radius_extent = diameter / 2.0

        x, z, angle, dist = _place_closest(rng, radius_extent, placed)

        placed.append((x, z, radius_extent))
        y = round(rng.uniform(height_lo, height_hi))
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

def _compose_views(view_paths, out_path, gap=24, divider_color=(26, 26, 26), divider_width=2):
    """Lays out the given rendered view images left-to-right on one shared
    background, with a plain vertical divider line between each pair - no
    titles or captions."""
    from PIL import Image, ImageDraw

    imgs = [Image.open(p).convert("RGB") for p in view_paths]
    h = max(img.height for img in imgs)

    def fit_h(img):
        if img.height == h:
            return img
        w = round(img.width * h / img.height)
        return img.resize((w, h), Image.LANCZOS)

    imgs = [fit_h(img) for img in imgs]

    body_w = sum(img.width for img in imgs) + gap * (len(imgs) - 1)
    body = Image.new("RGB", (body_w, h), BG_COLOR)
    draw = ImageDraw.Draw(body)
    x = 0
    for idx, img in enumerate(imgs):
        body.paste(img, (x, 0))
        x += img.width
        if idx < len(imgs) - 1:
            divider_x = x + gap // 2
            draw.line([(divider_x, 0), (divider_x, h)], fill=divider_color, width=divider_width)
            x += gap

    body.save(out_path)


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
    _compose_views(view_paths, out_path)
    for p in view_paths:
        Path(p).unlink(missing_ok=True)
    print(f"Saved preview image to {out_path}")

    if args.schem:
        structure.to_schematic(args.out_dir, args.out)


if __name__ == "__main__":
    main()
