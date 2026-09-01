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
clear_and_place below - since a real scene can be hundreds of thousands
of voxels across many chunks. clear_and_place also fixes up each touched
chunk's HeightMap (see _fix_heightmap) - writing raw block data bypasses
every incremental heightmap/light update normal in-game block placement
would trigger, and clearing+placing must happen in one get/put per chunk,
not two separate passes (see clear_and_place's own docstring for why).

IMPORTANT: amulet-core 1.9.44 has a real bug that silently discards this
computed heightmap at save time (writes 256 zeros instead) - see
patch_amulet.py's docstring. Run `python world_import/patch_amulet.py`
once after any fresh `pip install -r requirements.txt` before trusting
anything this script writes; it's a one-time environment fix, not
something this script applies itself each run.

Usage:
    python world_import/import_structure.py generate/output/scene_tiny.npz
    python world_import/import_structure.py generate/output/scene_tiny.npz --at 100,70,100
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "generate"))

from utils import Structure  # noqa: E402
from block_compat import translate_block  # noqa: E402
from config import load_config  # noqa: E402

import amulet  # noqa: E402
import amulet_nbt  # noqa: E402
from amulet.api.block import Block  # noqa: E402
from amulet.level.formats.anvil_world.region import AnvilRegionInterface  # noqa: E402
from amulet_nbt import ByteArrayTag, IntTag  # noqa: E402

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


def _fix_heightmap(chunk, air_idx):
    """Recomputes and sets this chunk's HeightMap (misc key
    "height_map256IA", a 16x16 int array: topmost-non-air-Y + 1 per (x, z)
    column, 0 for an all-air column) from its OWN current block data, and
    writes it into chunk.misc so amulet includes it when saving.

    Necessary because we write raw block data directly, bypassing every
    incremental heightmap/light update normal block-placement triggers in
    game - so without this, every chunk we touch keeps whatever heightmap
    it already had (stale, if we changed its terrain) or none at all (a
    chunk level.create_chunk() made from scratch has no heightmap in
    chunk.misc whatsoever - confirmed by comparing a fresh chunk's misc
    keys against an originally-generated one's, which has this same key
    already populated).

    Reads chunk.blocks section by section - chunk.blocks[:, :, :] doesn't
    behave like a plain dense array (a section that was never created,
    e.g. far above anything ever placed, isn't materialized as an air-
    filled array; slicing across it doesn't return one either) - rather
    than assuming a full 0-255 dense array exists."""
    heights = np.zeros((16, 16), dtype=np.int32)
    ys = np.arange(16)[None, :, None]
    for cy in chunk.blocks.sub_chunks:
        solid = chunk.blocks.get_sub_chunk(cy) != air_idx
        if not solid.any():
            continue
        topmost = np.where(solid, ys, -1).max(axis=1)  # (16, 16) local top within this section, -1 if none
        heights = np.maximum(heights, np.where(topmost >= 0, cy * 16 + topmost + 1, 0))
    chunk.misc["height_map256IA"] = heights


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
            air_idx = _air_index(chunk)
            chunk.blocks[lx0:lx1, y0:y1, lz0:lz1] = air_idx
            _fix_heightmap(chunk, air_idx)
            chunk.changed = True
            level.put_chunk(chunk, dimension)
            n_chunks += 1
    print(f"cleared {shape[0]}x{shape[1]}x{shape[2]} region at {min_corner} ({n_chunks} chunk(s) touched)")


def clear_and_place(level, dimension, clear_min, clear_shape, structure, place_min):
    """Clears [clear_min, clear_min+clear_shape) to air AND writes
    `structure` into the world at place_min, in one pass - each touched
    chunk is fetched, modified, heightmap-fixed and put back exactly
    once.

    This has to be one combined pass, not a separate clear_region() call
    followed by a separate placement call: place_min's footprint is
    always a subset of the (bigger, padded) clear box, so every chunk
    that receives real structure content would otherwise get get_chunk/
    put_chunk'd twice in the same session (once to clear it, once to
    place into it) - and amulet's chunk history only persists the FIRST
    put's non-block chunk data (misc - see _fix_heightmap) to disk,
    silently dropping the second. Confirmed by direct repro: the in-memory
    heightmap was correct after each step, but only the first put's
    heightmap survived level.save(). Block data itself isn't affected
    (amulet does correctly compose sequential block edits to the same
    chunk) - it's specifically a misc/non-block quirk. One get/put per
    chunk sidesteps it entirely, and is simpler besides.

    A chunk within the clear box but outside the structure's own
    footprint is only touched (and only needs to exist) if it's already
    real - nothing to clear in a chunk that was never generated. A chunk
    the structure itself touches is always created if missing, same as
    the old place_structure did.
    """
    cx0, cy0, cz0 = clear_min
    cdx, cdy, cdz = clear_shape
    cy1 = min(WORLD_HEIGHT, cy0 + cdy)

    data = structure.data
    names = structure.atlas.names
    px0, py0, pz0 = place_min
    sx, sy, sz = data.shape
    py1 = min(WORLD_HEIGHT, py0 + sy)
    if not (0 <= py0 < py1 <= WORLD_HEIGHT):
        raise ValueError(f"structure's Y range [{py0}, {py0 + sy}) doesn't fit in [0, {WORLD_HEIGHT})")

    n_chunks = 0
    n_blocks = 0
    for cx, clx0, clx1, cwx0, cwx1 in _chunk_spans(cx0, cx0 + cdx):
        for cz, clz0, clz1, cwz0, cwz1 in _chunk_spans(cz0, cz0 + cdz):
            # does the structure itself land in this chunk?
            px_lo, px_hi = max(px0, cwx0), min(px0 + sx, cwx1)
            pz_lo, pz_hi = max(pz0, cwz0), min(pz0 + sz, cwz1)
            touches_structure = px_lo < px_hi and pz_lo < pz_hi

            if not (touches_structure or level.has_chunk(cx, cz, dimension)):
                continue
            chunk = (level.get_chunk(cx, cz, dimension) if level.has_chunk(cx, cz, dimension)
                     else level.create_chunk(cx, cz, dimension))

            air_idx = _air_index(chunk)
            chunk.blocks[clx0:clx1, cy0:cy1, clz0:clz1] = air_idx

            if touches_structure:
                local_index = np.zeros(len(names), dtype=np.uint32)
                local_index[0] = air_idx
                for idx, name in enumerate(names):
                    if idx == 0:
                        continue
                    namespace, legacy_name, meta = translate_block(name)
                    block = Block(namespace, legacy_name, {"block_data": IntTag(meta)})
                    local_index[idx] = chunk.block_palette.get_add_block(block)

                plx0, plx1 = px_lo - cx * CHUNK_SIZE, px_hi - cx * CHUNK_SIZE
                plz0, plz1 = pz_lo - cz * CHUNK_SIZE, pz_hi - cz * CHUNK_SIZE
                sub = data[px_lo - px0:px_hi - px0, 0:py1 - py0, pz_lo - pz0:pz_hi - pz0]
                chunk.blocks[plx0:plx1, py0:py1, plz0:plz1] = local_index[sub]
                n_blocks += int(np.count_nonzero(sub))

            _fix_heightmap(chunk, air_idx)
            chunk.changed = True
            level.put_chunk(chunk, dimension)
            n_chunks += 1

    print(f"cleared {clear_shape[0]}x{clear_shape[1]}x{clear_shape[2]} at {clear_min} and placed "
          f"{n_blocks} blocks at {place_min} in one pass ({n_chunks} chunk(s) touched)")


def _as_signed_byte(value):
    """0-255 int -> the equivalent two's-complement int8 (NBT byte arrays are
    signed; Minecraft's Blocks/Data/Add bytes are conceptually unsigned).
    np.int8(value) works but is deprecated for out-of-range (>127) input -
    this is numpy's own suggested replacement (np.array(...).astype(...))."""
    return np.array(value).astype(np.int8)


def _load_block_id_registry(save_path):
    """namespace:name (as it appears in level.dat) -> THIS save's own
    per-world numeric block id. amulet doesn't expose this itself - only
    needed for patch_modded_blocks below."""
    level_dat = amulet_nbt.load(str(Path(save_path) / "level.dat"))
    ids_list = level_dat.compound.get("FML").get("Registries").get("minecraft:blocks").get("ids")
    return {str(e.get("K")): int(e.get("V")) for e in ids_list}


def clear_stale_extended_id_tags(save_path, dimension_folder, clear_min, clear_shape):
    """Strips any leftover "Palette"/"Add"/"Add2" NBT tags from every
    section within the clear box, for every chunk that already exists.

    Any chunk the live game has ever loaded (even just once, e.g. during a
    login that later crashed elsewhere) gets rewritten by JEID's own
    MixinBlockStateContainer.reid$newGetDataForNBT the next time it's
    saved - it UNCONDITIONALLY converts every section's Blocks/Data into
    palette-index form plus a "Palette" int-array tag, whether or not
    extended (>255) ids are actually involved. If this script then
    overwrites that chunk's Blocks/Data with fresh plain-vanilla-style raw
    ids (as clear_and_place/patch_modded_blocks do) without also removing
    the old "Palette" tag, the chunk becomes self-contradictory: on the
    next load, JEID sees the (stale) Palette tag, sets a non-null
    temporaryPalette, and treats the fresh Blocks/Data bytes as PALETTE
    INDICES instead of raw ids - indexing into the stale, unrelated
    palette int[] with them. Confirmed as the actual cause of a real
    ArrayIndexOutOfBoundsException login crash: the crash index each time
    exactly matched (freshly-written block byte << 4) | meta - a bogus
    palette index computed against a stale length-1 "all air" palette left
    over from before this chunk had real content. "Add"/"Add2" are also
    stripped here since a Palette-format section never carries them (see
    JEID's own save code, which explicitly nulls the Add array) - any
    leftover is equally stale.

    Must run AFTER level.close() (same as patch_modded_blocks) and BEFORE
    it, so patch_modded_blocks writes its own Add/Add2 into a clean slate.
    Runs unconditionally (not just when the structure has modded blocks) -
    this contamination isn't specific to those.
    """
    x0, y0, z0 = clear_min
    dx, dy, dz = clear_shape
    cx0, cx1 = x0 // CHUNK_SIZE, (x0 + dx - 1) // CHUNK_SIZE
    cz0, cz1 = z0 // CHUNK_SIZE, (z0 + dz - 1) // CHUNK_SIZE

    by_region = defaultdict(set)
    for cx in range(cx0, cx1 + 1):
        for cz in range(cz0, cz1 + 1):
            by_region[(cx // 32, cz // 32)].add((cx, cz))

    n_cleaned = 0
    for (rx, rz), chunks in by_region.items():
        region_path = Path(save_path) / dimension_folder / "region" / f"r.{rx}.{rz}.mca"
        if not region_path.exists():
            continue
        region = AnvilRegionInterface(str(region_path))
        for (cx, cz) in chunks:
            local_cx, local_cz = cx - rx * 32, cz - rz * 32
            if not region.has_chunk(local_cx, local_cz):
                continue
            tag = region.get_data(local_cx, local_cz)
            level = tag.compound.get("Level")
            sections = level.get("Sections") if level is not None else None
            if sections is None:
                # a chunk amulet just created from nothing (never generated/
                # visited before this import - the common case for a brand
                # new world) has no Level/Sections yet to carry a stale
                # Palette/Add/Add2 tag in the first place, so there's
                # nothing here to clean.
                continue
            changed = False
            for sec in sections:
                for key in ("Palette", "Add", "Add2"):
                    if sec.get(key) is not None:
                        del sec[key]
                        changed = True
            if changed:
                region.write_data(local_cx, local_cz, tag)
                n_cleaned += 1

    if n_cleaned:
        print(f"cleared stale Palette/Add/Add2 tags from {n_cleaned} previously-touched chunk(s)")


def patch_modded_blocks(save_path, dimension_folder, structure, place_min):
    """amulet-core/PyMCTranslate has no translation spec for a real
    (non-vanilla) mod block, so clear_and_place's normal chunk.block_palette
    write silently drops any such voxel to air at level.save() time -
    confirmed by direct inspection (raw id/meta both read back as 0 despite
    a successful, warning-only import run); PyMCTranslate's own "Could not
    find translation information ... if this is not a vanilla block ignore
    this message" is misleading here, since the block is NOT actually
    placed. This patches every such voxel directly into the already-saved
    region file's raw NBT (Sections' Blocks/Data byte arrays, plus a vanilla
    Add nibble for ids above 255 and JEID's own extra "Add2" nibble - its
    own extension past vanilla's 4096 cap, see MixinAnvilChunkLoader/
    MixinBlockStateContainer - for ids above 4095, up to 65535 total),
    entirely bypassing amulet's chunk API for exactly these voxels - see
    block_compat.py's 3-tuple (namespace, name, meta) LEGACY_MAP entries.
    Must run AFTER level.close() (so this has the region files to itself)
    and AFTER clear_stale_extended_id_tags (so it starts from sections with
    no leftover "Palette"/Add/Add2 tags to accidentally build on).
    """
    data = structure.data
    names = structure.atlas.names
    modded = {}
    for idx, name in enumerate(names):
        if idx == 0:
            continue
        namespace, legacy_name, meta = translate_block(name)
        if namespace != "minecraft":
            modded[idx] = (namespace, legacy_name, meta)
    if not modded:
        return

    registry = _load_block_id_registry(save_path)
    px0, py0, pz0 = place_min

    by_region = defaultdict(lambda: defaultdict(list))
    for idx, (namespace, legacy_name, meta) in modded.items():
        registry_key = f"{namespace}:{legacy_name}"
        world_id = registry.get(registry_key)
        if world_id is None:
            raise SystemExit(f"Block {registry_key!r} has no numeric id in this save's level.dat "
                              f"FML block registry - it must have been placed/loaded in this world "
                              f"at least once before an import can reference it")
        if world_id >= 65536:
            raise SystemExit(f"Block {registry_key!r} has world id {world_id} (>= 65536) - "
                              f"patch_modded_blocks's id encoding (Blocks + Add + JEID's own Add2 "
                              f"nibble - see JEID's MixinAnvilChunkLoader/MixinBlockStateContainer) "
                              f"tops out at 16 bits; extend it before using a block whose id lands "
                              f"beyond that")
        xs, ys, zs = (data == idx).nonzero()
        for x, y, z in zip(xs, ys, zs):
            wx, wy, wz = int(x) + px0, int(y) + py0, int(z) + pz0
            cx, cz = wx // CHUNK_SIZE, wz // CHUNK_SIZE
            rx, rz = cx // 32, cz // 32
            by_region[(rx, rz)][(cx, cz)].append((wx, wy, wz, world_id, meta))

    n_patched = 0
    for (rx, rz), chunks in by_region.items():
        region_path = Path(save_path) / dimension_folder / "region" / f"r.{rx}.{rz}.mca"
        region = AnvilRegionInterface(str(region_path))
        for (cx, cz), voxels in chunks.items():
            local_cx, local_cz = cx - rx * 32, cz - rz * 32
            tag = region.get_data(local_cx, local_cz)
            sec_by_y = {int(sec.get("Y")): sec for sec in tag.compound.get("Level").get("Sections")}
            by_sy = defaultdict(list)
            for wx, wy, wz, world_id, meta in voxels:
                by_sy[wy // 16].append((wx, wy, wz, world_id, meta))
            for sy, sy_voxels in by_sy.items():
                sec = sec_by_y.get(sy)
                if sec is None:
                    raise SystemExit(f"Section Y={sy} missing in chunk {cx},{cz} - the normal "
                                      f"clear_and_place pass should already have created it")
                blocks = sec.get("Blocks")
                dat = sec.get("Data")
                for wx, wy, wz, world_id, meta in sy_voxels:
                    # Blocks(8 bit) + vanilla Add nibble (bits 8-11) covers
                    # up to id 4095; JEID's own "Add2" nibble (bits 12-15,
                    # its "NEID format" - see MixinAnvilChunkLoader/
                    # MixinBlockStateContainer's reid$newSetDataFromNBT
                    # fallback path) extends that to 16 bits (65535).
                    add_nibble = (world_id >> 8) & 0xF
                    add2_nibble = (world_id >> 12) & 0xF
                    add = sec.get("Add")
                    if add_nibble and add is None:
                        add = ByteArrayTag(np.zeros(2048, dtype=np.int8))
                        sec["Add"] = add
                    add2 = sec.get("Add2")
                    if add2_nibble and add2 is None:
                        add2 = ByteArrayTag(np.zeros(2048, dtype=np.int8))
                        sec["Add2"] = add2
                    lx, ly, lz = wx - cx * 16, wy - sy * 16, wz - cz * 16
                    vidx = (ly * 16 + lz) * 16 + lx
                    blocks[vidx] = _as_signed_byte(world_id & 0xFF)
                    byte_i, hi = vidx // 2, vidx % 2 == 1
                    cur = int(dat[byte_i]) & 0xFF
                    dat[byte_i] = _as_signed_byte((cur & 0x0F) | (meta << 4) if hi else (cur & 0xF0) | meta)
                    if add_nibble:
                        cur_a = int(add[byte_i]) & 0xFF
                        new_a = (cur_a & 0x0F) | (add_nibble << 4) if hi else (cur_a & 0xF0) | add_nibble
                        add[byte_i] = _as_signed_byte(new_a)
                    if add2_nibble:
                        cur_a2 = int(add2[byte_i]) & 0xFF
                        new_a2 = (cur_a2 & 0x0F) | (add2_nibble << 4) if hi else (cur_a2 & 0xF0) | add2_nibble
                        add2[byte_i] = _as_signed_byte(new_a2)
                    n_patched += 1
            region.write_data(local_cx, local_cz, tag)

    print(f"raw-patched {n_patched} modded-block voxel(s) amulet/PyMCTranslate can't translate")


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
        clear_and_place(level, config["dimension"], clear_min, clear_shape, structure, origin)
        print("saving...")
        level.save()
    finally:
        level.close()
    clear_stale_extended_id_tags(config["save_path"], config["dimension"], clear_min, clear_shape)
    patch_modded_blocks(config["save_path"], config["dimension"], structure, origin)
    print("done")


if __name__ == "__main__":
    main()
