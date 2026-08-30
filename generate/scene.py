"""
Grand Scene Composer
=====================
Combines Sauron's spire (spire.py) with one island of every theme this
project has (13: grass, volcano, snow, desert, mesa, mushroom, bones,
crystal, coral, ruins, swamp, prismarine, hive), each sized within
DIAMETER_RANGE. The spire doesn't get a themed island of its own: it's
planted on top of a dedicated, deliberately plain dark-stone platform
(spire_base.py - not one of the 13 themes, so it's never placed a second
time in the ring), fixed at the origin. Every one of the 13 themes,
volcano included, is just a normal ring island now.

All thirteen are packed as close to the host as they can get (see
_place_closest): each is dropped in at the smallest radius, and a random
angle at that radius, that clears a minimum distance (island radius +
neighbor's radius + GAP) from every island already placed - so the whole
group pulls in tight around the spire rather than sitting at some
precomputed ring radius, while the random angle search (several candidate
angles are tried at each radius, and one of the valid ones is picked at
random rather than always the first) keeps it from looking like a rigid
spiral.

Height comes from a 2D noise field (see _height_fraction_field) rather than
per-island randomness, so nearby islands land at similar heights and the
cluster reads as one gently undulating group instead of scattered
independently. The field is shifted so its lowest point sits exactly at
the spire's own position (a genuine local minimum of the noise, not just
whatever value happens to be there), and normalized so that minimum maps
to 0% and its highest sampled point maps to 100% of HEIGHT_FRAC_MAX (20%)
of the spire's height - islands away from the spire (which is all of them,
packed as they are) then land a bit above the very bottom rather than
anywhere in the range, without ever exceeding it.

Color feeds directly into _place_closest itself rather than just the order
islands get placed in: each theme's top-platform block has a color (see
TOP_BLOCK, sourced straight from that theme's own BLOCK_COLORS), and
whenever the closest-radius search turns up several angles that all clear
the min-distance rule, the one picked is whichever keeps the most distance
from already-placed islands weighted by how similar their color is to the
new island's - so a spot near a similarly-colored island (e.g. grass's
green near ruins' moss green) is only picked if nothing better-separated
cleared the same radius. It's a real 2D comparison against actual placed
positions, not a proxy - islands stay ordered by simple shuffle, since the
placement mechanic itself now does the color spreading.

Outputs (into --out-dir, default generate/output):
    <out>.npz    canonical Structure (numpy voxel array + Atlas) - the same
                 format every other generator in this project produces.
    <out>.png    preview render, two panels side by side: isometric on the
                 left, top-down on the right.
    <out>.schem  WorldEdit schematic (only with --schem, if mcschematic is
                 installed)

generate/output/scene.png is the STANDARD location to look at this scene -
running the script with no arguments always (re)writes exactly that path,
so that's where to look (or diff against) rather than a one-off render
elsewhere. Point --out/--out-dir at a scratch location (e.g.
generate/output/tmp/) for throwaway experiments instead of overwriting it.

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

from utils import render_screenshot, BG_COLOR, fractal_noise_2d  # noqa: E402
import spire  # noqa: E402
import spire_base  # noqa: E402
import common  # noqa: E402
import grass, volcano, snow, desert, mesa, mushroom, bones  # noqa: E402
import crystal, coral, ruins, swamp, prismarine, hive  # noqa: E402

THEME_MODULES = {
    "grass": grass, "volcano": volcano, "snow": snow, "desert": desert, "mesa": mesa,
    "mushroom": mushroom, "bones": bones, "crystal": crystal, "coral": coral,
    "ruins": ruins, "swamp": swamp, "prismarine": prismarine, "hive": hive,
}
ALL_THEMES = list(THEME_MODULES)
HOST_MODULE = spire_base  # the plain dark-stone platform the spire is planted on, fixed at
                           # the origin - not one of ALL_THEMES, so it never shows up twice

# Each theme's flat top surface is always one fixed block (checked directly
# against every theme module's own top_block function) - used only to look
# up that theme's representative color for _place_closest's color spread.
TOP_BLOCK = {
    "grass": "minecraft:grass_block", "volcano": "minecraft:blackstone",
    "snow": "minecraft:snow_block", "desert": "minecraft:sand", "mesa": "minecraft:red_sand",
    "mushroom": "minecraft:mycelium", "bones": "minecraft:bone_block",
    "crystal": "minecraft:purpur_block", "coral": "minecraft:sand",
    "ruins": "minecraft:moss_block", "swamp": "minecraft:mud",
    "prismarine": "minecraft:prismarine_bricks", "hive": "minecraft:honeycomb_block",
}
HOST_TOP_COLOR = spire_base.BLOCK_COLORS["minecraft:deepslate"]  # for _place_closest's color spread

DIAMETER_RANGE = (100, 120)
GAP = 18  # minimum clear void every pair of islands (host included) must keep between their footprints

RADIUS_SEARCH_STEP = 6      # how far the search radius grows per failed sweep of _place_closest
ANGLE_SAMPLES_PER_STEP = 32  # random angles probed at each search radius

HEIGHT_FRAC_MAX = 0.2          # islands land between 0% (the spire's own base) and this much of its height
HEIGHT_NOISE_BASE_FREQ = 0.01  # spatial frequency of the height field - low, for a broad gentle "flow"
                                # across the whole cluster rather than a bump per island
HEIGHT_NOISE_SAMPLE_RADIUS = 500  # how far out (in blocks) to search for the field's minimum/maximum
HEIGHT_NOISE_SAMPLE_STEP = 5

def _hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _color_dist(hex_a, hex_b):
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    return math.sqrt((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2)


def _color_similarity(hex_a, hex_b):
    """0 (nothing alike) to ~1 (identical) - see _place_closest, where it
    weights how strongly two islands repel each other by position."""
    return 1.0 / (_color_dist(hex_a, hex_b) + 1.0)


def _place_closest(rng, radius_extent, color, placed):
    """Finds a spot for a new island of this radius as close to the origin
    as the min-distance rule (>= its radius + a neighbor's radius + GAP,
    against every already-placed island) allows: starting from a radius
    that could at best clear the single largest already-placed neighbor, it
    probes ANGLE_SAMPLES_PER_STEP random angles and keeps every one that
    clears ALL of them - only stepping the search radius out by
    RADIUS_SEARCH_STEP and retrying if none do, so islands end up as close
    in as the packing genuinely allows.

    Among the valid candidates found at that closest feasible radius, the
    one actually used isn't picked uniformly at random: each is scored by
    summing _color_similarity(color, other's color) / distance(candidate,
    other) over every already-placed island, and the LOWEST-scoring
    candidate wins - i.e. whichever angle keeps the most distance from
    similarly-colored neighbors specifically, not just from neighbors in
    general. `placed` entries are (x, z, radius_extent, color_hex)."""
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
# Height: a 2D noise field, anchored so the spire sits at its low point
# ---------------------------------------------------------------------------

def _height_fraction_field(seed):
    """Builds a smooth 2D noise field (see utils.fractal_noise_2d) over the
    area islands can occupy, locates its lowest point within that sample,
    and returns height_fraction(x, z) - the field re-centered so that
    minimum sits exactly at the origin (the spire's own position) and
    normalized so it maps to 0.0 there and 1.0 at the field's highest
    sampled point. Because the field is smooth and spatially coherent
    (unlike per-island independent randomness), islands near each other
    land at similar heights - the cluster "flows" - and because the spire
    itself anchors the minimum, everything else tends to sit a bit above
    the very bottom rather than anywhere in the range."""
    coords = np.arange(-HEIGHT_NOISE_SAMPLE_RADIUS, HEIGHT_NOISE_SAMPLE_RADIUS + 1, HEIGHT_NOISE_SAMPLE_STEP)
    gx, gz = np.meshgrid(coords, coords, indexing="ij")
    raw = fractal_noise_2d(gx, gz, seed, base_freq=HEIGHT_NOISE_BASE_FREQ)
    noise_min, noise_max = float(raw.min()), float(raw.max())
    anchor_i = np.unravel_index(np.argmin(raw), raw.shape)
    anchor_x, anchor_z = float(gx[anchor_i]), float(gz[anchor_i])

    def height_fraction(x, z):
        value = fractal_noise_2d(
            np.array([x + anchor_x]), np.array([z + anchor_z]), seed, base_freq=HEIGHT_NOISE_BASE_FREQ,
        )[0]
        return min(1.0, max(0.0, (value - noise_min) / (noise_max - noise_min)))

    return height_fraction


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
    placed = []  # (x, z, radius_extent, top_color) for every island placed so far, host included

    top_colors = {theme: THEME_MODULES[theme].BLOCK_COLORS[TOP_BLOCK[theme]] for theme in ALL_THEMES}

    host_diameter = round(rng.uniform(*DIAMETER_RANGE))
    host_max_depth = max(6, host_diameter // 2)
    blocks.update(HOST_MODULE.generate_island(
        seed=seed, diameter=host_diameter, max_depth=host_max_depth,
        decorate_top=False, decorate_underside=True, offset=(0, 0, 0),
    ))
    placed.append((0.0, 0.0, host_diameter / 2.0, HOST_TOP_COLOR))
    print(f"host spire-base island (spire): d={host_diameter}")

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
    height_lo = spire_offset[1]
    height_span = spire_height * HEIGHT_FRAC_MAX
    height_fraction = _height_fraction_field(seed + 9973)

    order = list(ALL_THEMES)
    rng.shuffle(order)

    for i, theme in enumerate(order):
        module = THEME_MODULES[theme]
        diameter = round(rng.uniform(*DIAMETER_RANGE))
        radius_extent = diameter / 2.0

        x, z, angle, dist = _place_closest(rng, radius_extent, top_colors[theme], placed)

        placed.append((x, z, radius_extent, top_colors[theme]))
        y = round(height_lo + height_fraction(x, z) * height_span)
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
for _mod in list(THEME_MODULES.values()) + [spire, spire_base]:
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
