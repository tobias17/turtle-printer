"""
Grand Scene Composer
=====================
Combines Sauron's spire (spire.py) with one island of every theme this
project has (13: grass, volcano, snow, desert, mushroom, bones, crystal,
coral, ruins, swamp, prismarine, hive, gearworks), each sized within
DIAMETER_RANGE. The spire doesn't get a dedicated island of its own: it's
planted on top of the HOST_THEME (volcano) island, fixed at the origin.

The other twelve are laid out in as many concentric rings as their geometry
needs (see _ring_layout): rings are added outward until their combined
capacity - how many max-size islands actually fit around each one with
good gaps - covers all of them, then islands are round-robin balanced
across just those rings so each one carries roughly its fair share rather
than always maxing out the innermost first. Nothing about ring count or
radii is hard-coded, so adding or removing a theme just reflows the rings.
Every island then gets its own independent Gaussian jitter off its slot's
nominal spot (angle, radius, and height), re-rolled if it would actually
collide with an already-placed island, so the rings read as organic rather
than a mechanical spoke pattern while staying guaranteed non-overlapping.
Height is drawn uniformly between the spire's base and half its height, so
the rings sit in the tower's lower half rather than centered on it.

WHICH theme sits at which slot is decided separately from all of that, by
_assign_themes_to_slots: each theme's top-platform block has a color (see
TOP_BLOCK, sourced straight from that theme's own BLOCK_COLORS), and a
generic local search assigns themes to the fixed slot positions to (locally)
maximize the total color-similarity-weighted physical distance between
every pair - i.e. push similarly-colored islands (e.g. grass's green and
ruins' moss green) as far apart as the layout allows. That search runs with
its own fixed internal seed, not --seed, so the assignment is identical
across seeds - only the exact jittered position of each already-assigned
island changes with --seed.

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
GAP = 6  # minimum clear void kept between any two islands' footprints (and between the host and ring 0)

# Ring geometry is sized off the *largest possible* island (DIAMETER_RANGE's
# max), so clearance is guaranteed regardless of what diameter actually gets
# rolled for any given slot, and regardless of how many islands there are in
# total - see _ring_layout, which is the only thing that decides ring
# count/radii/per-ring occupancy, all computed from n_items alone.
_MAX_RADIUS = DIAMETER_RANGE[1] / 2.0
RING_GAP_FACTOR = 1.2  # extra breathing room applied to every radial gap - ring 0 to host,
                       # and ring to ring - beyond the bare minimum clearance

RADIUS_STD = 20      # Gaussian jitter off each slot's nominal radius
ANGLE_STD_DEG = 8     # ...and off its nominal angle
MAX_PLACEMENT_TRIES = 200  # re-roll jitter this many times before falling back to the exact slot

ASSIGNMENT_SEED = 12345  # fixed on purpose - see _assign_themes_to_slots


def _ring_capacity(radius, item_radius=_MAX_RADIUS, gap=GAP):
    """How many items of radius `item_radius` fit evenly spaced around a
    circle of this `radius`, keeping at least `gap` clearance between
    neighbors - the exact circle-packing bound (chord length 2*R*sin(pi/k)
    must clear 2*item_radius+gap), not a circumference/spacing
    approximation, which overshoots at the small counts inner rings have."""
    clearance = item_radius + gap / 2.0
    if radius <= clearance:
        return 1
    return max(1, math.floor(math.pi / math.asin(min(1.0, clearance / radius))))


def _ring_layout(n_items):
    """Dynamically lays out `n_items` slots - nominal (radius, angle_deg) -
    into as many concentric rings as needed. Nothing about ring count,
    radii, or per-ring occupancy is hard-coded, so adding or removing
    island themes (changing n_items) just works:

      1. Rings are added outward, one at a time (radius growing by a fixed
         step each time), accumulating each new ring's capacity
         (_ring_capacity) until the running total covers n_items.
      2. Items are then distributed across just those rings by round-robin
         (repeatedly filling whichever ring currently holds the fewest,
         skipping any already at its capacity) - this balances the
         per-ring counts as evenly as their geometry allows, rather than
         always maxing out the inner rings first and leaving outer ones
         sparse.

    Each ring's start angle is staggered half a slot from the ring before
    it, so slots don't all line up along the same spokes."""
    ring0_radius = (_MAX_RADIUS + _MAX_RADIUS + GAP) * RING_GAP_FACTOR  # clears the host
    ring_spacing = (2 * _MAX_RADIUS + GAP) * RING_GAP_FACTOR            # clears the ring before it

    radii, capacities, covered = [], [], 0
    while covered < n_items:
        radius = ring0_radius + len(radii) * ring_spacing
        cap = _ring_capacity(radius)
        radii.append(radius)
        capacities.append(cap)
        covered += cap

    counts = [0] * len(radii)
    for _ in range(n_items):
        i = min((i for i in range(len(radii)) if counts[i] < capacities[i]), key=lambda i: counts[i])
        counts[i] += 1

    slots = []
    for ring_i, (radius, count) in enumerate(zip(radii, counts)):
        step = 360.0 / count
        stagger = (step / 2.0) * (ring_i % 2)
        for k in range(count):
            slots.append((radius, stagger + k * step))
    return slots


# ---------------------------------------------------------------------------
# Slot assignment: spread similarly-colored tops apart
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


def _assign_themes_to_slots(themes, colors, slots, iterations=8000):
    """Generic theme -> slot assignment: (locally) maximizes, over every
    pair of islands, color_similarity(a, b) * physical_distance(slot_a,
    slot_b) - i.e. rewards putting similarly-colored islands far apart and
    is indifferent to how far apart dissimilar ones end up. A textbook
    quadratic-assignment-style hill climb (random swap, keep it if the
    score doesn't drop) starting from a fixed shuffle - deterministic (same
    result every run) because it uses its own ASSIGNMENT_SEED rather than
    the scene's --seed, which only controls each island's exact jitter
    around whatever slot it lands in here."""
    positions = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for r, a in slots]
    rng = random.Random(ASSIGNMENT_SEED)
    order = list(themes)
    rng.shuffle(order)
    n = len(order)

    def dist(i, j):
        return math.hypot(positions[i][0] - positions[j][0], positions[i][1] - positions[j][1])

    def score():
        return sum(
            _color_similarity(colors[order[i]], colors[order[j]]) * dist(i, j)
            for i in range(n) for j in range(i + 1, n)
        )

    current = score()
    for _ in range(iterations):
        i, j = rng.randrange(n), rng.randrange(n)
        if i == j:
            continue
        order[i], order[j] = order[j], order[i]
        s = score()
        if s >= current:
            current = s
        else:
            order[i], order[j] = order[j], order[i]  # revert

    return {theme: slots[i] for i, theme in enumerate(order)}


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
    height_lo, height_hi = spire_offset[1], spire_offset[1] + spire_height / 2

    ring_themes = [t for t in ALL_THEMES if t != HOST_THEME]
    top_colors = {theme: THEME_MODULES[theme].BLOCK_COLORS[TOP_BLOCK[theme]] for theme in ring_themes}
    slots = _ring_layout(len(ring_themes))
    assignment = _assign_themes_to_slots(ring_themes, top_colors, slots)
    # innermost ring first, so each new island has the fullest picture of
    # what's already down when it checks for collisions
    ordered = sorted(assignment.items(), key=lambda kv: kv[1][0])

    for i, (theme, (nom_radius, nom_angle)) in enumerate(ordered):
        module = THEME_MODULES[theme]
        diameter = round(rng.uniform(*DIAMETER_RANGE))
        radius_extent = diameter / 2.0

        for _ in range(MAX_PLACEMENT_TRIES):
            angle = nom_angle + rng.gauss(0, ANGLE_STD_DEG)
            dist = nom_radius + rng.gauss(0, RADIUS_STD)
            x, z = dist * math.cos(math.radians(angle)), dist * math.sin(math.radians(angle))
            if all(math.hypot(x - px, z - pz) >= radius_extent + pr + GAP for px, pz, pr in placed):
                break
        else:
            # The exact nominal slot is guaranteed clear by construction
            # (ring radii are spaced for the largest possible island), so
            # falling back to it - jitter-free, this once - can't collide.
            angle, dist = nom_angle, nom_radius
            x, z = dist * math.cos(math.radians(angle)), dist * math.sin(math.radians(angle))
            print(f"  note: used the exact ring slot for {theme} (jitter kept colliding)")

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
              f"ring_r={nom_radius:.0f} dist={dist:.0f} angle={angle:.0f}deg")

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
