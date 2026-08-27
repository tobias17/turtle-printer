"""
Floating Island Generator for Minecraft
=========================================

Procedurally generates floating rock islands (irregular grassy top,
tapering rocky underside, hanging "root" stalactites, moss/vine
decoration) in the style of concept-art floating islands.

Outputs (into --out-dir, default generate/out):
  1. A .npz Structure (block-index array + Atlas legend) in the same
     canonical format used by tree.py - see generate/utils.py.
  2. A 3D preview image rendered as full shaded blocks so you can check
     the shape BEFORE building anything in-game.
  3. Optionally (--schem) a WorldEdit schematic, to see it live in a
     creative-mode save.

No external world/game connection is needed to preview - this is pure
geometry + a plotting library.

Usage:
    python island.py --diameter 40           # single island, flat 40-block-wide top
    python island.py --diameter 40 --seed 7  # different random variation, same size
    python island.py --scene                 # old multi-island demo composition

By default the island has a perfectly FLAT top (single Y level) so it's
easy to build on, but the outline is irregular (not a perfect circle) and
the underside tapers down into rock with hanging root/stalactite drips.
"""

import argparse
import math
import random
from pathlib import Path

import numpy as np

from utils import Atlas, Structure, render_screenshot, value_noise_2d


# ---------------------------------------------------------------------------
# Island generation
# ---------------------------------------------------------------------------

STONE_VARIANTS = [
    ("minecraft:stone", 0.85),
    ("minecraft:andesite", 0.15),
]


def pick_stone(rng):
    roll = rng.random()
    acc = 0
    for block, p in STONE_VARIANTS:
        acc += p
        if roll <= acc:
            return block
    return "minecraft:stone"


def _drip_radius_profile(t, rise_frac, taper_power):
    """Radius profile for a drip, as a multiplier in [0, 1], parameterized
    by fraction-of-length t in [0, 1]. Zero at t=0 (top, so it attaches
    cleanly with no shelf), rises quickly to its full width over the first
    `rise_frac` of the length, then narrows continuously (monotonically -
    no re-widening) down to a point at t=1. No bulge/dip in the middle, so
    it reads as one consistently tapering spike rather than growing then
    shrinking."""
    def smoothstep(u):
        u = min(max(u, 0.0), 1.0)
        return u * u * (3 - 2 * u)

    rise_frac = min(max(rise_frac, 1e-6), 1 - 1e-6)
    if t <= rise_frac:
        return smoothstep(t / rise_frac)
    u = (t - rise_frac) / (1 - rise_frac)
    return max(0.0, 1 - u) ** taper_power


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
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    radius = diameter / 2.0

    size = int(radius * 2 + 6)
    half = size // 2

    # Detail (noise grid resolution, harmonic count) scales with island size
    # so bumps/roughness stay roughly constant in block-size rather than
    # stretching thin and looking under-detailed on big islands.
    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    k_max = max(6, 4 + int(diameter / 16))

    # Irregular radial silhouette (a few sine harmonics -> lumpy circle,
    # not a perfect disc)
    thetas = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    R = np.full(360, float(radius))
    for k in range(2, k_max):
        amp = radius * np_rng.uniform(0.015, 0.045) / math.sqrt(k_max / 6)
        phase = np_rng.uniform(0, 2 * np.pi)
        R += amp * np.sin(k * thetas + phase)
    R = np.clip(R, radius * 0.55, None)

    edge_noise = value_noise_2d(size, grid_for(5), seed + 1) * (radius * 0.05)
    hill_noise = value_noise_2d(size, grid_for(6), seed + 2)
    # per-column jitter on the taper radius so the underside isn't a
    # perfectly smooth cone
    taper_noise = value_noise_2d(size, grid_for(4, 8), seed + 3) * (radius * 0.08)
    # smooth noise driving the grass+dirt thickness (min..max range)
    thickness_noise = value_noise_2d(size, grid_for(6), seed + 5)

    # How much the body's radius shrinks from just-under-the-dirt (t=0) down
    # to max_depth (t=1). TAPER_EXPONENT < 1 front-loads the shrinkage so
    # tapering is visible immediately rather than staying flat-sided for the
    # first several layers.
    TAPER_STRENGTH = 0.85
    TAPER_EXPONENT = 0.6

    min_thick, max_thick = top_thickness_range

    blocks = {}
    col_bottom = {}
    columns = []  # (x, z, topY, depth, r, localR) - depth is the carved depth
    for xi in range(size):
        for zi in range(size):
            x, z = xi - half, zi - half
            r = math.hypot(x, z)
            theta = math.atan2(z, x) % (2 * math.pi)
            idx = int(theta / (2 * math.pi) * 360) % 360
            localR = R[idx] + edge_noise[xi, zi]
            if r > localR:
                continue
            topY = 0 if flat_top else int(round(hill_noise[xi, zi] * 2.2))

            norm = (thickness_noise[xi, zi] + 1) / 2  # 0..1
            thickness = int(round(min_thick + norm * (max_thick - min_thick)))
            thickness = min(max(thickness, min_thick), max_thick)

            blocks[(x, topY, z)] = "minecraft:grass_block"

            # Carve everything below grass - dirt, then stone - in one
            # continuous taper. The allowed radius shrinks starting right
            # after the grass layer (only the single grass block itself is
            # guaranteed full-width), so the dirt band tapers in too instead
            # of standing as a vertical wall down to where stone starts.
            total_depth = (thickness - 1) + max_depth
            jitter = taper_noise[xi, zi]
            bottomY = topY
            for y_offset in range(1, total_depth + 1):
                t = y_offset / total_depth
                allowed_r = localR * (1 - TAPER_STRENGTH * (t ** TAPER_EXPONENT)) + jitter
                if y_offset > 1 and r > max(allowed_r, 0):
                    break
                y = topY - y_offset
                block = "minecraft:dirt" if y_offset < thickness else pick_stone(rng)
                blocks[(x, y, z)] = block
                bottomY = y

            depth = topY - bottomY
            col_bottom[(x, z)] = (bottomY, topY, r, localR)
            columns.append((x, z, topY, depth, r, localR))

            # occasional moss cap on the very bottom face near the edge
            if r / localR > 0.65 and rng.random() < 0.35:
                blocks[(x, bottomY, z)] = "minecraft:mossy_cobblestone"

    if decorate_underside:
        # Eligible origins are ANY column, not just the rim - the taper
        # already makes central columns the deepest part of the underside,
        # so restricting to a rim band was cutting out the exact spots
        # (toward the center) where long hanging roots read most naturally.
        # Density is applied to the full column count, so it scales with
        # the island's underside area (which is what actually needs
        # covering) rather than any diameter formula.
        max_drip_r = max(0, round(diameter / 40))
        KEEP_OUT_MARGIN = 1  # a radius-3 drip needs 3+1 blocks of clearance
        eligible = columns

        n_drips = num_drips if num_drips is not None else max(3, int(len(eligible) * drip_density))

        # Each drip gets its OWN randomized length cap (derived from
        # max_depth, not a literal), so lengths vary from short stubs to
        # occasional longer roots instead of clustering under one shared
        # maximum.
        len_floor = max(2, round(max_depth * 0.06))
        len_ceiling = max(len_floor + 2, round(max_depth * 0.4))

        rng.shuffle(eligible)
        for (x, z, topY, depth, r, localR) in eligible[:n_drips]:
            bottomY, _, _, _ = col_bottom[(x, z)]

            # Keep-out zone: a drip of radius N must stay at least N blocks
            # (plus margin) from the true edge, so its lateral spread never
            # reaches past the island's silhouette. Cap this drip's radius
            # by how much clearance its own column actually has. Central
            # columns have huge clearance, so they're free to grow the
            # thickest drips.
            clearance = int(localR - r)
            local_max_r = max(0, min(max_drip_r, clearance - KEEP_OUT_MARGIN))
            drip_r_choices = list(range(0, local_max_r + 1))
            drip_r_weights = [3] + [1] * local_max_r if local_max_r > 0 else [1]
            drip_r = rng.choices(drip_r_choices, weights=drip_r_weights)[0]

            # Length is scaled by thickness: a radius-0 spike is a thin
            # single-block column for its whole length, so a long one reads
            # as an unnaturally long toothpick. Thin drips are capped much
            # shorter; only thicker drips can reach the full length range.
            radius_frac = drip_r / max(1, max_drip_r)
            this_len_ceiling = len_floor + max(2, round((len_ceiling - len_floor) * radius_frac))
            this_len_ceiling = min(this_len_ceiling, len_ceiling)
            personal_cap = rng.randint(len_floor, this_len_ceiling)
            drip_len = rng.randint(len_floor, personal_cap)

            # Radius rises quickly off the attachment point (no exposed
            # shelf) then narrows continuously to a point at the tip - no
            # bulge/dip, so it reads as one consistent taper rather than
            # growing then shrinking. A plain filled disc each layer, no
            # per-block randomness, so nothing pokes out sideways.
            rise_frac = rng.uniform(0.08, 0.2)
            taper_power = rng.uniform(0.9, 1.4)
            for dl in range(drip_len):
                t = dl / max(1, drip_len - 1)
                radius = drip_r * _drip_radius_profile(t, rise_frac, taper_power)
                # local_max_r is the hard keep-out bound computed above
                radius = max(0.0, min(radius, local_max_r))
                y = bottomY - dl
                is_tip = t > 0.8
                ir = min(math.floor(radius), local_max_r)
                for dx in range(-ir, ir + 1):
                    for dz in range(-ir, ir + 1):
                        if dx * dx + dz * dz <= radius * radius:
                            block = "minecraft:mossy_cobblestone" if is_tip else "minecraft:stone"
                            blocks[(x + dx, y, z + dz)] = block
            if rng.random() < 0.6:
                blocks[(x, bottomY - drip_len, z)] = "minecraft:vine"

        # vines draped down from the underside near the outer rim
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR > 0.55 and rng.random() < 0.18:
                bottomY, _, _, _ = col_bottom[(x, z)]
                for vy in range(rng.randint(2, 6)):
                    blocks.setdefault((x, bottomY - vy, z), "minecraft:vine")

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
    rng = random.Random(seed)
    blocks = {}

    # main island
    blocks.update(generate_island(seed=seed, diameter=40, max_depth=16,
                                   num_drips=14, offset=(0, 90, 0)))

    # a couple of medium islands
    satellite_specs = [
        dict(diameter=20, max_depth=9, num_drips=6, offset=(-42, 110, -10)),
        dict(diameter=16, max_depth=8, num_drips=5, offset=(30, 118, -28)),
    ]
    for i, spec in enumerate(satellite_specs):
        blocks.update(generate_island(seed=seed + 10 + i, **spec))

    # tiny floating debris (just a few blocks each), like the specks in the sky
    for i in range(5):
        cx = rng.randint(-55, 55)
        cy = rng.randint(95, 130)
        cz = rng.randint(-40, 20)
        n = rng.randint(1, 4)
        for _ in range(n):
            dx, dy, dz = rng.randint(-1, 1), rng.randint(-1, 1), rng.randint(-1, 1)
            blocks[(cx + dx, cy + dy, cz + dz)] = "minecraft:stone"

    return blocks


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def blocks_to_structure(blocks):
    """Converts a {(x, y, z): "minecraft:block_id"} dict to the project's
    canonical Structure: a 3D numpy array of int16 block indices
    (X, Y, Z with Y up, 0 = air) plus an Atlas naming each index.
    Coordinates are shifted so the bounding box starts at the origin."""
    items = list(blocks.items())
    atlas = Atlas()
    indices = {name: atlas.add(name) for name in sorted({b for _, b in items})}
    xs = np.array([k[0] for k, _ in items])
    ys = np.array([k[1] for k, _ in items])
    zs = np.array([k[2] for k, _ in items])
    origin = (int(xs.min()), int(ys.min()), int(zs.min()))
    shape = (int(xs.max()) - origin[0] + 1,
             int(ys.max()) - origin[1] + 1,
             int(zs.max()) - origin[2] + 1)
    data = np.zeros(shape, dtype=np.int16)
    data[xs - origin[0], ys - origin[1], zs - origin[2]] = (
        np.array([indices[b] for _, b in items], dtype=np.int16)
    )
    return Structure.from_data(data, atlas)


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


def preview(structure, out_path="preview.png", title=None):
    """Renders the island as full shaded blocks (one 3D screenshot in the
    same style as islands_old's screenshots) and saves it to out_path."""
    palette = {
        name: (
            int(color.lstrip("#")[0:2], 16) / 255.0,
            int(color.lstrip("#")[2:4], 16) / 255.0,
            int(color.lstrip("#")[4:6], 16) / 255.0,
        )
        for name, color in BLOCK_COLORS.items()
    }
    return render_screenshot(structure, out_path, title=title, palette=palette)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Generate a floating island for Minecraft.")
    ap.add_argument("--seed", type=int, default=1, help="random seed")
    ap.add_argument("--diameter", type=int, default=32,
                     help="top diameter of the island in blocks (default: 32)")
    ap.add_argument("--max-depth", type=int, default=None,
                     help="how far the rock tapers down below the top (default: scales with diameter)")
    ap.add_argument("--num-drips", type=int, default=None,
                     help="number of hanging root/stalactite drips (default: auto-scales with the "
                          "island's rim geometry - see --drip-density)")
    ap.add_argument("--drip-density", type=float, default=None,
                     help="fraction of eligible rim columns that grow a drip, used only when "
                          "--num-drips is not set (default: 0.05)")
    ap.add_argument("--decorate-top", action="store_true",
                     help="scatter grass/flowers/trees on top (off by default so it stays buildable)")
    ap.add_argument("--no-underside-decor", action="store_true",
                     help="disable drips/vines/moss on the underside")
    ap.add_argument("--out", type=str, default="island", help="output file prefix")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "out",
                     dest="out_dir",
                     help="directory for outputs (default: generate/out)")
    ap.add_argument("--scene", action="store_true",
                     help="generate the old multi-island demo scene instead of a single island")
    ap.add_argument("--schem", action="store_true",
                     help="also export a .schem for WorldEdit (requires mcschematic)")
    args = ap.parse_args()

    if args.scene:
        blocks = generate_scene(seed=args.seed)
    else:
        max_depth = args.max_depth if args.max_depth is not None else max(6, args.diameter // 2)
        kwargs = dict(
            seed=args.seed,
            diameter=args.diameter,
            max_depth=max_depth,
            num_drips=args.num_drips,  # None -> auto-scales inside generate_island
            decorate_top=args.decorate_top,
            decorate_underside=not args.no_underside_decor,
        )
        if args.drip_density is not None:
            kwargs["drip_density"] = args.drip_density
        blocks = generate_island(**kwargs)

    structure = blocks_to_structure(blocks)
    npz_path = structure.save(args.out_dir / f"{args.out}.npz")
    print(f"Wrote {len(blocks)} blocks to {npz_path}")

    title = (f"multi-island demo scene (seed={args.seed})" if args.scene
             else f"floating island (d={args.diameter}, seed={args.seed})")
    png_path = preview(structure, out_path=args.out_dir / f"{args.out}.png", title=title)
    print(f"Saved preview image to {png_path}")

    if args.schem:
        structure.to_schematic(args.out_dir, args.out)


if __name__ == "__main__":
    main()
