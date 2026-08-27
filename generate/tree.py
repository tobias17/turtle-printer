"""
Giant Epic Tree Generator (~350 blocks tall)
=============================================
Procedurally builds a voxel model of a colossal fantasy tree -- a few thick
roots that fork repeatedly as they plunge into the ground, a towering
trunk, and one continuous rolling "blanket" of canopy foliage draped over a
forking branch skeleton -- and:
  1) renders a preview image with matplotlib
  2) exports a real Minecraft .schem file (via mcschematic) you can paste
     with WorldEdit (`//schem load giant_tree` then `//paste`)

Grid generation is fully vectorized with numpy so it stays fast even at
this scale (the grid has tens of millions of cells).

Run:
    python3 giant_tree.py
Outputs:
    giant_tree_preview.png
    giant_tree.schem   (if mcschematic is installed: pip install mcschematic)
"""

import math
import time
import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import uniform_filter

RNG_SEED = 7
np.random.seed(RNG_SEED)

# ---------------------------------------------------------------------------
# Grid setup -- sized for a ~350 block tall tree with a sprawling canopy
# ---------------------------------------------------------------------------
AIR, WOOD, LEAVES, LEAVES_DARK, LEAVES_LIGHT, DIRT = 0, 1, 2, 4, 5, 3

SIZE_X, SIZE_Y, SIZE_Z = 680, 680, 400   # Z is "up" -- wide and short: ~350 tall, very broad
grid = np.zeros((SIZE_X, SIZE_Y, SIZE_Z), dtype=np.uint8)

CX, CY = SIZE_X // 2, SIZE_Y // 2

GROUND_Z = 4              # roots plunge down to roughly this height (no island slab)
ROOT_FLARE_TOP = 55       # trunk root-flare zone ends here
TRUNK_TOP_Z = 200         # trunk becomes canopy support above this
CANOPY_BASE_Z = 215       # vertical anchor the canopy blanket is built around
TOP_Z = 400               # overall model height (grid ceiling; canopy tops out ~350)


def bump_vec(theta, phi, seed, n=4, amp=1.0):
    """Vectorized cheap pseudo-noise (sum of sines over spherical angles) --
    numpy version of value-noise so no external noise library is needed."""
    rng = np.random.RandomState(seed)
    f1 = rng.uniform(1.5, 5.0, n)
    f2 = rng.uniform(1.5, 5.0, n)
    p1 = rng.uniform(0, math.tau, n)
    p2 = rng.uniform(0, math.tau, n)
    val = np.zeros_like(theta, dtype=np.float64)
    for k in range(n):
        val += np.sin(f1[k] * theta + p1[k]) * np.cos(f2[k] * phi + p2[k])
    return amp * val / n


def noise2d(X, Y, seed, n=5, base_freq=0.02, amp=1.0, freq_growth=1.8, amp_decay=0.55):
    """Fractal-ish 2D value noise built from a handful of randomly-oriented
    sine waves (Fourier synthesis). Used for the canopy's rolling 'blanket'
    surface -- no external noise library needed."""
    rng = np.random.RandomState(seed)
    val = np.zeros_like(X, dtype=np.float64)
    freq, a = base_freq, amp
    for _ in range(n):
        ang = rng.uniform(0, 2 * math.pi)
        kx, ky = math.cos(ang) * freq, math.sin(ang) * freq
        phase = rng.uniform(0, 2 * math.pi)
        val += a * np.sin(kx * X + ky * Y + phase)
        freq *= freq_growth
        a *= amp_decay
    return val


def edge_wave(theta, seed, n=5, amp=1.0):
    """1D angular noise for an organic (non-circular) footprint edge."""
    rng = np.random.RandomState(seed)
    val = np.zeros_like(theta, dtype=np.float64)
    for _ in range(n):
        f = rng.uniform(2, 7)
        p = rng.uniform(0, 2 * math.pi)
        val += np.sin(f * theta + p)
    return amp * val / n


def stamp_sphere(cx, cy, cz, r, block, noise_seed=None, noise_amp=0.0,
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
        rad = rad + bump_vec(theta, phi, noise_seed, amp=noise_amp)
    mask = dist <= rad
    sub = grid[x0:x1, y0:y1, z0:z1]
    if overwrite is not None:
        allowed = np.isin(sub, list(overwrite))
        mask &= allowed
    sub[mask] = block


def fill_tapered_column(z0, z1, radius_fn, block, noise_seed=None,
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
            rad = r + bump_vec(theta, np.full_like(theta, z * 0.04), noise_seed, amp=noise_amp)
        mask = dist <= rad
        grid[x0:x1, y0:y1, z][mask] = block


def _seed_mix(seed):
    return int(abs(seed)) % 2_000_000_000


def grow_limb_system(origin_z, n_primary, primary_radius, primary_length,
                      dive_dir, max_depth, seed_base, block=WOOD,
                      angle_jitter=0.12, child_range=(2, 3),
                      radius_shrink=(0.5, 0.68), length_shrink=(0.55, 0.78),
                      z_slope_range=(0.45, 0.7), wobble_amp=3.0,
                      tip_dirt=False, min_radius_to_fork=4.0,
                      fork_angle_spread=0.75, origin_xy=None):
    """Grows a branching limb system (used for both roots and support
    branches) as a handful of thick primaries that periodically fork into
    thinner children, tapering and wandering organically. dive_dir=-1 makes
    the limbs sink (roots), dive_dir=+1 makes them climb (branches)."""
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
            stamp_sphere(int(cur_x), int(cur_y), int(cur_z), last_r, block,
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
                stamp_sphere(int(cur_x), int(cur_y), int(cur_z), r2, block,
                             noise_seed=seed, noise_amp=0.6)
            if tip_dirt:
                stamp_sphere(int(cur_x), int(cur_y), int(cur_z) - 1, last_r * 0.7,
                             DIRT, noise_seed=_seed_mix(seed + 5), noise_amp=0.6,
                             overwrite={AIR})


t0 = time.time()

# ---------------------------------------------------------------------------
# 1) Roots: a handful of massive primary roots that fork repeatedly into
#    thinner children as they plunge into the ground -- no island slab.
# ---------------------------------------------------------------------------
def build_roots():
    grow_limb_system(
        origin_z=ROOT_FLARE_TOP - 6, n_primary=7, primary_radius=19.0,
        primary_length=85, dive_dir=-1, max_depth=3,
        seed_base=300, block=WOOD, angle_jitter=0.09,
        child_range=(2, 3), radius_shrink=(0.45, 0.62),
        length_shrink=(0.62, 0.85), z_slope_range=(0.1, 0.2),
        wobble_amp=4.0, tip_dirt=True, min_radius_to_fork=4.2,
        fork_angle_spread=0.85)


build_roots()
print(f"roots done  ({time.time() - t0:.1f}s)")

# ---------------------------------------------------------------------------
# 2) Trunk: huge flared buttress base rising into a long, tapering,
#    gnarled trunk.
# ---------------------------------------------------------------------------
def build_trunk():
    # Flare zone (buttress roots merging into trunk): wide at very bottom,
    # narrowing quickly.
    def flare_r(t):
        return 52.0 * (1 - t) ** 0.8 + 30.0 * t

    fill_tapered_column(ROOT_FLARE_TOP - 10, ROOT_FLARE_TOP + 12, flare_r,
                         WOOD, noise_seed=55, noise_amp=3.2)

    # Long tall trunk, gentle taper with gnarly bark noise.
    def trunk_r(t):
        return 37.0 * (1 - t) ** 0.55 + 19.0 * t

    fill_tapered_column(ROOT_FLARE_TOP + 12, TRUNK_TOP_Z, trunk_r,
                         WOOD, noise_seed=57, noise_amp=2.8)


build_trunk()
print(f"trunk done  ({time.time() - t0:.1f}s)")

# ---------------------------------------------------------------------------
# 3) Canopy: one continuous, rolling "blanket" of foliage draped over a
#    support pillar and a forking branch skeleton, instead of separate
#    leaf-ball clumps. Built as a height-field (top surface + bottom
#    surface per (x, y) column) with multi-octave noise for soft rolling
#    folds, so the silhouette reads as a single mass, like the reference.
# ---------------------------------------------------------------------------
def build_canopy():
    # Support pillar: solid wood core the blanket will drape over. Thicker
    # and taller now to hold up a much bigger mass of foliage.
    def crown_r(t):
        return 22.0 * (1 - t) + 10.0 * t

    fill_tapered_column(TRUNK_TOP_Z, min(SIZE_Z, CANOPY_BASE_Z + 45), crown_r,
                         WOOD, noise_seed=61, noise_amp=2.2)

    # Forking support branches -- wide-reaching but shallow-climbing, since
    # the canopy above them is now broad rather than tall.
    grow_limb_system(
        origin_z=TRUNK_TOP_Z + 15, n_primary=13, primary_radius=19.0,
        primary_length=95, dive_dir=1, max_depth=2,
        seed_base=1200, block=WOOD, angle_jitter=0.12,
        child_range=(2, 3), radius_shrink=(0.55, 0.72),
        length_shrink=(0.55, 0.72), z_slope_range=(0.14, 0.24),
        wobble_amp=5.0, tip_dirt=False, min_radius_to_fork=4.5,
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

    footprint_r = R + edge_wave(theta, seed=901, n=5, amp=34)
    inside = r <= footprint_r
    r_norm = np.clip(r / np.maximum(footprint_r, 1e-6), 0, 1)
    taper = 1 - 0.45 * r_norm

    dome = 120.0 * np.cos(r_norm * math.pi / 2) ** 0.5
    grand_noise = noise2d(X, Y, seed=905, n=3, base_freq=0.028, amp=8) * taper        # ~225 blk folds
    top_noise = noise2d(X, Y, seed=910, n=4, base_freq=0.10, amp=6) * taper           # ~63 blk folds
    top_noise += noise2d(X, Y, seed=911, n=4, base_freq=0.42, amp=4)                  # ~15 blk clumps
    top_noise += noise2d(X, Y, seed=912, n=3, base_freq=1.35, amp=1.8)                # ~5 blk roughness
    top_z = CANOPY_BASE_Z + dome + grand_noise + top_noise

    thickness = 30.0 + 118.0 * np.exp(-((r_norm - 0.4) / 0.4) ** 2)
    bottom_noise = noise2d(X, Y, seed=920, n=4, base_freq=0.11, amp=12)
    bottom_noise += noise2d(X, Y, seed=921, n=3, base_freq=0.5, amp=4)
    bottom_z = top_z - thickness + bottom_noise

    top_i = np.clip(np.round(top_z).astype(int), 0, SIZE_Z - 1)
    bottom_i = np.clip(np.round(bottom_z).astype(int), 0, SIZE_Z - 1)

    # Per-column leaf "tone": a mottled mix of normal / darker foliage, plus
    # a lighter sun-facing highlight near the very top surface -- gives the
    # canopy a rich, painterly, multi-toned look instead of flat green.
    tone_noise = noise2d(X, Y, seed=930, n=3, base_freq=0.3, amp=1.0)
    dark_tone = tone_noise < -0.12
    highlight_tone = noise2d(X, Y, seed=931, n=3, base_freq=0.35, amp=1.0) > 0.35

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


build_canopy()
print(f"canopy done ({time.time() - t0:.1f}s)")

counts = {name: int((grid == val).sum())
          for name, val in [("air", AIR), ("wood", WOOD),
                             ("leaves", LEAVES), ("leaves_dark", LEAVES_DARK),
                             ("leaves_light", LEAVES_LIGHT), ("dirt", DIRT)]}
nz = np.nonzero(grid)
print(f"bounding box height: z {nz[2].min()} to {nz[2].max()} "
      f"= {nz[2].max() - nz[2].min()} blocks tall")
print("Voxel counts (solid):", counts)
print(f"total generation time: {time.time() - t0:.1f}s")

# ---------------------------------------------------------------------------
# Render preview with matplotlib BEFORE hollowing -- the outward silhouette
# is identical either way, but downsampling a hollowed grid can skip thin
# shell voxels and create fake-looking holes, so we snapshot the look first.
# ---------------------------------------------------------------------------
COLORS = {
    WOOD: "#5b3a1e",
    LEAVES: "#3f7a30",
    LEAVES_DARK: "#274d1c",
    LEAVES_LIGHT: "#8fc153",
    DIRT: "#5a3d22",
}
BLOCK_IDS = [WOOD, LEAVES, LEAVES_DARK, LEAVES_LIGHT, DIRT]


def aa_downsample(g, target_max_dim):
    """Anti-aliased downsample for preview rendering: box-filter (average)
    occupancy and per-block-type fraction BEFORE subsampling, so the fine
    surface texture is band-limited into a coherent lower-res shape instead
    of aliasing into a noisy checkerboard. Naive point-sampling (grid[::k])
    looks wrong AND is extremely slow to render, because the aliased
    checkerboard defeats matplotlib's hidden-face culling -- almost every
    voxel ends up with an exposed neighbor even deep in the interior."""
    factor = max(1, max(g.shape) // target_max_dim)
    occ = (g != AIR).astype(np.float32)
    occ_smooth = uniform_filter(occ, size=factor, mode="constant")
    sub = tuple(slice(factor // 2, None, factor) for _ in range(3))
    filled = occ_smooth[sub] > 0.5

    best_id = np.zeros(filled.shape, dtype=np.uint8)
    best_frac = np.zeros(filled.shape, dtype=np.float32)
    for bid in BLOCK_IDS:
        frac = uniform_filter((g == bid).astype(np.float32), size=factor, mode="constant")[sub]
        better = frac > best_frac
        best_frac = np.where(better, frac, best_frac)
        best_id = np.where(better, bid, best_id)
    best_id = np.where(filled, best_id, AIR)

    colors = np.empty(best_id.shape, dtype=object)
    for block, hexcolor in COLORS.items():
        colors[best_id == block] = hexcolor
    return filled, colors, factor


def render_iso(filled, colors, path="giant_tree_preview.png"):
    fig = plt.figure(figsize=(13, 15))
    ax = fig.add_subplot(111, projection="3d")
    ax.voxels(filled, facecolors=colors, edgecolor=None, shade=True)
    ax.set_box_aspect(filled.shape)
    ax.set_axis_off()
    ax.view_init(elev=11, azim=-55)
    plt.tight_layout(pad=0)
    fig.savefig(path, dpi=170, facecolor="#bfe3ff")
    plt.close(fig)
    print("Saved render to", path)


def render_scale_view(filled, colors, factor, elev, azim, path, tick_step=50):
    """Orthographic-feeling side/front view with a height ruler (real block
    units) planted next to the tree, so foreshortening from the isometric
    angle can't make the scale misleading."""
    nz = np.nonzero(filled)
    z_max_idx = int(nz[2].max()) if len(nz[2]) else filled.shape[2]
    real_h = z_max_idx * factor

    fig = plt.figure(figsize=(13, 15))
    ax = fig.add_subplot(111, projection="3d")
    ax.voxels(filled, facecolors=colors, edgecolor=None, shade=True)

    # Ruler: a vertical line beside the tree with tick marks every
    # `tick_step` real blocks, labeled in actual block units.
    ruler_x = -filled.shape[0] * 0.12
    ruler_y = filled.shape[1] / 2
    ax.plot([ruler_x, ruler_x], [ruler_y, ruler_y], [0, z_max_idx],
            color="black", linewidth=1.5)
    for real_z in range(0, real_h + 1, tick_step):
        zi = real_z / factor
        ax.plot([ruler_x - filled.shape[0] * 0.02, ruler_x + filled.shape[0] * 0.02],
                [ruler_y, ruler_y], [zi, zi], color="black", linewidth=1.2)
        ax.text(ruler_x - filled.shape[0] * 0.07, ruler_y, zi, f"{real_z}",
                fontsize=9, ha="right", va="center")

    ax.set_box_aspect(filled.shape)
    ax.set_axis_off()
    ax.view_init(elev=elev, azim=azim)
    ax.set_title(f"actual height: {real_h} blocks", fontsize=13)
    plt.tight_layout(pad=0)
    fig.savefig(path, dpi=170, facecolor="#bfe3ff")
    plt.close(fig)
    print("Saved", path, "| measured height:", real_h, "blocks")


filled, colors, factor = aa_downsample(grid, target_max_dim=100)
render_iso(filled, colors)
render_scale_view(filled, colors, factor, elev=0, azim=-90, path="giant_tree_side.png")
render_scale_view(filled, colors, factor, elev=0, azim=0, path="giant_tree_front.png")

# ---------------------------------------------------------------------------
# Hollow out fully-buried interior voxels. A solid blob this size is almost
# entirely invisible interior -- removing it keeps the shape identical from
# the outside but cuts the block count (and WorldEdit paste time) hugely.
# HOLLOW_SHELL = how many layers of solid blocks to keep from the surface in.
# ---------------------------------------------------------------------------
HOLLOW_SHELL = 2


def hollow_out(shell=HOLLOW_SHELL):
    """Binary-erode the solid mask `shell` times (6-connectivity). What's
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


removed_n = hollow_out()
print(f"hollowed out {removed_n} buried interior voxels")
counts_after = {name: int((grid == val).sum())
                for name, val in [("air", AIR), ("wood", WOOD),
                                   ("leaves", LEAVES), ("leaves_dark", LEAVES_DARK),
                                   ("leaves_light", LEAVES_LIGHT), ("dirt", DIRT)]}
print("Voxel counts (after hollowing):", counts_after)

# ---------------------------------------------------------------------------
# Export a real Minecraft .schem file
# ---------------------------------------------------------------------------
def export_schematic(path_folder=".", name="giant_tree"):
    try:
        import mcschematic
    except ImportError:
        print("mcschematic not installed -- run `pip install mcschematic` to "
              "get a real .schem file for WorldEdit.")
        return

    block_map = {
        WOOD: "minecraft:oak_log",
        LEAVES: "minecraft:oak_leaves[persistent=true]",
        LEAVES_DARK: "minecraft:dark_oak_leaves[persistent=true]",
        LEAVES_LIGHT: "minecraft:birch_leaves[persistent=true]",
        DIRT: "minecraft:dirt",
    }

    schem = mcschematic.MCSchematic()
    xs, ys, zs = np.nonzero(grid)
    n = len(xs)
    for idx in range(n):
        x, y, z = int(xs[idx]), int(ys[idx]), int(zs[idx])
        block = block_map.get(int(grid[x, y, z]))
        if block:
            # mcschematic axes are (x, y, z) with y = up -> map our z to y
            schem.setBlock((x, z, y), block)

    schem.save(path_folder, name, mcschematic.Version.JE_1_20_1)
    print(f"Saved {name}.schem to {path_folder} "
          f"({n} blocks) -- load it in-game with WorldEdit: "
          f"//schem load {name}  then  //paste")


export_schematic()
print(f"all done ({time.time() - t0:.1f}s)")
