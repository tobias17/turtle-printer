"""
Shared machinery for the floating-island generators in generate/islands/
(grass.py, volcano.py, and other biome variants).

Every island theme follows the same recipe: an irregular radial silhouette,
a flat (or gently rolling) top, a tapering rocky body carved straight down
per column, optional hanging "drip" stalactites on the underside, and
optional decoration scattered on top. What differs per theme is purely
*which blocks* get used at each stage - so that's what lives here, and each
theme file only supplies block-picking callbacks plus whatever genuinely
unique decoration it wants (trees, cacti, crystals, mushrooms, ...).

Don't duplicate this machinery in a theme file - if a new theme needs a
tweak to the shared carve/drip loop itself (not just different blocks),
extend the functions here with a new parameter rather than forking them.
"""

import argparse
import math
import random
import sys
from pathlib import Path

import numpy as np

# generate/utils.py lives one directory up from generate/islands/ - add it
# to sys.path so `from utils import ...` resolves regardless of whether this
# module is run directly or imported by a sibling theme script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import Atlas, Structure, render_screenshot, value_noise_2d  # noqa: E402

__all__ = [
    "Atlas", "Structure", "render_screenshot", "value_noise_2d",
    "weighted_choice", "grid_dims", "drip_radius_profile", "carve_columns",
    "generate_drips", "decorate_rim_underside", "basic_scene",
    "blocks_to_structure", "preview", "build_arg_parser", "run_cli",
]


# ---------------------------------------------------------------------------
# Small generic helpers
# ---------------------------------------------------------------------------

def weighted_choice(rng, weighted_options):
    """Picks a value from [(value, weight), ...]; weights need not sum to 1."""
    total = sum(w for _, w in weighted_options)
    roll = rng.random() * total
    acc = 0.0
    for value, w in weighted_options:
        acc += w
        if roll <= acc:
            return value
    return weighted_options[-1][0]


def grid_dims(diameter):
    """The (size, half, radius) triple every island theme's grid uses,
    derived purely from diameter. Shared so a theme needing extra noise
    fields (sized to line up with carve_columns' grid) can compute them
    before calling carve_columns, without re-deriving this formula."""
    radius = diameter / 2.0
    size = int(radius * 2 + 6)
    half = size // 2
    return size, half, radius


def drip_radius_profile(t, rise_frac, taper_power):
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


# ---------------------------------------------------------------------------
# Shared silhouette + taper carve
# ---------------------------------------------------------------------------

def carve_columns(seed, diameter, top_thickness_range, max_depth, flat_top,
                   top_block_fn, body_block_fn, bottom_face_fn=None,
                   silhouette_amp=(0.015, 0.045), edge_amp_frac=0.05,
                   taper_amp_frac=0.08, taper_strength=0.85, taper_exponent=0.6):
    """Shared irregular-silhouette + tapering carve loop used by every
    island theme (island.py's original main loop, generalized).

    top_block_fn(rng, x, z, xi, zi) -> block for the single topY voxel.
    body_block_fn(rng, x, z, xi, zi, y_offset, thickness, total_depth) ->
        block for each voxel below the top, y_offset in [1, total_depth].
    bottom_face_fn(rng, blocks, x, z, bottomY, r, localR), optional ->
        called once per column after carving, for theme-specific touches on
        the very bottom face (e.g. island.py's occasional moss cap).

    Returns (blocks, col_bottom, columns, rng, size, half, radius):
      columns   - list of (x, z, topY, depth, r, localR)
      col_bottom - {(x, z): (bottomY, topY, r, localR)}
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    size, half, radius = grid_dims(diameter)

    def grid_for(cell_blocks, minimum=6):
        return max(minimum, size // cell_blocks)

    k_max = max(6, 4 + int(diameter / 16))

    # Irregular radial silhouette (a few sine harmonics -> lumpy circle,
    # not a perfect disc)
    thetas = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    R = np.full(360, float(radius))
    for k in range(2, k_max):
        amp = radius * np_rng.uniform(*silhouette_amp) / math.sqrt(k_max / 6)
        phase = np_rng.uniform(0, 2 * np.pi)
        R += amp * np.sin(k * thetas + phase)
    R = np.clip(R, radius * 0.55, None)

    edge_noise = value_noise_2d(size, grid_for(5), seed + 1) * (radius * edge_amp_frac)
    hill_noise = value_noise_2d(size, grid_for(6), seed + 2)
    taper_noise = value_noise_2d(size, grid_for(4, 8), seed + 3) * (radius * taper_amp_frac)
    thickness_noise = value_noise_2d(size, grid_for(6), seed + 5)

    min_thick, max_thick = top_thickness_range

    blocks = {}
    col_bottom = {}
    columns = []
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

            blocks[(x, topY, z)] = top_block_fn(rng, x, z, xi, zi)

            # Carve everything below the top in one continuous taper. The
            # allowed radius shrinks starting right after the top block
            # (only that single voxel is guaranteed full-width), so the
            # crust band tapers in too instead of standing as a vertical
            # wall down to where the deeper material starts.
            total_depth = (thickness - 1) + max_depth
            jitter = taper_noise[xi, zi]
            bottomY = topY
            for y_offset in range(1, total_depth + 1):
                t = y_offset / total_depth
                allowed_r = localR * (1 - taper_strength * (t ** taper_exponent)) + jitter
                if y_offset > 1 and r > max(allowed_r, 0):
                    break
                y = topY - y_offset
                block = body_block_fn(rng, x, z, xi, zi, y_offset, thickness, total_depth)
                blocks[(x, y, z)] = block
                bottomY = y

            depth = topY - bottomY
            col_bottom[(x, z)] = (bottomY, topY, r, localR)
            columns.append((x, z, topY, depth, r, localR))

            if bottom_face_fn is not None:
                bottom_face_fn(rng, blocks, x, z, bottomY, r, localR)

    return blocks, col_bottom, columns, rng, size, half, radius


# ---------------------------------------------------------------------------
# Shared underside decoration
# ---------------------------------------------------------------------------

DRIP_SUPPORT_TOLERANCE = 3  # blocks of ordinary rock-surface unevenness to ignore


def _drip_support_radius(col_bottom, x, z, bottom_y, max_r):
    """How far a drip anchored at (x, z) can flare out before its cap
    would sit under a spot the carved rock doesn't reach anywhere near - a
    missing neighbor column, or one whose own rock stops well above this
    anchor's bottomY - which reads as the drip's wide top hanging over
    nothing instead of growing out of solid stone.

    Only checked in the outward arc (away from the island's center at the
    origin), with a few blocks of tolerance: the carved cone gets shallower
    as you move away from center as a normal, continuous feature of the
    taper (typically by close to a block of depth per block of horizontal
    distance), so demanding neighbors be no shallower at all - or checking
    a full ring instead of just outward - flags that constantly and leaves
    every drip a bare single-column toothpick. The real problem case is an
    anchor sitting at a distinctly deeper spike/pocket than what's
    immediately outward of it (e.g. a lone column near the tapered tip, or
    a sharp dip from edge/taper noise), which this still catches because
    moving further outward from an already-thin point runs out of rock
    fast, well past ordinary unevenness.
    """
    if max_r <= 0:
        return 0
    r_from_center = math.hypot(x, z)
    base_angle = math.atan2(z, x) if r_from_center > 1e-6 else 0.0
    r = 0
    for test_r in range(1, max_r + 1):
        ok = True
        for offset_deg in range(-60, 61, 20):
            rad = base_angle + math.radians(offset_deg)
            nx = round(x + test_r * math.cos(rad))
            nz = round(z + test_r * math.sin(rad))
            nb = col_bottom.get((nx, nz))
            if nb is None or nb[0] > bottom_y + DRIP_SUPPORT_TOLERANCE:
                ok = False
                break
        if not ok:
            break
        r = test_r
    return r


def generate_drips(rng, blocks, columns, col_bottom, diameter, max_depth,
                    num_drips, drip_density, drip_block_fn,
                    max_drip_r_fn=None, after_drip_fn=None):
    """Shared hanging-drip decoration loop (island.py's stalactite roots).

    drip_block_fn(rng, t, is_tip) -> block for each filled voxel in a drip,
        t in [0, 1] fraction along the drip's length.
    max_drip_r_fn(diameter) -> int, optional override for the max drip
        radius (default: island.py's `round(diameter / 40)`).
    after_drip_fn(rng, blocks, x, tip_y, z), optional -> called once per
        generated drip with the position just past its tip, for
        theme-specific extras (e.g. island.py's occasional trailing vine).

    Mutates `blocks` in place; returns nothing.
    """
    max_drip_r = max_drip_r_fn(diameter) if max_drip_r_fn else max(0, round(diameter / 40))
    KEEP_OUT_MARGIN = 1  # a radius-N drip needs N+1 blocks of clearance
    # Anchors this shallow are right at the island's tapered-out rim - too
    # thin a perch for even a slim drip to read as growing out of the rock
    # rather than out of a single stray crust block.
    MIN_ANCHOR_DEPTH = 2
    eligible = [c for c in columns if c[3] >= MIN_ANCHOR_DEPTH]

    n_drips = num_drips if num_drips is not None else max(3, int(len(eligible) * drip_density))

    len_floor = max(2, round(max_depth * 0.06))
    len_ceiling = max(len_floor + 2, round(max_depth * 0.4))

    rng.shuffle(eligible)
    for (x, z, topY, depth, r, localR) in eligible[:n_drips]:
        bottomY, _, _, _ = col_bottom[(x, z)]

        # Keep-out zone: a drip of radius N must stay at least N blocks
        # (plus margin) from the true edge. Cap this drip's radius by how
        # much clearance its own column actually has.
        clearance = int(localR - r)
        local_max_r = max(0, min(max_drip_r, clearance - KEEP_OUT_MARGIN))
        local_max_r = min(local_max_r, _drip_support_radius(col_bottom, x, z, bottomY, local_max_r))
        drip_r_choices = list(range(0, local_max_r + 1))
        drip_r_weights = [3] + [1] * local_max_r if local_max_r > 0 else [1]
        drip_r = rng.choices(drip_r_choices, weights=drip_r_weights)[0]

        # Length scales with thickness so thin drips don't read as
        # unnaturally long toothpicks.
        radius_frac = drip_r / max(1, max_drip_r)
        this_len_ceiling = len_floor + max(2, round((len_ceiling - len_floor) * radius_frac))
        this_len_ceiling = min(this_len_ceiling, len_ceiling)
        personal_cap = rng.randint(len_floor, this_len_ceiling)
        drip_len = rng.randint(len_floor, personal_cap)

        rise_frac = rng.uniform(0.08, 0.2)
        taper_power = rng.uniform(0.9, 1.4)
        for dl in range(drip_len):
            t = dl / max(1, drip_len - 1)
            radius = drip_r * drip_radius_profile(t, rise_frac, taper_power)
            radius = max(0.0, min(radius, local_max_r))
            y = bottomY - dl
            is_tip = t > 0.8
            ir = min(math.floor(radius), local_max_r)
            for dx in range(-ir, ir + 1):
                for dz in range(-ir, ir + 1):
                    if dx * dx + dz * dz <= radius * radius:
                        blocks[(x + dx, y, z + dz)] = drip_block_fn(rng, t, is_tip)

        if after_drip_fn is not None:
            after_drip_fn(rng, blocks, x, bottomY - drip_len, z)


def decorate_rim_underside(rng, blocks, columns, col_bottom, rim_block_fn,
                            r_frac_threshold=0.55, chance=0.18, length_range=(2, 6)):
    """Shared thin-decoration-draped-from-the-rim loop (island.py's vines,
    volcano.py's bare icicles, etc). Skips columns whose bottom face is
    already the deepest point elsewhere near the true rim."""
    lo, hi = length_range
    for (x, z, topY, depth, r, localR) in columns:
        if r / localR > r_frac_threshold and rng.random() < chance:
            bottomY, _, _, _ = col_bottom[(x, z)]
            for vy in range(rng.randint(lo, hi)):
                blocks.setdefault((x, bottomY - vy, z), rim_block_fn(rng))


# ---------------------------------------------------------------------------
# Shared multi-island scene composition
# ---------------------------------------------------------------------------

def basic_scene(seed, generate_island_fn, debris_block,
                 main_kwargs=None, satellite_specs=None,
                 debris_bounds=((-55, 55), (95, 130), (-40, 20)), debris_count=5):
    """One big island plus a couple of smaller satellites and tiny floating
    debris chunks (island.py's original demo composition, themeable)."""
    rng = random.Random(seed)
    blocks = {}

    main_kwargs = main_kwargs or dict(diameter=40, max_depth=16, num_drips=14, offset=(0, 90, 0))
    blocks.update(generate_island_fn(seed=seed, **main_kwargs))

    satellite_specs = satellite_specs if satellite_specs is not None else [
        dict(diameter=20, max_depth=9, num_drips=6, offset=(-42, 110, -10)),
        dict(diameter=16, max_depth=8, num_drips=5, offset=(30, 118, -28)),
    ]
    for i, spec in enumerate(satellite_specs):
        blocks.update(generate_island_fn(seed=seed + 10 + i, **spec))

    (xlo, xhi), (ylo, yhi), (zlo, zhi) = debris_bounds
    for i in range(debris_count):
        cx = rng.randint(xlo, xhi)
        cy = rng.randint(ylo, yhi)
        cz = rng.randint(zlo, zhi)
        n = rng.randint(1, 4)
        for _ in range(n):
            dx, dy, dz = rng.randint(-1, 1), rng.randint(-1, 1), rng.randint(-1, 1)
            blocks[(cx + dx, cy + dy, cz + dz)] = debris_block

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

def preview(structure, block_colors, out_path="preview.png", title=None):
    """Renders the island as full shaded blocks and saves it to out_path.
    `block_colors` is a {block_name: "#rrggbb"} dict, theme-specific."""
    palette = {
        name: (
            int(color.lstrip("#")[0:2], 16) / 255.0,
            int(color.lstrip("#")[2:4], 16) / 255.0,
            int(color.lstrip("#")[4:6], 16) / 255.0,
        )
        for name, color in block_colors.items()
    }
    return render_screenshot(structure, out_path, title=title, palette=palette)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser(description, out_default, num_drips_help, decorate_top_help,
                      no_underside_help="disable drips/decoration on the underside"):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--seed", type=int, default=1, help="random seed")
    ap.add_argument("--diameter", type=int, default=32,
                     help="top diameter of the island in blocks (default: 32)")
    ap.add_argument("--max-depth", type=int, default=None,
                     help="how far the rock tapers down below the top (default: scales with diameter)")
    ap.add_argument("--num-drips", type=int, default=None, help=num_drips_help)
    ap.add_argument("--drip-density", type=float, default=None,
                     help="fraction of eligible rim columns that grow a drip, used only when "
                          "--num-drips is not set (default: 0.05)")
    ap.add_argument("--decorate-top", action="store_true", help=decorate_top_help)
    ap.add_argument("--no-underside-decor", action="store_true", help=no_underside_help)
    ap.add_argument("--out", type=str, default=out_default, help="output file prefix")
    ap.add_argument("--out-dir", type=Path, default=None, dest="out_dir",
                     help="directory for outputs (default: generate/out)")
    ap.add_argument("--scene", action="store_true",
                     help="generate a multi-island demo scene instead of a single island")
    ap.add_argument("--schem", action="store_true",
                     help="also export a .schem for WorldEdit (requires mcschematic)")
    return ap


def run_cli(description, out_default, generate_island_fn, generate_scene_fn,
            block_colors, single_title_fn, scene_title_fn,
            num_drips_help=("number of hanging drips (default: auto-scales with the island's "
                             "rim geometry - see --drip-density)"),
            decorate_top_help="scatter decoration on top (off by default so it stays buildable)"):
    """Full CLI entry point shared by every theme's main(): parses args,
    generates either a single island or a demo scene, exports the .npz +
    preview PNG (+ optional .schem)."""
    ap = build_arg_parser(description, out_default, num_drips_help, decorate_top_help)
    args = ap.parse_args()
    out_dir = args.out_dir if args.out_dir is not None else Path(__file__).resolve().parent.parent / "out"

    if args.scene:
        blocks = generate_scene_fn(seed=args.seed)
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
        blocks = generate_island_fn(**kwargs)

    structure = blocks_to_structure(blocks)
    npz_path = structure.save(out_dir / f"{args.out}.npz")
    print(f"Wrote {len(blocks)} blocks to {npz_path}")

    title = scene_title_fn(args.seed) if args.scene else single_title_fn(args.diameter, args.seed)
    png_path = preview(structure, block_colors, out_path=out_dir / f"{args.out}.png", title=title)
    print(f"Saved preview image to {png_path}")

    if args.schem:
        structure.to_schematic(out_dir, args.out)
