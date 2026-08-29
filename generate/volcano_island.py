"""
Volcanic Floating Island Generator for Minecraft
=================================================

A fork of island.py with a volcanic theme: dark igneous stone instead of
grass/dirt/stone. The top crust is solid black (blackstone, with rare
obsidian flecks), then color gradually shifts to a darker grey with depth
- basalt, deepslate, cobbled deepslate, tuff - as you move down toward the
underside, with per-column/per-voxel noise so the banding isn't a
perfectly smooth gradient. No lava/magma - pure stone-color grading, kept
dark top to bottom (no light greys or white stone).
Meant to sit around spire.py's dark tower.

Outputs (into --out-dir, default generate/out):
  1. A .npz Structure (block-index array + Atlas legend) in the same
     canonical format used by tree.py/island.py - see generate/utils.py.
  2. A 3D preview image rendered as full shaded blocks so you can check
     the shape BEFORE building anything in-game.
  3. Optionally (--schem) a WorldEdit schematic, to see it live in a
     creative-mode save.

Usage:
    python volcano_island.py --diameter 40
    python volcano_island.py --diameter 40 --seed 7
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


def _drip_radius_profile(t, rise_frac, taper_power):
    """Radius profile for a drip, as a multiplier in [0, 1], parameterized
    by fraction-of-length t in [0, 1]. Zero at t=0 (top, so it attaches
    cleanly with no shelf), rises quickly to its full width over the first
    `rise_frac` of the length, then narrows continuously (monotonically -
    no re-widening) down to a point at t=1."""
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
    """Returns dict {(x, y, z): "minecraft:block_id"} for one volcanic
    island, positioned with its center at `offset`. Same silhouette/taper/
    drip machinery as island.generate_island, but re-themed: solid black
    crust on top, gradually lightening stone body as depth increases, and
    pale root-drips on the underside.

    diameter        - island top diameter in blocks (radius = diameter / 2)
    flat_top        - if True (default), the top surface is a single flat
                       Y level. Outline is still irregular.
    top_thickness_range - (min, max) number of crust layers, forced solid
                       black, before the color gradient starts. Varies
                       smoothly across the island.
    num_drips / drip_density - see island.py; same auto-scaling behavior.
    decorate_top     - if True, scatters small basalt columns on top. Off
                       by default so the surface stays buildable.
    decorate_underside - hanging root drips on the rock underside. On by
                       default.
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    radius = diameter / 2.0

    size = int(radius * 2 + 6)
    half = size // 2

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    k_max = max(6, 4 + int(diameter / 16))

    thetas = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    R = np.full(360, float(radius))
    for k in range(2, k_max):
        amp = radius * np_rng.uniform(0.015, 0.045) / math.sqrt(k_max / 6)
        phase = np_rng.uniform(0, 2 * np.pi)
        R += amp * np.sin(k * thetas + phase)
    R = np.clip(R, radius * 0.55, None)

    edge_noise = value_noise_2d(size, grid_for(5), seed + 1) * (radius * 0.05)
    hill_noise = value_noise_2d(size, grid_for(6), seed + 2)
    taper_noise = value_noise_2d(size, grid_for(4, 8), seed + 3) * (radius * 0.08)
    thickness_noise = value_noise_2d(size, grid_for(6), seed + 5)
    # per-column offset (in gradient-index units) so the dark->light
    # transition isn't a perfectly smooth function of depth alone - a
    # coarse field for broad blotches plus a finer one for speckle
    gradient_noise = value_noise_2d(size, grid_for(4, 8), seed + 9) * 1.8
    speckle_noise = value_noise_2d(size, grid_for(2, 12), seed + 13) * 1.1

    TAPER_STRENGTH = 0.85
    TAPER_EXPONENT = 0.6

    min_thick, max_thick = top_thickness_range

    blocks = {}
    col_bottom = {}
    columns = []  # (x, z, topY, depth, r, localR)
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

            blocks[(x, topY, z)] = pick_black(rng)

            total_depth = (thickness - 1) + max_depth
            jitter = taper_noise[xi, zi]
            g_jitter = gradient_noise[xi, zi] + speckle_noise[xi, zi]
            bottomY = topY
            for y_offset in range(1, total_depth + 1):
                t = y_offset / total_depth
                allowed_r = localR * (1 - TAPER_STRENGTH * (t ** TAPER_EXPONENT)) + jitter
                if y_offset > 1 and r > max(allowed_r, 0):
                    break
                y = topY - y_offset
                if y_offset < thickness:
                    block = pick_black(rng)
                else:
                    t_grad = (y_offset - thickness) / max(1, total_depth - thickness)
                    block = pick_gradient(rng, t_grad, jitter=g_jitter + rng.uniform(-0.9, 0.9))
                blocks[(x, y, z)] = block
                bottomY = y

            depth = topY - bottomY
            col_bottom[(x, z)] = (bottomY, topY, r, localR)
            columns.append((x, z, topY, depth, r, localR))

    if decorate_underside:
        max_drip_r = max(0, round(diameter / 40))
        KEEP_OUT_MARGIN = 1
        eligible = columns

        n_drips = num_drips if num_drips is not None else max(3, int(len(eligible) * drip_density))

        len_floor = max(2, round(max_depth * 0.06))
        len_ceiling = max(len_floor + 2, round(max_depth * 0.4))

        rng.shuffle(eligible)
        for (x, z, topY, depth, r, localR) in eligible[:n_drips]:
            bottomY, _, _, _ = col_bottom[(x, z)]

            clearance = int(localR - r)
            local_max_r = max(0, min(max_drip_r, clearance - KEEP_OUT_MARGIN))
            drip_r_choices = list(range(0, local_max_r + 1))
            drip_r_weights = [3] + [1] * local_max_r if local_max_r > 0 else [1]
            drip_r = rng.choices(drip_r_choices, weights=drip_r_weights)[0]

            radius_frac = drip_r / max(1, max_drip_r)
            this_len_ceiling = len_floor + max(2, round((len_ceiling - len_floor) * radius_frac))
            this_len_ceiling = min(this_len_ceiling, len_ceiling)
            personal_cap = rng.randint(len_floor, this_len_ceiling)
            drip_len = rng.randint(len_floor, personal_cap)

            rise_frac = rng.uniform(0.08, 0.2)
            taper_power = rng.uniform(0.9, 1.4)
            # drips hang below the island's own deepest point, so they sit
            # at the pale end of the gradient, with the usual randomness
            for dl in range(drip_len):
                t = dl / max(1, drip_len - 1)
                radius = drip_r * _drip_radius_profile(t, rise_frac, taper_power)
                radius = max(0.0, min(radius, local_max_r))
                y = bottomY - dl
                ir = min(math.floor(radius), local_max_r)
                for dx in range(-ir, ir + 1):
                    for dz in range(-ir, ir + 1):
                        if dx * dx + dz * dz <= radius * radius:
                            block = pick_gradient(rng, 0.8 + 0.2 * t, jitter=rng.uniform(-0.6, 0.6))
                            blocks[(x + dx, y, z + dz)] = block

        # a few bare hanging dark "icicles" near the outer rim (replaces
        # island.py's draped vines)
        for (x, z, topY, depth, r, localR) in columns:
            if r / localR > 0.55 and rng.random() < 0.12:
                bottomY, _, _, _ = col_bottom[(x, z)]
                for vy in range(rng.randint(1, 3)):
                    blocks.setdefault((x, bottomY - vy, z), pick_gradient(rng, 0.9))

    if decorate_top:
        # a couple of small basalt columns (replaces island.py's trees)
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
    rng = random.Random(seed)
    blocks = {}

    blocks.update(generate_island(seed=seed, diameter=40, max_depth=16,
                                   num_drips=14, offset=(0, 90, 0)))

    satellite_specs = [
        dict(diameter=20, max_depth=9, num_drips=6, offset=(-42, 110, -10)),
        dict(diameter=16, max_depth=8, num_drips=5, offset=(30, 118, -28)),
    ]
    for i, spec in enumerate(satellite_specs):
        blocks.update(generate_island(seed=seed + 10 + i, **spec))

    for i in range(5):
        cx = rng.randint(-55, 55)
        cy = rng.randint(95, 130)
        cz = rng.randint(-40, 20)
        n = rng.randint(1, 4)
        for _ in range(n):
            dx, dy, dz = rng.randint(-1, 1), rng.randint(-1, 1), rng.randint(-1, 1)
            blocks[(cx + dx, cy + dy, cz + dz)] = "minecraft:blackstone"

    return blocks


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def blocks_to_structure(blocks):
    """Converts a {(x, y, z): "minecraft:block_id"} dict to the project's
    canonical Structure. See island.blocks_to_structure - identical logic."""
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
    "minecraft:blackstone": "#2b2626",
    "minecraft:obsidian": "#161022",
    "minecraft:deepslate": "#393a3d",
    "minecraft:basalt": "#4a484c",
    "minecraft:polished_basalt": "#5a5760",
    "minecraft:cobbled_deepslate": "#55565a",
    "minecraft:tuff": "#6a6b64",
}


def preview(structure, out_path="preview.png", title=None):
    """Renders the island as full shaded blocks and saves it to out_path."""
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
    ap = argparse.ArgumentParser(description="Generate a volcanic floating island for Minecraft.")
    ap.add_argument("--seed", type=int, default=1, help="random seed")
    ap.add_argument("--diameter", type=int, default=32,
                     help="top diameter of the island in blocks (default: 32)")
    ap.add_argument("--max-depth", type=int, default=None,
                     help="how far the rock tapers down below the top (default: scales with diameter)")
    ap.add_argument("--num-drips", type=int, default=None,
                     help="number of hanging basalt/magma drips (default: auto-scales with the "
                          "island's rim geometry - see --drip-density)")
    ap.add_argument("--drip-density", type=float, default=None,
                     help="fraction of eligible rim columns that grow a drip, used only when "
                          "--num-drips is not set (default: 0.05)")
    ap.add_argument("--decorate-top", action="store_true",
                     help="scatter small basalt columns on top (off by default)")
    ap.add_argument("--no-underside-decor", action="store_true",
                     help="disable drips on the underside")
    ap.add_argument("--out", type=str, default="volcano_island", help="output file prefix")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "out",
                     dest="out_dir",
                     help="directory for outputs (default: generate/out)")
    ap.add_argument("--scene", action="store_true",
                     help="generate a multi-island demo scene instead of a single island")
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
            num_drips=args.num_drips,
            decorate_top=args.decorate_top,
            decorate_underside=not args.no_underside_decor,
        )
        if args.drip_density is not None:
            kwargs["drip_density"] = args.drip_density
        blocks = generate_island(**kwargs)

    structure = blocks_to_structure(blocks)
    npz_path = structure.save(args.out_dir / f"{args.out}.npz")
    print(f"Wrote {len(blocks)} blocks to {npz_path}")

    title = (f"volcanic multi-island demo scene (seed={args.seed})" if args.scene
             else f"volcanic floating island (d={args.diameter}, seed={args.seed})")
    png_path = preview(structure, out_path=args.out_dir / f"{args.out}.png", title=title)
    print(f"Saved preview image to {png_path}")

    if args.schem:
        structure.to_schematic(args.out_dir, args.out)


if __name__ == "__main__":
    main()
