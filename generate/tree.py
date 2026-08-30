"""
Giant Epic Tree Generator (~350 blocks tall)
=============================================
Procedurally builds a voxel model of a colossal fantasy tree -- a towering
trunk that simply cuts off cleanly at the bottom (there's no ground to
root into -- it's floating in the void), and one continuous rolling
"blanket" of canopy foliage draped over a forking branch skeleton.

Grid generation is fully vectorized with numpy so it stays fast even at
this scale (the grid has tens of millions of cells).

Usage:
    python tree.py                 # generate + preview with the default seed
    python tree.py --seed 7        # different random variation
    python tree.py --schem         # also export a .schem for WorldEdit

Outputs (into --out-dir, default generate/output/tmp):
    <out>.npz            canonical Structure (for the future printer pipeline)
    <out>_preview.png    isometric preview
    <out>_side.png       side view with a height ruler
    <out>_front.png      front view with a height ruler
    <out>.schem          WorldEdit schematic (only with --schem, if
                          mcschematic is installed)
"""

import argparse
import math
import time
from pathlib import Path

import numpy as np

from utils import Atlas, Structure, render_screenshot, fractal_noise_2d, angular_noise_1d, spherical_bump_noise

# ---------------------------------------------------------------------------
# Grid setup -- sized for a ~350 block tall tree with a sprawling canopy
# ---------------------------------------------------------------------------
AIR, WOOD, LEAVES, LEAVES_DARK, LEAVES_LIGHT = 0, 1, 2, 3, 4

SIZE_X, SIZE_Y, SIZE_Z = 680, 680, 400   # Z is "up" -- wide and short: spans most of the 400 height
CX, CY = SIZE_X // 2, SIZE_Y // 2

BASE_BOTTOM_Z = 0         # trunk runs down to (nominally) the very bottom of the grid
TRUNK_TOP_Z = 243         # trunk becomes canopy support above this
CANOPY_BASE_Z = 263       # vertical anchor the canopy blanket is built around

BLOCK_NAMES = {
    WOOD: "minecraft:oak_log",
    LEAVES: "minecraft:oak_leaves[persistent=true]",
    LEAVES_DARK: "minecraft:dark_oak_leaves[persistent=true]",
    LEAVES_LIGHT: "minecraft:birch_leaves[persistent=true]",
}

BLOCK_COLORS = {
    "minecraft:oak_log": "#5b3a1e",
    "minecraft:oak_leaves[persistent=true]": "#3f7a30",
    "minecraft:dark_oak_leaves[persistent=true]": "#274d1c",
    "minecraft:birch_leaves[persistent=true]": "#8fc153",
}


def stamp_sphere(grid, cx, cy, cz, r, block, noise_seed=None, noise_amp=0.0,
                  overwrite=None, squash_z=1.0):
    """Vectorized: fill a (optionally noisy, optionally squashed) blob into
    the grid. squash_z < 1 flattens the blob vertically."""
    ir = int(math.ceil(r + noise_amp)) + 1
    x0, x1 = max(0, cx - ir), min(SIZE_X, cx + ir + 1)
    y0, y1 = max(0, cy - ir), min(SIZE_Y, cy + ir + 1)
    z0, z1 = max(0, cz - ir), min(SIZE_Z, cz + ir + 1)
    if x0 >= x1 or y0 >= y1 or z0 >= z1:
        return
    xs = (np.arange(x0, x1) - cx).astype(np.float64)
    ys = (np.arange(y0, y1) - cy).astype(np.float64)
    zs = (np.arange(z0, z1) - cz).astype(np.float64) / squash_z
    dx, dy, dz = np.meshgrid(xs, ys, zs, indexing="ij")
    dist = np.sqrt(dx * dx + dy * dy + dz * dz)
    rad = np.full_like(dist, r)
    if noise_seed is not None:
        safe = np.where(dist > 0, dist, 1)
        theta = np.arctan2(dy, dx)
        phi = np.arcsin(np.clip(dz / safe, -1, 1))
        rad = rad + spherical_bump_noise(theta, phi, noise_seed, amp=noise_amp)
    mask = dist <= rad
    sub = grid[x0:x1, y0:y1, z0:z1]
    if overwrite is not None:
        allowed = np.isin(sub, list(overwrite))
        mask &= allowed
    sub[mask] = block


def fill_tapered_column(grid, z0, z1, radius_fn, block, noise_seed=None,
                         noise_amp=0.0, cx=CX, cy=CY):
    """Vectorized per-layer fill for the trunk: at each z, fill a disc whose
    radius (and bark noise) is computed from radius_fn(t)."""
    for z in range(z0, z1):
        t = (z - z0) / max(1, (z1 - z0))
        r = radius_fn(t)
        ir = int(math.ceil(r + noise_amp)) + 1
        x0, x1 = max(0, cx - ir), min(SIZE_X, cx + ir + 1)
        y0, y1 = max(0, cy - ir), min(SIZE_Y, cy + ir + 1)
        xs = (np.arange(x0, x1) - cx).astype(np.float64)
        ys = (np.arange(y0, y1) - cy).astype(np.float64)
        dx, dy = np.meshgrid(xs, ys, indexing="ij")
        dist = np.sqrt(dx * dx + dy * dy)
        rad = r
        if noise_seed is not None:
            theta = np.arctan2(dy, dx)
            rad = r + spherical_bump_noise(theta, np.full_like(theta, z * 0.04), noise_seed, amp=noise_amp)
        mask = dist <= rad
        grid[x0:x1, y0:y1, z][mask] = block


def _seed_mix(seed):
    return int(abs(seed)) % 2_000_000_000


def grow_limb_system(grid, origin_z, n_primary, primary_radius, primary_length,
                      dive_dir, max_depth, seed_base, block=WOOD,
                      angle_jitter=0.12, child_range=(2, 3),
                      radius_shrink=(0.5, 0.68), length_shrink=(0.55, 0.78),
                      z_slope_range=(0.45, 0.7), wobble_amp=3.0,
                      min_radius_to_fork=4.0,
                      fork_angle_spread=0.75, origin_xy=None):
    """Grows a branching limb system (used for the canopy's support
    branches) as a handful of thick primaries that periodically fork into
    thinner children, tapering and wandering organically. dive_dir=-1 makes
    the limbs sink, dive_dir=+1 makes them climb (branches)."""
    ox, oy = origin_xy if origin_xy else (float(CX), float(CY))
    stack = []
    for i in range(n_primary):
        angle = (i / n_primary) * math.tau + np.random.uniform(-0.1, 0.1)
        stack.append(dict(
            x=ox, y=oy, z=float(origin_z), angle=angle,
            z_slope=np.random.uniform(*z_slope_range),
            radius=primary_radius * np.random.uniform(0.85, 1.15),
            length=primary_length * np.random.uniform(0.85, 1.15),
            depth=0, seed=_seed_mix(seed_base + i * 97 + 1)))

    while stack:
        seg = stack.pop()
        cur_x, cur_y, cur_z = seg["x"], seg["y"], seg["z"]
        cur_angle = seg["angle"]
        z_slope, radius, length = seg["z_slope"], seg["radius"], seg["length"]
        depth, seed = seg["depth"], seg["seed"]

        steps = max(5, int(length / 3.0))
        last_r = radius
        for s in range(steps):
            t = s / steps
            step_len = length / steps
            cur_angle += np.random.uniform(-angle_jitter, angle_jitter)
            cur_x += math.cos(cur_angle) * step_len
            cur_y += math.sin(cur_angle) * step_len
            cur_z += dive_dir * z_slope * step_len * (0.5 + 0.9 * t)
            cur_z += math.sin(t * 6 + seed % 97) * wobble_amp * 0.3
            # gentle taper (down to ~50% of starting radius) -- segments stay
            # thick enough at their end to plausibly fork; a fine tapered
            # point is only added afterwards for tips that don't fork.
            last_r = max(1.4, radius * (1 - 0.5 * t))
            stamp_sphere(grid, int(cur_x), int(cur_y), int(cur_z), last_r, block,
                         noise_seed=seed, noise_amp=1.1)

        if depth < max_depth and last_r > min_radius_to_fork:
            n_children = np.random.randint(child_range[0], child_range[1] + 1)
            for c in range(n_children):
                side = 1 if c % 2 == 0 else -1
                spread = fork_angle_spread * side * np.random.uniform(0.6, 1.2)
                child_angle = cur_angle + spread + np.random.uniform(-0.15, 0.15)
                stack.append(dict(
                    x=cur_x, y=cur_y, z=cur_z, angle=child_angle,
                    z_slope=z_slope * np.random.uniform(0.8, 1.3),
                    radius=radius * np.random.uniform(*radius_shrink),
                    length=length * np.random.uniform(*length_shrink),
                    depth=depth + 1, seed=_seed_mix(seed * 13 + c + 1)))
        else:
            # terminal tip: taper the rest of the way down to a fine point
            stub_len = max(8.0, last_r * 3.0)
            stub_steps = 8
            for s2 in range(stub_steps):
                t2 = s2 / stub_steps
                step_len2 = stub_len / stub_steps
                cur_angle += np.random.uniform(-angle_jitter, angle_jitter)
                cur_x += math.cos(cur_angle) * step_len2
                cur_y += math.sin(cur_angle) * step_len2
                cur_z += dive_dir * z_slope * step_len2 * 0.6
                r2 = max(0.8, last_r * (1 - t2))
                stamp_sphere(grid, int(cur_x), int(cur_y), int(cur_z), r2, block,
                             noise_seed=seed, noise_amp=0.6)


# ---------------------------------------------------------------------------
# 1) Trunk: a long, tapering, gnarled trunk running the full height of the
#    tree, down to a clean cutoff at the very bottom of the grid -- no
#    flare, no roots, no dirt, just more trunk going into the void.
# ---------------------------------------------------------------------------
def build_trunk(grid):
    def trunk_r(t):
        return 37.0 * (1 - t) ** 0.55 + 19.0 * t

    fill_tapered_column(grid, BASE_BOTTOM_Z, TRUNK_TOP_Z, trunk_r,
                         WOOD, noise_seed=57, noise_amp=2.8)


# ---------------------------------------------------------------------------
# 3) Canopy: one continuous, rolling "blanket" of foliage draped over a
#    support pillar and a forking branch skeleton, instead of separate
#    leaf-ball clumps. Built as a height-field (top surface + bottom
#    surface per (x, y) column) with multi-octave noise for soft rolling
#    folds, so the silhouette reads as a single mass.
# ---------------------------------------------------------------------------
def build_canopy(grid):
    # Support pillar: solid wood core the blanket will drape over. Thicker
    # and taller now to hold up a much bigger mass of foliage.
    def crown_r(t):
        return 22.0 * (1 - t) + 10.0 * t

    fill_tapered_column(grid, TRUNK_TOP_Z, min(SIZE_Z, CANOPY_BASE_Z + 20), crown_r,
                         WOOD, noise_seed=61, noise_amp=2.2)

    # Forking support branches -- wide-reaching but shallow-climbing, since
    # the canopy above them is now broad rather than tall. Kept well clear
    # of the canopy blanket's top surface (see top_z below) so the branch
    # tips stay buried in foliage instead of poking out above it.
    grow_limb_system(
        grid, origin_z=TRUNK_TOP_Z + 5, n_primary=13, primary_radius=19.0,
        primary_length=80, dive_dir=1, max_depth=2,
        seed_base=1200, block=WOOD, angle_jitter=0.12,
        child_range=(2, 3), radius_shrink=(0.55, 0.72),
        length_shrink=(0.55, 0.72), z_slope_range=(0.08, 0.13),
        wobble_amp=5.0, min_radius_to_fork=4.5,
        fork_angle_spread=0.5)

    # --- The blanket itself -------------------------------------------------
    # Wider than ever, but shallower in the vertical -- a huge, broad,
    # umbrella-like mass instead of a tall dome, matching the ~350-block
    # total height target while still feeling massive.
    R = 240.0                 # base footprint radius before edge noise
    bounds = int(R + 80)
    x0, x1 = max(0, CX - bounds), min(SIZE_X, CX + bounds + 1)
    y0, y1 = max(0, CY - bounds), min(SIZE_Y, CY + bounds + 1)
    xs = (np.arange(x0, x1) - CX).astype(np.float64)
    ys = (np.arange(y0, y1) - CY).astype(np.float64)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    r = np.sqrt(X * X + Y * Y)
    theta = np.arctan2(Y, X)

    footprint_r = R + angular_noise_1d(theta, seed=901, n=5, amp=34)
    inside = r <= footprint_r
    r_norm = np.clip(r / np.maximum(footprint_r, 1e-6), 0, 1)
    taper = 1 - 0.45 * r_norm

    dome = 65.0 * np.cos(r_norm * math.pi / 2) ** 0.5
    grand_noise = fractal_noise_2d(X, Y, seed=905, n=3, base_freq=0.028, amp=8) * taper        # ~225 blk folds
    top_noise = fractal_noise_2d(X, Y, seed=910, n=4, base_freq=0.10, amp=6) * taper           # ~63 blk folds
    top_noise += fractal_noise_2d(X, Y, seed=911, n=4, base_freq=0.42, amp=4)                  # ~15 blk clumps
    top_noise += fractal_noise_2d(X, Y, seed=912, n=3, base_freq=1.35, amp=1.8)                # ~5 blk roughness
    top_z = CANOPY_BASE_Z + dome + grand_noise + top_noise

    thickness = 22.0 + 60.0 * np.exp(-((r_norm - 0.4) / 0.4) ** 2)
    bottom_noise = fractal_noise_2d(X, Y, seed=920, n=4, base_freq=0.11, amp=12)
    bottom_noise += fractal_noise_2d(X, Y, seed=921, n=3, base_freq=0.5, amp=4)
    bottom_z = top_z - thickness + bottom_noise

    top_i = np.clip(np.round(top_z).astype(int), 0, SIZE_Z - 1)
    bottom_i = np.clip(np.round(bottom_z).astype(int), 0, SIZE_Z - 1)

    # Per-column leaf "tone": a mottled mix of normal / darker foliage, plus
    # a lighter sun-facing highlight near the very top surface -- gives the
    # canopy a rich, painterly, multi-toned look instead of flat green.
    tone_noise = fractal_noise_2d(X, Y, seed=930, n=3, base_freq=0.3, amp=1.0)
    dark_tone = tone_noise < -0.12
    highlight_tone = fractal_noise_2d(X, Y, seed=931, n=3, base_freq=0.35, amp=1.0) > 0.35

    if inside.any():
        z_lo = int(bottom_i[inside].min())
        z_hi = int(top_i[inside].max())
        for z in range(z_lo, z_hi + 1):
            mask = inside & (z >= bottom_i) & (z <= top_i)
            if not mask.any():
                continue
            layer = grid[x0:x1, y0:y1, z]
            mask &= (layer == AIR)   # don't swallow the wood branches/pillar
            near_top = mask & (top_i - z <= 5) & highlight_tone
            dark = mask & ~near_top & dark_tone
            normal = mask & ~near_top & ~dark
            layer[near_top] = LEAVES_LIGHT
            layer[dark] = LEAVES_DARK
            layer[normal] = LEAVES


# ---------------------------------------------------------------------------
# Hollowing -- a solid blob this size is almost entirely invisible interior;
# removing it keeps the shape identical from the outside but cuts the block
# count (and WorldEdit paste time / printer travel) hugely.
# ---------------------------------------------------------------------------
def hollow_out(grid, shell):
    """Binary-erodes the solid mask `shell` times (6-connectivity). What's
    left after eroding is the deeply-buried core -- delete just that, which
    leaves a `shell`-thick solid crust identical in outward shape."""
    core = grid != AIR
    for _ in range(shell):
        pad = np.pad(core, 1, mode="constant", constant_values=False)
        core = (
            pad[2:, 1:-1, 1:-1] & pad[:-2, 1:-1, 1:-1] &
            pad[1:-1, 2:, 1:-1] & pad[1:-1, :-2, 1:-1] &
            pad[1:-1, 1:-1, 2:] & pad[1:-1, 1:-1, :-2] & core
        )
    grid[core] = AIR
    return int(core.sum())


# ---------------------------------------------------------------------------
# Generation entry point
# ---------------------------------------------------------------------------
def generate_tree(seed=7):
    """Builds the full (unhollowed) tree voxel grid and returns it (dtype
    uint8, using the module's AIR/WOOD/LEAVES/... internal ids).

    Deliberately does NOT hollow the grid -- hollowing removes buried
    interior voxels, and downsampling a hollowed grid for preview can skip
    thin shell voxels and create fake-looking holes. Call hollow_out()
    separately, after rendering the preview, once the full-detail grid is
    no longer needed for anything but export."""
    np.random.seed(seed)
    grid = np.zeros((SIZE_X, SIZE_Y, SIZE_Z), dtype=np.uint8)

    t0 = time.time()
    build_trunk(grid)
    print(f"trunk done  ({time.time() - t0:.1f}s)")
    build_canopy(grid)
    print(f"canopy done ({time.time() - t0:.1f}s)")

    counts = {name: int((grid == val).sum())
              for name, val in [("air", AIR), ("wood", WOOD), ("leaves", LEAVES),
                                 ("leaves_dark", LEAVES_DARK), ("leaves_light", LEAVES_LIGHT)]}
    nz = np.nonzero(grid)
    print(f"bounding box height: z {nz[2].min()} to {nz[2].max()} "
          f"= {nz[2].max() - nz[2].min()} blocks tall")
    print("Voxel counts (solid):", counts)
    print(f"total generation time: {time.time() - t0:.1f}s")
    return grid


def grid_to_structure(grid):
    """Converts the internal uint8 grid (AIR/WOOD/LEAVES/... ids) into the
    project's canonical Structure, via an Atlas that maps those ids
    directly onto real Minecraft block names."""
    atlas = Atlas()
    for internal_id in sorted(BLOCK_NAMES):
        idx = atlas.add(BLOCK_NAMES[internal_id])
        assert idx == internal_id, "BLOCK_NAMES ids must register in atlas in the same order as the grid's own ids"
    # This module's own grid is (X, Y, Z) with Z (axis 2) vertical, but the
    # Structure/Atlas contract is Y (axis 1) vertical -- swap here, once, at
    # the boundary, so everything downstream (render_screenshot, .npz, the
    # future printer pipeline) can rely on one consistent convention.
    return Structure.from_data(grid.transpose(0, 2, 1), atlas)


def preview(structure, out_dir, out_name, title=None):
    """Renders an isometric preview plus side/front views with a height
    ruler (useful at this scale, where foreshortening can be misleading)."""
    palette = {
        name: (
            int(color.lstrip("#")[0:2], 16) / 255.0,
            int(color.lstrip("#")[2:4], 16) / 255.0,
            int(color.lstrip("#")[4:6], 16) / 255.0,
        )
        for name, color in BLOCK_COLORS.items()
    }
    views = [
        dict(suffix="_preview", elev=11, azim=-55),
        dict(suffix="_side", elev=0, azim=-90, ruler=True),
        dict(suffix="_front", elev=0, azim=0, ruler=True),
    ]
    return render_screenshot(structure, out_dir / f"{out_name}.png", title=title, palette=palette, views=views)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate a giant fantasy tree for Minecraft.")
    ap.add_argument("--seed", type=int, default=7, help="random seed")
    ap.add_argument("--hollow-shell", type=int, default=2,
                     help="how many layers of solid blocks to keep from the surface in "
                          "(0 disables hollowing)")
    ap.add_argument("--schem", action="store_true",
                     help="also export a .schem for WorldEdit (requires mcschematic)")
    ap.add_argument("--out", type=str, default="giant_tree", help="output file prefix")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "output" / "tmp",
                     dest="out_dir", help="directory for outputs (default: generate/output/tmp - "
                                           "this is a standalone dev-iteration render, not a "
                                           "canonical output)")
    args = ap.parse_args()

    grid = generate_tree(seed=args.seed)
    structure = grid_to_structure(grid)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Render BEFORE hollowing -- the outward silhouette is identical either
    # way, but downsampling a hollowed grid can skip thin shell voxels and
    # create fake-looking holes, so we snapshot the look first.
    preview(structure, args.out_dir, args.out, title=f"giant tree (seed={args.seed})")

    if args.hollow_shell > 0:
        removed_n = hollow_out(structure.data, args.hollow_shell)
        print(f"hollowed out {removed_n} buried interior voxels")

    npz_path = structure.save(args.out_dir / f"{args.out}.npz")
    print(f"Wrote structure to {npz_path}")

    if args.schem:
        structure.to_schematic(args.out_dir, args.out)


if __name__ == "__main__":
    main()
