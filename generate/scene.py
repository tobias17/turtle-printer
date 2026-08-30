"""
Grand Scene Composer
=====================
Combines Sauron's spire (spire.py) with thirty floating islands - five of
each theme (grass, volcano, snow, desert, mushroom, bones), each with its
own random diameter spanning DIAMETER_RANGE. The spire doesn't get a
dedicated island of its own: it's planted on top of the single largest of
the five volcano islands, which still counts as one of volcano's five (so
the scene stays at exactly five per theme, thirty total).

Placement is randomized but "human random", like a smart-shuffle playlist:
islands are packed outward from the host volcano island (largest-diameter
first, for a tight non-overlapping fit) into random positions, rejecting
any candidate spot that either overlaps an already-placed island/the host,
or sits within THEME_MIN_ANGLE_DEG of another island of the SAME theme - so
same-theme islands always end up well spread around the circle instead of
clustering together, without the layout looking like a mechanical grid.

Outputs (into --out-dir, default generate/out):
    <out>.npz    canonical Structure (numpy voxel array + Atlas) - the same
                 format every other generator in this project produces.
    <out>.png    isometric preview render
    <out>.schem  WorldEdit schematic (only with --schem, if mcschematic is
                 installed)

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

from utils import render_screenshot  # noqa: E402
import spire  # noqa: E402
import common  # noqa: E402
import grass, volcano, snow, desert, mushroom, bones  # noqa: E402

THEME_MODULES = {
    "grass": grass, "volcano": volcano, "snow": snow,
    "desert": desert, "mushroom": mushroom, "bones": bones,
}
THEMES = list(THEME_MODULES)

N_PER_THEME = 5
DIAMETER_RANGE = (40, 100)  # each island's diameter is randomized somewhere in this span
DIAMETER_JITTER_FRAC = 0.15  # +/- this fraction of the span, applied per island on top of its spread target

GAP = 6                     # minimum clear void kept between any two islands' footprints
MAX_SPREAD = 280            # width of the annulus satellites are scattered into, beyond the host's edge
THEME_MIN_ANGLE_DEG = 45    # minimum angular separation enforced between same-theme islands
MAX_TRIES = 600
Y_JITTER = (-10, 35)        # satellite top-surface height, relative to the host island's own top -
                             # kept modest so the whole scene (spire included) stays under 256 blocks tall


def _spanning_diameters(rng, n, lo, hi, jitter_frac=DIAMETER_JITTER_FRAC):
    """n diameters spread evenly across [lo, hi], each independently jittered
    by up to +/- jitter_frac of the span - so a theme's islands cover the
    whole size range (not clustered near one value) while no two are
    identical or mechanically evenly-spaced."""
    span = hi - lo
    step = span / (n - 1) if n > 1 else 0
    jitter = span * jitter_frac
    return [
        round(min(hi, max(lo, lo + step * i + rng.uniform(-jitter, jitter))))
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Placement: "smart shuffle" packing around the center
# ---------------------------------------------------------------------------

def _angle_diff_deg(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _place_islands(rng, specs, host):
    """specs: [(theme, diameter), ...], largest-diameter first. `host` is the
    already-placed island (dict with theme/x/z/radius/angle) everything else
    is packed around. Returns one dict per spec with world x/z (and
    angle/dist, for logging) added, via rejection sampling into an annulus
    around the host."""
    placed = [host]
    r_lo = host["radius"] + GAP
    r_hi = r_lo + MAX_SPREAD

    for theme, diameter in specs:
        radius = diameter / 2.0
        chosen = None
        for relax in (False, True):  # second pass drops the same-theme angle rule
            if chosen is not None:
                break
            for _ in range(MAX_TRIES):
                angle = rng.uniform(0, 360)
                dist = math.sqrt(rng.uniform(r_lo ** 2, r_hi ** 2))
                x = dist * math.cos(math.radians(angle))
                z = dist * math.sin(math.radians(angle))

                ok = all(
                    math.hypot(x - o["x"], z - o["z"]) >= radius + o["radius"] + GAP
                    for o in placed
                )
                if ok and not relax:
                    ok = all(
                        _angle_diff_deg(angle, o["angle"]) >= THEME_MIN_ANGLE_DEG
                        for o in placed if o["theme"] == theme
                    )
                if ok:
                    chosen = (x, z, angle, dist)
                    break

        if chosen is None:
            # Last resort (should be rare): take the least-overlapping of
            # another batch of candidates rather than failing outright.
            best, best_overlap = None, None
            for _ in range(MAX_TRIES):
                angle = rng.uniform(0, 360)
                dist = math.sqrt(rng.uniform(r_lo ** 2, r_hi ** 2))
                x = dist * math.cos(math.radians(angle))
                z = dist * math.sin(math.radians(angle))
                overlap = max(
                    (radius + o["radius"] + GAP) - math.hypot(x - o["x"], z - o["z"])
                    for o in placed
                )
                if best_overlap is None or overlap < best_overlap:
                    best, best_overlap = (x, z, angle, dist), overlap
            chosen = best
            print(f"  warning: could not find a fully clear spot for {theme} d={diameter}, "
                  f"used the least-overlapping candidate")

        x, z, angle, dist = chosen
        placed.append(dict(theme=theme, diameter=diameter,
                            x=x, z=z, radius=radius, angle=angle, dist=dist))

    return placed[1:]  # drop the host entry (the caller already has it)


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

    theme_diameters = {theme: _spanning_diameters(rng, N_PER_THEME, *DIAMETER_RANGE) for theme in THEMES}

    # the spire needs a home: the single largest volcano island becomes the
    # host, planted at the origin - it still counts as one of volcano's five
    # instances rather than an extra island.
    host_idx = max(range(N_PER_THEME), key=lambda i: theme_diameters["volcano"][i])
    host_diameter = theme_diameters["volcano"][host_idx]

    specs = [
        (theme, diameter)
        for theme in THEMES
        for i, diameter in enumerate(theme_diameters[theme])
        if not (theme == "volcano" and i == host_idx)
    ]
    rng.shuffle(specs)
    specs.sort(key=lambda s: -s[1])  # largest first, for tighter packing

    host = dict(theme="volcano", x=0.0, z=0.0, radius=host_diameter / 2.0, angle=0.0)
    placements = _place_islands(rng, specs, host)

    blocks = {}

    host_max_depth = max(6, host_diameter // 2)
    blocks.update(volcano.generate_island(
        seed=seed, diameter=host_diameter, max_depth=host_max_depth,
        decorate_top=False, decorate_underside=True, offset=(0, 0, 0),
    ))
    print(f"host volcano island (spire): d={host_diameter}")

    for i, p in enumerate(placements):
        module = THEME_MODULES[p["theme"]]
        y = rng.randint(*Y_JITTER)
        max_depth = max(6, p["diameter"] // 2)
        offset = (round(p["x"]), y, round(p["z"]))
        island_blocks = module.generate_island(
            seed=seed * 1000 + i + 1, diameter=p["diameter"], max_depth=max_depth,
            decorate_top=False, decorate_underside=True, offset=offset,
        )
        blocks.update(island_blocks)
        print(f"  {p['theme']:<8} d={p['diameter']:<4} "
              f"pos=({offset[0]:>5}, {offset[1]:>4}, {offset[2]:>5})  "
              f"dist={p['dist']:.0f} angle={p['angle']:.0f}deg")

    print("generating spire...")
    grid = spire.generate_spire(seed=seed)
    spire_structure = spire.grid_to_structure(grid)
    spire.hollow_out(spire_structure.data, 2)
    # spire's own (X, Z) center is (CX, CY); its Y=0 is its flat base, which
    # needs to land right on the buildable surface just above the host
    # island's flat top (topY=0, so the surface to build on is y=1).
    spire_offset = (-spire.CX, 1, -spire.CY)
    blocks.update(structure_to_blocks(spire_structure, offset=spire_offset))

    return blocks


BLOCK_COLORS = {}
for _mod in (grass, volcano, snow, desert, mushroom, bones, spire):
    BLOCK_COLORS.update(_mod.BLOCK_COLORS)


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
    png_path = render_screenshot(structure, args.out_dir / f"{args.out}.png",
                                  title=f"grand scene (seed={args.seed})", palette=palette,
                                  width=1600, height=1600)
    print(f"Saved preview image to {png_path}")

    if args.schem:
        structure.to_schematic(args.out_dir, args.out)


if __name__ == "__main__":
    main()
