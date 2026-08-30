"""
Imports a generated Structure (.npz, from any generate/*.py's own
Structure.save()) into a real Minecraft 1.12.2 world save, via
amulet-core - see config.py for the (gitignored) save path/dimension/
paste origin this targets, and block_compat.py for how generate/'s
modern block names get translated into 1.12.2 legacy (id, meta) blocks.

Clears a configurable box around the paste origin first (filled with
air) - see config.json's clear_size/clear_margin - so repeated test
imports never leave stale blocks from a previous, differently-shaped
structure lying around. The clear box is always at least clear_size (from
config.json), grown further if the structure itself is bigger than that
(plus clear_margin of headroom on every side).

Writes are vectorized per chunk (numpy slice assignment against amulet's
own Chunk.blocks array, not a Python loop over individual voxels) - see
place_structure/clear_region below - since a real scene can be hundreds of
thousands of voxels across many chunks.

Usage:
    python world_import/import_structure.py generate/output/scene_tiny.npz
    python world_import/import_structure.py generate/output/scene_tiny.npz --at 100,70,100
"""

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "generate"))

from utils import Structure  # noqa: E402
from block_compat import translate_block  # noqa: E402
from config import load_config  # noqa: E402

import amulet  # noqa: E402
from amulet.api.block import Block  # noqa: E402
from amulet_nbt import IntTag  # noqa: E402

CHUNK_SIZE = 16
WORLD_HEIGHT = 256


def _chunk_spans(lo, hi):
    """lo/hi world coords (hi exclusive) along one horizontal axis -> list
    of (chunk_index, local_lo, local_hi, world_lo, world_hi) covering
    every 16-wide chunk column [lo, hi) touches."""
    spans = []
    c0, c1 = lo // CHUNK_SIZE, (hi - 1) // CHUNK_SIZE
    for c in range(c0, c1 + 1):
        cw0 = c * CHUNK_SIZE
        wlo, whi = max(lo, cw0), min(hi, cw0 + CHUNK_SIZE)
        spans.append((c, wlo - cw0, whi - cw0, wlo, whi))
    return spans


def _air_index(chunk):
    return chunk.block_palette.get_add_block(Block("universal_minecraft", "air"))


def clear_region(level, dimension, min_corner, shape):
    """Fills [min_corner, min_corner+shape) with air, one vectorized numpy
    slice assignment per touched chunk. Only touches chunks that already
    exist - an ungenerated chunk has nothing to clear."""
    x0, y0, z0 = min_corner
    dx, dy, dz = shape
    y1 = min(WORLD_HEIGHT, y0 + dy)
    n_chunks = 0
    for cx, lx0, lx1, _, _ in _chunk_spans(x0, x0 + dx):
        for cz, lz0, lz1, _, _ in _chunk_spans(z0, z0 + dz):
            if not level.has_chunk(cx, cz, dimension):
                continue
            chunk = level.get_chunk(cx, cz, dimension)
            chunk.blocks[lx0:lx1, y0:y1, lz0:lz1] = _air_index(chunk)
            chunk.changed = True
            level.put_chunk(chunk, dimension)
            n_chunks += 1
    print(f"cleared {shape[0]}x{shape[1]}x{shape[2]} region at {min_corner} ({n_chunks} chunk(s) touched)")


def place_structure(level, dimension, structure, min_corner):
    """Writes `structure`'s dense voxel array into the world with its own
    (0,0,0) corner at min_corner. Creates a chunk if it doesn't already
    exist (unlike clear_region - here we're deliberately adding new
    content, not just clearing old). Each atlas block name is translated
    and registered into that chunk's own block_palette once (not per
    voxel), then the whole per-chunk sub-array is remapped via one numpy
    fancy-index and written in a single slice assignment."""
    data = structure.data
    names = structure.atlas.names
    x0, y0, z0 = min_corner
    sx, sy, sz = data.shape
    y1 = min(WORLD_HEIGHT, y0 + sy)
    if not (0 <= y0 < y1 <= WORLD_HEIGHT):
        raise ValueError(f"structure's Y range [{y0}, {y0 + sy}) doesn't fit in [0, {WORLD_HEIGHT})")

    n_chunks = 0
    n_blocks = 0
    for cx, lx0, lx1, wx0, wx1 in _chunk_spans(x0, x0 + sx):
        for cz, lz0, lz1, wz0, wz1 in _chunk_spans(z0, z0 + sz):
            chunk = (level.get_chunk(cx, cz, dimension) if level.has_chunk(cx, cz, dimension)
                     else level.create_chunk(cx, cz, dimension))

            local_index = np.zeros(len(names), dtype=np.uint32)
            local_index[0] = _air_index(chunk)
            for idx, name in enumerate(names):
                if idx == 0:
                    continue
                legacy_name, meta = translate_block(name)
                block = Block("minecraft", legacy_name, {"block_data": IntTag(meta)})
                local_index[idx] = chunk.block_palette.get_add_block(block)

            sub = data[wx0 - x0:wx1 - x0, 0:y1 - y0, wz0 - z0:wz1 - z0]
            chunk.blocks[lx0:lx1, y0:y1, lz0:lz1] = local_index[sub]
            chunk.changed = True
            level.put_chunk(chunk, dimension)
            n_chunks += 1
            n_blocks += int(np.count_nonzero(sub))

    print(f"placed {n_blocks} blocks across {n_chunks} chunk(s), min corner {min_corner}")


def main():
    ap = argparse.ArgumentParser(
        description="Import a generated Structure (.npz) into a real Minecraft 1.12.2 world save "
                     "(see world_import/config.json for the target save/dimension/origin)."
    )
    ap.add_argument("structure_path", type=Path, help="path to a .npz written by Structure.save()")
    ap.add_argument("--at", type=str, default=None,
                     help='world "x,y,z" for the structure\'s own (0,0,0) corner '
                          '(default: config.json\'s "origin")')
    args = ap.parse_args()

    config = load_config()
    origin = tuple(int(v) for v in args.at.split(",")) if args.at else config["origin"]

    structure = Structure.load(args.structure_path)
    print(f"loaded {args.structure_path} - shape {structure.shape}, "
          f"{int(np.count_nonzero(structure.data))} blocks")

    # Every block name the structure uses must resolve up front, before
    # touching the world at all - fail fast rather than partway through
    # clearing/placing a chunk.
    missing = []
    for name in structure.atlas.names[1:]:
        try:
            translate_block(name)
        except KeyError as e:
            missing.append(str(e))
    if missing:
        raise SystemExit("Cannot import:\n" + "\n".join(missing))

    margin = config["clear_margin"]
    clear_shape = tuple(max(cs, ss + 2 * margin) for cs, ss in zip(config["clear_size"], structure.shape))
    clear_min = (
        origin[0] - (clear_shape[0] - structure.shape[0]) // 2,
        max(0, origin[1] - margin),
        origin[2] - (clear_shape[2] - structure.shape[2]) // 2,
    )

    print(f"opening {config['save_path']} (dimension {config['dimension']!r})")
    level = amulet.load_level(str(config["save_path"]))
    try:
        clear_region(level, config["dimension"], clear_min, clear_shape)
        place_structure(level, config["dimension"], structure, origin)
        print("saving...")
        level.save()
    finally:
        level.close()
    print("done")


if __name__ == "__main__":
    main()
