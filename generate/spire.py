"""
Sauron's Spire Generator (~150 blocks tall)
=============================================
Procedurally builds a voxel model of a colossal dark-lord tower: a tall,
mostly-circular black-concrete shaft with a single continuous taper (no
lips or overhanging platforms) wrapped by a raised ridge that spirals up
the whole height like a walkable staircase, hollow all the way up (one
open shaft, no floors or ladder inside) so there's a huge amount of
hidden interior space to build in. It's topped by a crown of four claw
pillars, one at each cardinal direction, reaching up beside a
placeholder orange-wool orb (stand-in for a future draconic energy core).

The exterior is deliberately left with no doorway or other opening --
it should read as a solid, seamless tower from outside. The interior is
one continuous open shaft top to bottom with no floors or ladder to reach
it - build/access is left entirely up to whatever's placed inside later.

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

from utils import Atlas, Structure, render_screenshot, spherical_bump_noise

# ---------------------------------------------------------------------------
# Grid setup -- sized for a ~160 block tall spire with clawed crown spikes,
# scaled up 1.5x diameter / 1.2x height (DIAM_SCALE/HEIGHT_SCALE below)
# ---------------------------------------------------------------------------
(AIR, WALL, ORB) = range(3)

DIAM_SCALE = 1.5   # multiplies every radius in the profile below
HEIGHT_SCALE = 1.2  # multiplies every Z (height) value in the profile below

SIZE_X, SIZE_Y = round(140 * DIAM_SCALE), round(140 * DIAM_SCALE)
SIZE_Z = round(200 * HEIGHT_SCALE)   # Z is "up" internally, swapped to Y at export
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

# Base (unscaled) profile, scaled by DIAM_SCALE (radii) / HEIGHT_SCALE
# (heights) below. Z boundaries are scaled as a shared, once-rounded list
# rather than independently per tier, so consecutive tiers still line up
# exactly after rounding (see _validate_profile) instead of leaving a
# rounding gap/overlap between them.
_BASE_TIERS = [
    dict(z0=0,   z1=15,  r0=21.6, r1=18.0),   # foundation -- flat-bottomed, sits on the island
    dict(z0=15,  z1=45,  r0=18.0, r1=14.0),
    dict(z0=45,  z1=71,  r0=14.0, r1=11.0),
    dict(z0=71,  z1=93,  r0=11.0, r1=9.0),
    dict(z0=93,  z1=115, r0=9.0,  r1=7.5),
]
_boundaries = sorted({t["z0"] for t in _BASE_TIERS} | {t["z1"] for t in _BASE_TIERS})
_scaled_boundaries = [round(b * HEIGHT_SCALE) for b in _boundaries]
TIERS = [
    dict(z0=_scaled_boundaries[i], z1=_scaled_boundaries[i + 1],
         r0=t["r0"] * DIAM_SCALE, r1=t["r1"] * DIAM_SCALE)
    for i, t in enumerate(_BASE_TIERS)
]
SHAFT_TOP = TIERS[-1]["z1"]

# a raised ridge that spirals up the shaft like a walkable staircase: it
# completes one full revolution every STAIR_PITCH blocks of height, and
# sticks out STAIR_AMP blocks at the start of each turn, tapering back to
# 0 by the end of that turn (a sawtooth in the helical phase) -- small
# enough relative to WALL_THICK to never threaten the interior wall
STAIR_PITCH = 23.0
STAIR_AMP = 2.5

# --- crown / eye ----------------------------------------------------------
COLLAR_Z0, COLLAR_Z1 = SHAFT_TOP, SHAFT_TOP + round(4 * HEIGHT_SCALE)
# the +3.0 flare is kept unscaled by DIAM_SCALE (only the shaft-top radius
# feeding into it is already scaled) -- otherwise the collar platform the
# claws spring from balloons out disproportionately at DIAM_SCALE > 1.
COLLAR_R = TIERS[-1]["r1"] + 3.0
# true draconic-evolution energy ball radius -- a real, fixed-size structure
# the orb is standing in for (orange wool placeholder texture for now), so
# this stays fixed at its real radius rather than scaling with DIAM_SCALE
# like the rest of the tower's ornamentation does.
EYE_R = 7.0
# the orb's actual center height isn't a fixed constant -- build_crown
# returns it (the major claws' own tip Z), so the orb always lands exactly
# level with where the claws curl in to meet it. See generate_spire.

BLOCK_NAMES = {
    WALL: "minecraft:black_concrete",
    ORB: "minecraft:orange_wool",
}

BLOCK_COLORS = {
    "minecraft:black_concrete": "#0f0f10",
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
        layer[dist <= r_in] = AIR


# ---------------------------------------------------------------------------
# 2) Crown: a solid collar platform (roof of the shaft, floor of the top
#    chamber) ringed with tapering black spikes -- most short, four tall
#    ones reaching up around the eye. Returns the major claws' own tip Z,
#    so the orb (built afterward) can be centered at exactly that height.
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

    rng = np.random.RandomState(seed + 900)

    # the 4 prominent claws -- one at each cardinal (N/S/E/W) direction.
    # tilt starts leaning outward at the base (tilt0, positive = away from
    # the tower) then swings past straight-up to lean inward near the tip
    # (tilt1, negative = back toward the center axis) -- see build_spike --
    # so each one traces a real hooked claw/horn silhouette curling up and
    # in toward the orb, instead of a straight finger or a bulge that still
    # ends up pointing straight out. Their tip Z is returned so the orb can
    # be centered at exactly that height (see generate_spire) rather than
    # an independently-guessed constant that could drift out of alignment
    # with wherever the claws actually end up.
    major_angles = [i * math.pi / 2 for i in range(4)]
    tip_z = COLLAR_Z1
    for i, ang in enumerate(major_angles):
        bx = CX + int(round((COLLAR_R - 1) * math.cos(ang)))
        by = CY + int(round((COLLAR_R - 1) * math.sin(ang)))
        _, _, tip_z = build_spike(grid, bx, by, COLLAR_Z1 - 2, ang, 55, -35,
                                   11.0 * DIAM_SCALE, 3.0 * DIAM_SCALE, WALL, seed=seed + 60 + i)

    # a handful of smaller accent claws tucked at the OFF-cardinal angles,
    # between each pair of major claws -- same inward-curling shape, just
    # far shorter/thinner and never reaching anywhere near the orb, so they
    # stay pure minor detail and never compete with the 4 prominent ones.
    minor_angles = [math.pi / 4 + i * math.pi / 2 + rng.uniform(-0.1, 0.1) for i in range(4)]
    for i, ang in enumerate(minor_angles):
        bx = CX + int(round((COLLAR_R - 4) * math.cos(ang)))
        by = CY + int(round((COLLAR_R - 4) * math.sin(ang)))
        build_spike(grid, bx, by, COLLAR_Z1 - 2, ang, 50, -10,
                    8.0 * DIAM_SCALE, 2.0 * DIAM_SCALE, WALL, seed=seed + 30 + i)

    return tip_z


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
    eye_center_z = build_crown(grid, seed)
    print(f"crown done ({time.time() - t0:.1f}s)")
    build_eye(grid, seed, center_z=eye_center_z)
    print(f"eye done ({time.time() - t0:.1f}s)")

    counts = {name: int((grid == internal_id).sum()) for internal_id, name in BLOCK_NAMES.items()}
    nz = np.nonzero(grid)
    print(f"bounding box height: z {nz[2].min()} to {nz[2].max()} "
          f"= {nz[2].max() - nz[2].min()} blocks tall")
    print("Voxel counts (solid):", counts)
    print(f"total generation time: {time.time() - t0:.1f}s")
    return grid


def grid_to_structure(grid):
    """Converts the internal uint8 grid (AIR/WALL/ORB ids) into the
    project's canonical Structure, via an Atlas that maps those ids
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
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "output" / "tmp",
                     dest="out_dir", help="directory for outputs (default: generate/output/tmp - "
                                           "this is a standalone dev-iteration render, not a "
                                           "canonical output; scene.py is what assembles the real "
                                           "spire into generate/output/scene.png)")
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
