"""
Theme Rollup Preview Generator
================================

Renders every island theme, all at the SAME diameter used in the real scene
(see generate/scene.py's DIAMETER_RANGE), across several different seeds -
columns are themes, rows are seeds - into ONE consolidated grid image, so
all themes can be compared side by side at the size they'll actually appear
at, and seed-to-seed variety within a theme can be checked at a glance
instead of opening a dozen separate PNGs. Each grid cell is a fixed-size
square; the (autocropped) render is scaled to fit inside it and centered on
the same sky-blue background the 3D renderer itself uses, so different
islands' actual sizes/aspect ratios don't distort the grid. Cells are
separated by a plain black divider bar in each gap, the same style
scene.py's two-panel preview uses between its isometric/top-down views,
rather than relying on the background color alone to read as a seam.

Only the theme name is labeled (once, atop its column) - there's no per-row
label, since every row is just "this theme, a different seed" at the same
size.

THE canonical rollup - the one every agent/human should look at, and the
only file this script ever touches when run with no arguments - always
lives at CANONICAL_OUT (see below) and always covers every theme in
THEME_NAMES at DEFAULT_SEEDS. That path and that grid shape are the
single source of truth: don't repurpose them for a one-off/partial render.

    python rollup.py            # regenerates the canonical rollup, always
                                 # at the same path, always the full grid

To inspect a subset (fewer themes/seeds, a different diameter/cell size, or
decorations on) for iteration, you MUST pass --out to point at a different
file - the script refuses to run otherwise, specifically so a partial or
non-standard render can never silently overwrite the canonical one:

    python rollup.py --themes crystal,desert --out generate/output/tmp/_debug.png
    python rollup.py --seeds 1,2 --decorate-top --out generate/output/tmp/_debug.png

Each grid cell is independently cached (see CACHE_DIR / CACHE_MANIFEST below):
rendering an island is by far the slowest part of building the rollup, so a
cell is only regenerated when something that could actually change its
pixels changed - its theme's own file, common.py/utils.py, or that cell's
own seed/diameter/max_depth/decoration params. Editing one theme file only
re-renders that theme's column; editing common.py/utils.py re-renders
everything. Pass --no-cache to force a full regeneration regardless.
"""

import argparse
import hashlib
import importlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import common

# The one standard rollup file. Every agent/human looking for "the" rollup
# should look here, and this path should never point at anything other than
# the full, default-config grid - see the refusal logic in main().
CANONICAL_OUT = "generate/output/rollup.png"

# Per-cell render cache. Each grid cell (one theme, one seed, at whatever
# diameter/max_depth/decoration params produced it) is expensive to render
# but fully deterministic, so it's cached under a content hash and only
# regenerated when something that could change its pixels actually changed:
# the theme's own file, the shared common.py/utils.py machinery, or the
# cell's own render params. cell_size is deliberately excluded from the key
# - it only affects the cheap fit-into-square/paste step done after a cache
# hit, not the underlying render.
CACHE_DIR = Path("generate/output/tmp/rollup_cache")
CACHE_MANIFEST = CACHE_DIR / "manifest.json"

THEME_NAMES = [
    "spire_base",
    "grass", "volcano", "snow", "crystal", "desert", "mesa", "mushroom",
    "coral", "ruins", "swamp", "prismarine", "hive", "bones",
]
DEFAULT_SEEDS = "1,2,3,4"
# Matches the midpoint of generate/scene.py's DIAMETER_RANGE (100-120) -
# every satellite island in the real scene is sized somewhere in that
# range, so this is what they actually look like there.
DEFAULT_DIAMETER = 110
DEFAULT_CELL_SIZE = 360

BG_COLOR = (0xbf, 0xe3, 0xff)  # matches generate/utils.py's BG_COLOR
LABEL_COLOR = (26, 26, 26)
DIVIDER_COLOR = (26, 26, 26)   # matches scene.py's _compose_views divider
DIVIDER_WIDTH = 2
GAP = 24                        # matches scene.py's _compose_views gap


def _hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _common_code_hash():
    """Hash of the shared machinery every theme depends on: common.py
    itself plus utils.py (which common.py's Atlas/Structure/render_screenshot/
    value_noise_2d come from). A change to either can change every theme's
    pixels, so it's tracked as one bucket rather than per-theme."""
    islands_dir = Path(__file__).resolve().parent
    common_py = islands_dir / "common.py"
    utils_py = islands_dir.parent / "utils.py"
    return hashlib.sha256(
        (_hash_file(common_py) + _hash_file(utils_py)).encode("utf-8")
    ).hexdigest()


def _theme_file_hash(theme_name):
    islands_dir = Path(__file__).resolve().parent
    return _hash_file(islands_dir / f"{theme_name}.py")


def _cell_cache_key(theme, seed, diameter, max_depth, decorate_top,
                     decorate_underside, common_hash, theme_hash):
    payload = json.dumps(
        {
            "theme": theme, "seed": seed, "diameter": diameter,
            "max_depth": max_depth, "decorate_top": decorate_top,
            "decorate_underside": decorate_underside,
            "common_hash": common_hash, "theme_hash": theme_hash,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_font(size):
    for path in ("arial.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_into_square(img, size):
    """Scales img to fit within a size x size square (preserving aspect
    ratio, never upscaling past the square) and pastes it centered on a
    BG_COLOR square canvas, so every cell is the same size regardless of
    the render's own dimensions."""
    w, h = img.size
    scale = min(size / w, size / h)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), BG_COLOR)
    canvas.paste(resized, ((size - new_w) // 2, (size - new_h) // 2))
    return canvas


def build_rollup(theme_names, seeds, diameter=DEFAULT_DIAMETER, cell_size=DEFAULT_CELL_SIZE,
                  decorate_top=False, decorate_underside=True,
                  out_path=CANONICAL_OUT, use_cache=True):
    modules = [(name, importlib.import_module(name)) for name in theme_names]

    col_header_h = 50
    font = _load_font(22)

    cols, rows = len(modules), len(seeds)
    canvas_w = cols * cell_size + (cols - 1) * GAP
    canvas_h = col_header_h + rows * cell_size + (rows - 1) * GAP
    canvas = Image.new("RGB", (canvas_w, canvas_h), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    for ci, (name, _mod) in enumerate(modules):
        x0 = ci * (cell_size + GAP)
        bbox = draw.textbbox((0, 0), name, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((x0 + (cell_size - tw) / 2, 14), name, fill=LABEL_COLOR, font=font)

    max_depth = max(6, diameter // 2)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common_hash = _common_code_hash()
    theme_hashes = {name: _theme_file_hash(name) for name, _mod in modules}

    manifest_cells = {}
    n_cached, n_rendered = 0, 0
    for ci, (name, mod) in enumerate(modules):
        for ri, seed in enumerate(seeds):
            key = _cell_cache_key(
                name, seed, diameter, max_depth, decorate_top, decorate_underside,
                common_hash, theme_hashes[name],
            )
            cache_file = CACHE_DIR / f"{key}.png"
            if use_cache and cache_file.exists():
                cell_img = Image.open(cache_file).convert("RGB")
                n_cached += 1
            else:
                blocks = mod.generate_island(
                    seed=seed, diameter=diameter, max_depth=max_depth,
                    decorate_top=decorate_top, decorate_underside=decorate_underside,
                )
                structure = common.blocks_to_structure(blocks)
                common.preview(structure, mod.BLOCK_COLORS, out_path=cache_file, title=None)
                cell_img = Image.open(cache_file).convert("RGB")
                n_rendered += 1
            manifest_cells[f"{name}:{seed}"] = {"key": key, "cache_file": cache_file.name}

            fitted = _fit_into_square(cell_img, cell_size)
            x0 = ci * (cell_size + GAP)
            y0 = col_header_h + ri * (cell_size + GAP)
            canvas.paste(fitted, (x0, y0))

    CACHE_MANIFEST.write_text(json.dumps({
        "common_files": {
            "common.py": _hash_file(Path(__file__).resolve().parent / "common.py"),
            "utils.py": _hash_file(Path(__file__).resolve().parent.parent / "utils.py"),
        },
        "common_hash": common_hash,
        "theme_files": theme_hashes,
        "cells": manifest_cells,
    }, indent=2, sort_keys=True))
    print(f"Cache: {n_cached} cell(s) reused, {n_rendered} cell(s) regenerated "
          f"({CACHE_DIR})")

    # Black divider bars between cells (both between columns and between
    # rows), drawn in the middle of each gap - same style as scene.py's
    # _compose_views divider between its isometric/top-down panels.
    for ci in range(1, cols):
        x = ci * (cell_size + GAP) - GAP // 2
        draw.line([(x, col_header_h), (x, canvas_h)], fill=DIVIDER_COLOR, width=DIVIDER_WIDTH)
    for ri in range(1, rows):
        y = col_header_h + ri * (cell_size + GAP) - GAP // 2
        draw.line([(0, y), (canvas_w, y)], fill=DIVIDER_COLOR, width=DIVIDER_WIDTH)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    print(f"Saved rollup ({cols}x{rows} grid, d={diameter}) to {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser(
        description="Render every island theme, at the scene's diameter, across several seeds "
                     "into one grid image. With no arguments, regenerates THE canonical rollup at "
                     f"{CANONICAL_OUT} - see the module docstring before passing any flags.")
    ap.add_argument("--themes", type=str, default=None,
                     help="comma-separated theme names (default: all)")
    ap.add_argument("--seeds", type=str, default=DEFAULT_SEEDS,
                     help=f"comma-separated seeds (default: {DEFAULT_SEEDS})")
    ap.add_argument("--diameter", type=int, default=DEFAULT_DIAMETER,
                     help=f"island diameter, matching scene.py's range (default: {DEFAULT_DIAMETER})")
    ap.add_argument("--cell-size", type=int, default=DEFAULT_CELL_SIZE,
                     help="pixel size of each square grid cell")
    ap.add_argument("--decorate-top", action="store_true",
                     help="include top decorations (trees, flowers, etc)")
    ap.add_argument("--no-underside-decor", action="store_true",
                     help="disable drips/decoration on the underside")
    ap.add_argument("--out", type=str, default=None,
                     help="output path. Required if any of --themes/--seeds/--diameter/--cell-size/"
                          "--decorate-top/--no-underside-decor differ from their defaults - "
                          f"otherwise this would overwrite the canonical rollup at {CANONICAL_OUT}")
    ap.add_argument("--no-cache", action="store_true",
                     help="ignore the per-cell render cache and regenerate every cell "
                          f"(the cache lives at {CACHE_DIR})")
    args = ap.parse_args()

    is_default_config = (
        args.themes is None and args.seeds == DEFAULT_SEEDS and args.diameter == DEFAULT_DIAMETER
        and args.cell_size == DEFAULT_CELL_SIZE and not args.decorate_top
        and not args.no_underside_decor
    )
    if args.out is None:
        if not is_default_config:
            ap.error(
                "--out is required when overriding --themes/--seeds/--diameter/--cell-size/"
                "--decorate-top/--no-underside-decor, so a partial/non-standard render can "
                f"never silently overwrite the canonical rollup at {CANONICAL_OUT}. "
                "Point --out at a scratch file instead, e.g. generate/output/tmp/_debug.png"
            )
        out_path = CANONICAL_OUT
    else:
        out_path = args.out

    theme_names = [t.strip() for t in args.themes.split(",")] if args.themes else THEME_NAMES
    seeds = [int(s) for s in args.seeds.split(",")]

    build_rollup(
        theme_names, seeds, diameter=args.diameter, cell_size=args.cell_size,
        decorate_top=args.decorate_top, decorate_underside=not args.no_underside_decor,
        out_path=out_path, use_cache=not args.no_cache,
    )


if __name__ == "__main__":
    main()
