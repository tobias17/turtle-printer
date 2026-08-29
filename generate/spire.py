"""
Sauron's Spire Generator (~150 blocks tall)
=============================================
Procedurally builds a voxel model of a colossal dark-lord tower: a tall,
mostly-circular black-stone shaft with a single continuous taper (no
lips or overhanging platforms) wrapped by a raised ridge that spirals up
the whole height like a walkable staircase, hollow all the way up
(floors threaded by a ladder shaft) so there's a huge amount of hidden
interior space to build in. It's topped by a crown of four black claw
pillars, one at each cardinal direction, reaching up beside a
placeholder orange-wool orb (stand-in for a future draconic energy core).

The exterior is deliberately left with no doorway or other opening --
it should read as a solid, seamless tower from outside; the hollow
interior is reached via the ladder shaft from the hatch at the top,
under the crown.

The tower is deliberately built with a flat, un-flared bottom -- it's
meant to be planted on top of a separately-generated floating island (see
island.py), not rooted into the ground.

The hollow interior is a genuine usable space, not just an optimization:
the exterior has no real windows, so nothing about the interior is
visible from outside and it doesn't need to look pretty -- the only
vantage point on it is standing inside it in-game.

Grid generation is fully vectorized with numpy -- one pass per Z layer,
with the X/Y work inside each layer vectorized -- so it stays fast even at
this scale.

Usage:
    python spire.py                 # generate + preview with the default seed
    python spire.py --seed 3        # different random variation
    python spire.py --schem         # also export a .schem for WorldEdit

Outputs (into --out-dir, default generate/out):
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

from utils import Atlas, Structure, render_screenshot, spherical_bump_noise

# ---------------------------------------------------------------------------
# Grid setup -- sized for a ~160 block tall spire with clawed crown spikes
# ---------------------------------------------------------------------------
(AIR, WALL, FLOOR, LADDER, SPIKE, ORB) = range(6)

SIZE_X, SIZE_Y, SIZE_Z = 140, 140, 200   # Z is "up" internally, swapped to Y at export
CX, CY = SIZE_X // 2, SIZE_Y // 2

# --- shaft profile: ONE continuous taper (each segment's r0 matches the
# previous segment's r1 -- no radius jumps, so there's no flat "lip" ring
# anywhere). The tiered/staircase look instead comes from a helical ridge
# (STAIR_PITCH/STAIR_AMP below) that spirals up the surface, rather than
# from the taper itself stepping down.
# ---------------------------------------------------------------------------
WALL_THICK = 3
N_RIDGES = 6
RIDGE_AMP = 0.05   # kept low so the shaft reads as circular, just a hint of fluting

TIERS = [
    dict(z0=0,   z1=15,  r0=21.6, r1=18.0),   # foundation -- flat-bottomed, sits on the island
    dict(z0=15,  z1=45,  r0=18.0, r1=14.0),
    dict(z0=45,  z1=71,  r0=14.0, r1=11.0),
    dict(z0=71,  z1=93,  r0=11.0, r1=9.0),
    dict(z0=93,  z1=115, r0=9.0,  r1=7.5),
]
SHAFT_TOP = TIERS[-1]["z1"]

# a raised ridge that spirals up the shaft like a walkable staircase: it
# completes one full revolution every STAIR_PITCH blocks of height, and
# sticks out STAIR_AMP blocks at the start of each turn, tapering back to
# 0 by the end of that turn (a sawtooth in the helical phase) -- small
# enough relative to WALL_THICK to never threaten the interior wall
STAIR_PITCH = 23.0
STAIR_AMP = 2.5

# --- interior -----------------------------------------------------------
GROUND_FLOOR_Z = 3
FLOOR_THICK = 2
FLOOR_SPACING = 16
TOP_FLOOR_MARGIN = 6       # last mid-floor sits this far below SHAFT_TOP, doubling as the roof
HOLE_HALF = 1               # floor/collar hatch is a (2*HOLE_HALF+1) square around the ladder

# --- crown / eye ----------------------------------------------------------
COLLAR_Z0, COLLAR_Z1 = SHAFT_TOP, SHAFT_TOP + 4
COLLAR_R = TIERS[-1]["r1"] + 5.5
EYE_R = 7.0                     # placeholder orb radius -- orange wool for now
GAP_TO_ORB = 8.0                # air gap kept between the major claw tips and the orb's surface
EYE_CENTER_Z = COLLAR_Z1 + 19

BLOCK_NAMES = {
    WALL: "minecraft:blackstone",
    FLOOR: "minecraft:polished_blackstone_bricks",
    LADDER: "minecraft:ladder[facing=west]",
    SPIKE: "minecraft:polished_basalt",
    ORB: "minecraft:orange_wool",
}

BLOCK_COLORS = {
    "minecraft:blackstone": "#2b2530",
    "minecraft:polished_blackstone_bricks": "#221e26",
    "minecraft:ladder[facing=west]": "#4a3320",
    "minecraft:polished_basalt": "#3a3640",
    "minecraft:orange_wool": "#d2691e",
}


# ---------------------------------------------------------------------------
# Small stamp helper (spikes, eye) -- adapted from tree.py's stamp_sphere
# ---------------------------------------------------------------------------
def stamp_sphere(grid, cx, cy, cz, r, block, seed=None, noise_amp=0.0):
    """Vectorized: fill a (optionally noisy) blob into the grid."""
    ir = int(math.ceil(r + noise_amp)) + 1
    x0, x1 = max(0, cx - ir), min(SIZE_X, cx + ir + 1)
    y0, y1 = max(0, cy - ir), min(SIZE_Y, cy + ir + 1)
    z0, z1 = max(0, cz - ir), min(SIZE_Z, cz + ir + 1)
    if x0 >= x1 or y0 >= y1 or z0 >= z1:
        return
    xs = (np.arange(x0, x1) - cx).astype(np.float64)
    ys = (np.arange(y0, y1) - cy).astype(np.float64)
    zs = (np.arange(z0, z1) - cz).astype(np.float64)
    dx, dy, dz = np.meshgrid(xs, ys, zs, indexing="ij")
    dist = np.sqrt(dx * dx + dy * dy + dz * dz)
    rad = np.full_like(dist, r)
    if seed is not None:
        safe = np.where(dist > 0, dist, 1)
        theta = np.arctan2(dy, dx)
        phi = np.arcsin(np.clip(dz / safe, -1, 1))
        rad = rad + spherical_bump_noise(theta, phi, seed, amp=noise_amp)
    mask = dist <= rad
    grid[x0:x1, y0:y1, z0:z1][mask] = block


def build_spike(grid, x0, y0, z0, ang_xy, tilt0_deg, tilt1_deg, length, r0, block, seed):
    """Marches a straight-ish tapering spike outward from (x0, y0, z0).
    `ang_xy` is the horizontal direction (radians) it points outward along;
    `tilt` is the angle from vertical (0 = straight up, 90 = horizontal),
    interpolated tilt0 -> tilt1 over the spike's length so it can start
    leaning outward and straighten (or curl inward) toward the tip.
    Returns the spike's tip position (int x, y, z), so callers can place a
    decoration exactly at the point without re-deriving the path."""
    # step spacing kept well under the minimum radius floor below, so
    # consecutive stamped spheres always overlap -- otherwise a diagonal
    # step between two thin (radius ~1) samples near the tip can leave an
    # uncovered voxel, since a radius-1 sphere has no diagonal fill
    steps = max(10, math.ceil(length / 0.75))
    x, y, z = float(x0), float(y0), float(z0)
    for s in range(steps):
        t = s / steps
        tilt = math.radians(tilt0_deg + (tilt1_deg - tilt0_deg) * t)
        step_len = length / steps
        dx = math.sin(tilt) * math.cos(ang_xy)
        dy = math.sin(tilt) * math.sin(ang_xy)
        dz = math.cos(tilt)
        x += dx * step_len
        y += dy * step_len
        z += dz * step_len
        r = max(1.3, r0 * (1 - t) ** 1.2)
        # tiny noise_amp: smooth tapering horn/claw, not a scribbled blob
        stamp_sphere(grid, int(round(x)), int(round(y)), int(round(z)), r, block,
                     seed=seed, noise_amp=0.15)
    return int(round(x)), int(round(y)), int(round(z))


def build_spike_to(grid, x0, y0, z0, tx, ty, tz, r0, block, seed, bow=5.0):
    """Marches a tapering claw from (x0,y0,z0) that's guaranteed to land
    exactly on the target point (tx,ty,tz) -- a straight line bowed
    outward at the midpoint (quadratic, `bow` blocks at t=0.5, zero at
    both ends) so it reads as a claw curling in to grip something at the
    target, rather than a floating gap between the spike and its target."""
    dx0, dy0, dz0 = tx - x0, ty - y0, tz - z0
    length = math.sqrt(dx0 * dx0 + dy0 * dy0 + dz0 * dz0)
    # same overlap-guaranteeing spacing as build_spike above
    steps = max(10, math.ceil(length / 0.75))
    ang = math.atan2(y0 - CY, x0 - CX) if (x0 != CX or y0 != CY) else 0.0
    ox, oy = math.cos(ang), math.sin(ang)
    x = y = z = 0.0
    for s in range(steps + 1):
        t = s / steps
        bow_amt = bow * 4 * t * (1 - t)
        x = x0 + dx0 * t + ox * bow_amt
        y = y0 + dy0 * t + oy * bow_amt
        z = z0 + dz0 * t
        r = max(1.3, r0 * (1 - t) ** 1.1 + 0.6)
        stamp_sphere(grid, int(round(x)), int(round(y)), int(round(z)), r, block,
                     seed=seed, noise_amp=0.15)
    return int(round(x)), int(round(y)), int(round(z))


# ---------------------------------------------------------------------------
# Shaft radius profile -- piecewise linear taper within each tier, stepping
# straight down to the next. TIERS are contiguous in Z (checked by
# _validate_profile below), so every z in [0, SHAFT_TOP) hits exactly one.
# ---------------------------------------------------------------------------
def outer_radius(z):
    for tier in TIERS:
        if tier["z0"] <= z < tier["z1"]:
            t = (z - tier["z0"]) / (tier["z1"] - tier["z0"])
            return tier["r0"] * (1 - t) + tier["r1"] * t
    return TIERS[0]["r0"] if z < 0 else TIERS[-1]["r1"]


def _validate_profile():
    bounds = sorted(TIERS, key=lambda seg: seg["z0"])
    for a, b in zip(bounds, bounds[1:]):
        assert a["z1"] == b["z0"], f"gap/overlap in shaft profile between {a} and {b}"


_validate_profile()


def hollow_radius(z):
    return max(0.0, outer_radius(z) - WALL_THICK)


def ladder_xy(z):
    """The ladder shaft hugs the interior wall (1 block clear of it) on
    the +X side, tracking the taper so it's always adjacent to solid wall."""
    r = max(2.0, hollow_radius(z) - 1.0)
    return CX + int(round(r)), CY


FLOOR_ZS = list(range(GROUND_FLOOR_Z + FLOOR_THICK + FLOOR_SPACING, SHAFT_TOP - TOP_FLOOR_MARGIN, FLOOR_SPACING))
_top_fz = SHAFT_TOP - TOP_FLOOR_MARGIN
if not FLOOR_ZS or _top_fz - FLOOR_ZS[-1] > FLOOR_SPACING // 2:
    FLOOR_ZS.append(_top_fz)
else:
    FLOOR_ZS[-1] = _top_fz


# ---------------------------------------------------------------------------
# 1) Base + shaft: fluted tapering tower, hollowed out with floors and a
#    ladder shaft. No exterior openings -- reads as a solid tower from
#    outside; the interior is reached via the ladder hatch under the crown.
# ---------------------------------------------------------------------------
def build_tower(grid, seed):
    for z in range(0, SHAFT_TOP):
        r_out = outer_radius(z)
        r_in = hollow_radius(z)
        ir = int(math.ceil(r_out * (1 + RIDGE_AMP))) + 4
        x0, x1 = max(0, CX - ir), min(SIZE_X, CX + ir + 1)
        y0, y1 = max(0, CY - ir), min(SIZE_Y, CY + ir + 1)
        xs = (np.arange(x0, x1) - CX).astype(np.float64)
        ys = (np.arange(y0, y1) - CY).astype(np.float64)
        dx, dy = np.meshgrid(xs, ys, indexing="ij")
        dist = np.sqrt(dx * dx + dy * dy)
        theta = np.arctan2(dy, dx)

        # sharpened cosine (sign * |cos|^0.6) gives flatter plateaus and
        # crisper peaks than a plain sinusoid -- reads as chunky pilaster
        # buttresses rather than smooth fluting
        c = np.cos(N_RIDGES * theta + seed * 0.7)
        ridge = 1.0 + RIDGE_AMP * np.sign(c) * np.abs(c) ** 0.6
        # small amp: fine stone-block roughness, not enough to blur the
        # tiered/buttress silhouette into a melted-looking blob
        boundary = r_out * ridge + spherical_bump_noise(
            theta, np.full_like(theta, z * 0.03), seed + 7, n=6, amp=0.35)

        # spiral staircase ridge: a sawtooth in the helical phase (z blended
        # with angle) so the raised tread winds continuously up around the
        # shaft instead of forming a flat ring at one height. Growing with
        # phase (not shrinking) matters: the bulge must be narrowest right
        # after each riser and widen going up to it, so the flat landing at
        # the top of each turn has solid material directly underneath it
        # (a step you can stand on) instead of overhanging empty air.
        stair_phase = ((z - STAIR_PITCH * (theta / (2 * np.pi))) % STAIR_PITCH) / STAIR_PITCH
        boundary = boundary + STAIR_AMP * stair_phase

        layer = grid[x0:x1, y0:y1, z]
        solid = dist <= boundary
        layer[solid] = WALL

        if z < GROUND_FLOOR_Z + FLOOR_THICK:
            if z >= GROUND_FLOOR_Z:
                layer[dist <= r_in] = FLOOR   # solid ground floor, no hatch -- seals the bottom
            continue

        layer[dist <= r_in] = AIR

        on_floor = False
        for fz in FLOOR_ZS:
            if fz <= z < fz + FLOOR_THICK:
                layer[dist <= r_in] = FLOOR
                on_floor = True
                break

        lx, ly = ladder_xy(z)
        if on_floor:
            hx0, hx1 = max(0, lx - HOLE_HALF - x0), min(x1 - x0, lx + HOLE_HALF + 1 - x0)
            hy0, hy1 = max(0, ly - HOLE_HALF - y0), min(y1 - y0, ly + HOLE_HALF + 1 - y0)
            layer[hx0:hx1, hy0:hy1] = AIR
        grid[lx, ly, z] = LADDER


# ---------------------------------------------------------------------------
# 2) Crown: a solid collar platform (roof of the shaft, floor of the top
#    chamber) ringed with tapering black spikes -- most short, four tall
#    ones reaching up around the eye.
# ---------------------------------------------------------------------------
def build_crown(grid, seed):
    for z in range(COLLAR_Z0, COLLAR_Z1):
        ir = int(math.ceil(COLLAR_R)) + 2
        x0, x1 = max(0, CX - ir), min(SIZE_X, CX + ir + 1)
        y0, y1 = max(0, CY - ir), min(SIZE_Y, CY + ir + 1)
        xs = (np.arange(x0, x1) - CX).astype(np.float64)
        ys = (np.arange(y0, y1) - CY).astype(np.float64)
        dx, dy = np.meshgrid(xs, ys, indexing="ij")
        dist = np.sqrt(dx * dx + dy * dy)
        grid[x0:x1, y0:y1, z][dist <= COLLAR_R] = WALL

    # ladder hatch punched straight up through the collar to an open landing
    lx, ly = ladder_xy(SHAFT_TOP - 1)
    grid[lx - HOLE_HALF: lx + HOLE_HALF + 1, ly - HOLE_HALF: ly + HOLE_HALF + 1, COLLAR_Z0:COLLAR_Z1] = AIR
    for z in range(COLLAR_Z0, COLLAR_Z1):
        grid[lx, ly, z] = LADDER

    rng = np.random.RandomState(seed + 900)
    n_minor, n_major = 10, 4
    # offset by a fixed 9 degrees (plus small jitter) so none of the 10 minor
    # spikes lands on top of a major pillar -- 10 and 4 both divide 360, so
    # without this offset two of them (at 0 deg/East and 180 deg/West) sit
    # right against a major pillar and read as one doubled-up spike
    minor_angles = [(2 * math.pi * i / n_minor) + math.radians(9) + rng.uniform(-0.05, 0.05)
                     for i in range(n_minor)]
    # major pillars sit exactly at the four cardinal (N/S/E/W) directions, no jitter
    major_angles = [i * math.pi / 2 for i in range(n_major)]

    for i, ang in enumerate(minor_angles):
        bx = CX + int(round((COLLAR_R - 3) * math.cos(ang)))
        by = CY + int(round((COLLAR_R - 3) * math.sin(ang)))
        build_spike(grid, bx, by, COLLAR_Z1 - 2, ang, 58, 34, 13.0, 2.6, SPIKE, seed=seed + 30 + i)

    # major pillars: each one is aimed at a point held GAP_TO_ORB blocks off
    # the orb's own surface (rather than an independent tilt path), so the
    # gap between pillar tip and orb is controlled directly instead of being
    # a side effect of the tilt/length numbers.
    beta = math.radians(90)   # polar angle from the orb's top pole; 90 = its equator (comes up beside it)
    target_r = EYE_R + GAP_TO_ORB
    for i, ang in enumerate(major_angles):
        bx = CX + int(round((COLLAR_R + 1) * math.cos(ang)))
        by = CY + int(round((COLLAR_R + 1) * math.sin(ang)))
        tx = CX + target_r * math.sin(beta) * math.cos(ang)
        ty = CY + target_r * math.sin(beta) * math.sin(ang)
        tz = EYE_CENTER_Z + target_r * math.cos(beta)
        build_spike_to(grid, bx, by, COLLAR_Z1 - 2, tx, ty, tz, 3.4, SPIKE, seed=seed + 60 + i)


# ---------------------------------------------------------------------------
# 3) The eye: a placeholder orb -- solid orange wool, no shading/detail yet.
# ---------------------------------------------------------------------------
def build_eye(grid, seed, center_z):
    stamp_sphere(grid, CX, CY, center_z, EYE_R, ORB)


# ---------------------------------------------------------------------------
# Hollowing -- erosion-based cleanup of buried voxels left in solid parts
# (wall crust, collar, spikes, the eye) after the deliberate interior carve
# above. Purely an optimization: identical outward shape, fewer blocks.
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
def generate_spire(seed=3):
    np.random.seed(seed)
    grid = np.zeros((SIZE_X, SIZE_Y, SIZE_Z), dtype=np.uint8)

    t0 = time.time()
    build_tower(grid, seed)
    print(f"tower done ({time.time() - t0:.1f}s)")
    build_crown(grid, seed)
    print(f"crown done ({time.time() - t0:.1f}s)")
    build_eye(grid, seed, center_z=EYE_CENTER_Z)
    print(f"eye done ({time.time() - t0:.1f}s)")

    counts = {name: int((grid == internal_id).sum()) for internal_id, name in BLOCK_NAMES.items()}
    nz = np.nonzero(grid)
    print(f"bounding box height: z {nz[2].min()} to {nz[2].max()} "
          f"= {nz[2].max() - nz[2].min()} blocks tall")
    print("Voxel counts (solid):", counts)
    print(f"total generation time: {time.time() - t0:.1f}s")
    return grid


def grid_to_structure(grid):
    """Converts the internal uint8 grid (WALL/FLOOR/EYE_.../... ids) into
    the project's canonical Structure, via an Atlas that maps those ids
    directly onto real Minecraft block names."""
    atlas = Atlas()
    for internal_id in sorted(BLOCK_NAMES):
        idx = atlas.add(BLOCK_NAMES[internal_id])
        assert idx == internal_id, "BLOCK_NAMES ids must register in atlas in the same order as the grid's own ids"
    # This module's own grid is (X, Y, Z) with Z (axis 2) vertical, but the
    # Structure/Atlas contract is Y (axis 1) vertical -- swap here, once, at
    # the boundary.
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
    ap = argparse.ArgumentParser(description="Generate a Lord of the Rings-style dark spire for Minecraft.")
    ap.add_argument("--seed", type=int, default=3, help="random seed")
    ap.add_argument("--hollow-shell", type=int, default=2,
                     help="how many layers of solid blocks to keep from the surface in "
                          "(0 disables hollowing)")
    ap.add_argument("--schem", action="store_true",
                     help="also export a .schem for WorldEdit (requires mcschematic)")
    ap.add_argument("--out", type=str, default="spire", help="output file prefix")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "out",
                     dest="out_dir", help="directory for outputs (default: generate/out)")
    args = ap.parse_args()

    grid = generate_spire(seed=args.seed)
    structure = grid_to_structure(grid)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Render BEFORE hollowing -- the outward silhouette is identical either
    # way, but the erosion pass below only ever removes fully-buried
    # (already invisible) voxels, so the preview stays accurate.
    preview(structure, args.out_dir, args.out, title=f"sauron's spire (seed={args.seed})")

    if args.hollow_shell > 0:
        removed_n = hollow_out(structure.data, args.hollow_shell)
        print(f"hollowed out {removed_n} buried interior voxels")

    npz_path = structure.save(args.out_dir / f"{args.out}.npz")
    print(f"Wrote structure to {npz_path}")

    if args.schem:
        structure.to_schematic(args.out_dir, args.out)


if __name__ == "__main__":
    main()
