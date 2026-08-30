"""
Theme Rollup Preview Generator
================================

Renders every island theme at several diameters into ONE consolidated grid
image - columns are themes, rows are diameters - so all themes can be
compared side by side at a glance instead of opening a dozen separate PNGs.
Each grid cell is a fixed-size square; the (autocropped) render is scaled to
fit inside it and centered on the same sky-blue background the 3D renderer
itself uses, so different islands' actual sizes/aspect ratios don't distort
the grid.

THE canonical rollup - the one every agent/human should look at, and the
only file this script ever touches when run with no arguments - always
lives at CANONICAL_OUT (see below) and always covers every theme in
THEME_NAMES at DEFAULT_DIAMETERS. That path and that grid shape are the
single source of truth: don't repurpose them for a one-off/partial render.

    python rollup.py            # regenerates the canonical rollup, always
                                 # at the same path, always the full grid

To inspect a subset (fewer themes/diameters, a different cell size, or
decorations on) for iteration, you MUST pass --out to point at a different
file - the script refuses to run otherwise, specifically so a partial or
non-standard render can never silently overwrite the canonical one:

    python rollup.py --themes crystal,desert --out generate/out/renders/_debug.png
    python rollup.py --diameters 40 --decorate-top --out generate/out/renders/_debug.png
"""

import argparse
import importlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import common

# The one standard rollup file. Every agent/human looking for "the" rollup
# should look here, and this path should never point at anything other than
# the full, default-config grid - see the refusal logic in main().
CANONICAL_OUT = "generate/out/renders/rollup.png"

THEME_NAMES = [
    "grass", "volcano", "snow", "crystal", "desert", "mushroom",
    "coral", "ruins", "swamp", "prismarine", "hive", "bones", "gearworks",
]
DEFAULT_DIAMETERS = "40,80,120"
DEFAULT_CELL_SIZE = 360

BG_COLOR = (0xbf, 0xe3, 0xff)  # matches generate/utils.py's BG_COLOR
LABEL_COLOR = (26, 26, 26)


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


def build_rollup(theme_names, diameters, seed=1, cell_size=DEFAULT_CELL_SIZE,
                  decorate_top=False, decorate_underside=True,
                  out_path=CANONICAL_OUT):
    modules = [(name, importlib.import_module(name)) for name in theme_names]

    col_header_h = 50
    row_header_w = 90
    font = _load_font(22)

    cols, rows = len(modules), len(diameters)
    canvas_w = row_header_w + cols * cell_size
    canvas_h = col_header_h + rows * cell_size
    canvas = Image.new("RGB", (canvas_w, canvas_h), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    for ci, (name, _mod) in enumerate(modules):
        x0 = row_header_w + ci * cell_size
        bbox = draw.textbbox((0, 0), name, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((x0 + (cell_size - tw) / 2, 14), name, fill=LABEL_COLOR, font=font)

    for ri, diameter in enumerate(diameters):
        y0 = col_header_h + ri * cell_size
        label = f"d={diameter}"
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((10, y0 + (cell_size - th) / 2), label, fill=LABEL_COLOR, font=font)

    tmp_path = Path("generate/out/renders/_rollup_cell_tmp.png")
    for ci, (name, mod) in enumerate(modules):
        for ri, diameter in enumerate(diameters):
            max_depth = max(6, diameter // 2)
            blocks = mod.generate_island(
                seed=seed, diameter=diameter, max_depth=max_depth,
                decorate_top=decorate_top, decorate_underside=decorate_underside,
            )
            structure = common.blocks_to_structure(blocks)
            common.preview(structure, mod.BLOCK_COLORS, out_path=tmp_path, title=None)
            cell_img = Image.open(tmp_path).convert("RGB")
            fitted = _fit_into_square(cell_img, cell_size)
            x0 = row_header_w + ci * cell_size
            y0 = col_header_h + ri * cell_size
            canvas.paste(fitted, (x0, y0))

    tmp_path.unlink(missing_ok=True)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    print(f"Saved rollup ({cols}x{rows} grid) to {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser(
        description="Render every island theme at several diameters into one grid image. "
                     "With no arguments, regenerates THE canonical rollup at "
                     f"{CANONICAL_OUT} - see the module docstring before passing any flags.")
    ap.add_argument("--themes", type=str, default=None,
                     help="comma-separated theme names (default: all)")
    ap.add_argument("--diameters", type=str, default=DEFAULT_DIAMETERS,
                     help=f"comma-separated diameters (default: {DEFAULT_DIAMETERS})")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cell-size", type=int, default=DEFAULT_CELL_SIZE,
                     help="pixel size of each square grid cell")
    ap.add_argument("--decorate-top", action="store_true",
                     help="include top decorations (trees, flowers, etc)")
    ap.add_argument("--no-underside-decor", action="store_true",
                     help="disable drips/decoration on the underside")
    ap.add_argument("--out", type=str, default=None,
                     help="output path. Required if any of --themes/--diameters/--cell-size/"
                          "--decorate-top/--no-underside-decor differ from their defaults - "
                          f"otherwise this would overwrite the canonical rollup at {CANONICAL_OUT}")
    args = ap.parse_args()

    is_default_config = (
        args.themes is None and args.diameters == DEFAULT_DIAMETERS
        and args.cell_size == DEFAULT_CELL_SIZE and not args.decorate_top
        and not args.no_underside_decor
    )
    if args.out is None:
        if not is_default_config:
            ap.error(
                "--out is required when overriding --themes/--diameters/--cell-size/"
                "--decorate-top/--no-underside-decor, so a partial/non-standard render can "
                f"never silently overwrite the canonical rollup at {CANONICAL_OUT}. "
                "Point --out at a scratch file instead, e.g. generate/out/renders/_debug.png"
            )
        out_path = CANONICAL_OUT
    else:
        out_path = args.out

    theme_names = [t.strip() for t in args.themes.split(",")] if args.themes else THEME_NAMES
    diameters = [int(d) for d in args.diameters.split(",")]

    build_rollup(
        theme_names, diameters, seed=args.seed, cell_size=args.cell_size,
        decorate_top=args.decorate_top, decorate_underside=not args.no_underside_decor,
        out_path=out_path,
    )


if __name__ == "__main__":
    main()
