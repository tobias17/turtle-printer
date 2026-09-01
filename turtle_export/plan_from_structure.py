"""
Scene -> Turtle Build Plans
============================

Converts a generate/ Structure (.npz) into a set of per-turtle build plans
consumable by printer_david's ComputerCraft turtle runtime
(printer_david/turtles/nexus_deploy.lua + nexus_builder_gps.lua).
printer_david/ is treated as a fixed, read-only reference: this script never
reads or modifies anything under it, it only reproduces the file FORMAT its
Lua scripts already parse (see printer_david/turtles/SETUP_README.txt and
nexus_deploy.lua / nexus_builder_gps.lua's own parsing code):

  tower.cfg  - one shared world transform for the whole batch:
                 origin=<world x> <world y> <world z>
                 xvec=1 0
                 zvec=0 1
               (identity orientation - a Structure's own +X/+Z axes already
               line up with world +X/+Z, same convention world_import/ uses)

  Txx.plan   - one per turtle:
                 OFFSET <x> <y> <z>       this turtle's structure-space
                                          offset from the tower origin
                 BOUNDS <minX> <maxX> <minY> <maxY> <minZ> <maxZ>
                                          local movement bounds
                 BLOCKS <n>               total block count (progress only)
                 # PALETTE <k> <block>    material-slot legend, k = 1..7,
                                          matching turtle inventory slot k /
                                          supply Ender Chest slot 8+k (see
                                          nexus_builder_gps.lua's
                                          materialSlot/chestSlot tables).
                                          A "#" comment as far as the Lua
                                          reader is concerned (it only
                                          matches lines starting
                                          OFFSET/BOUNDS/BLOCKS/"B "), but
                                          it's the only place the slot ->
                                          block mapping lives, so whoever
                                          stocks the chests reads it here.
                 B <x> <y> <z> <k>        one line per block, in this
                                          turtle's LOCAL frame (relative to
                                          OFFSET)

One island == one connected component of solid voxels (6-connectivity).
Every generate/ scene keeps islands GAP blocks apart (see e.g.
scene_tiny.py's GAP constant) specifically so they never touch, so this
holds without knowing anything about how the scene was composed - the same
script works unchanged on scene.py's full cluster, just with more
components found. A tower/spire sits directly on its host island's top
surface (touching, by construction - see scene_tiny.py's tower_offset), so
a spire+host is correctly treated as the single component/single turtle it
physically is. Components smaller than --min-blocks (default 8) are
dropped rather than exported - some themes' underside decoration can place
a block or two that never touches the theme's own carved body (crystal.py's
individual crystal points, concretely), and sending a turtle to build a
single floating block isn't worth a plan of its own.

If more islands are found than the requested (or default) turtle count,
this refuses to run rather than silently combining islands onto one
turtle's single-bounding-box plan - re-run with a matching/higher
--turtles instead.

Usage:
    python turtle_export/plan_from_structure.py generate/output/scene_tiny.npz
    python turtle_export/plan_from_structure.py generate/output/scene_tiny.npz --turtles 4
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "generate"))

from utils import Structure  # noqa: E402

# Turtle inventory budget: 7 material slots + 7 matching supply Ender Chests
# + 1 fuel workspace + 1 fuel Ender Chest = 16 slots total (see
# nexus_builder_gps.lua's materialSlot/chestSlot tables).
MAX_MATERIAL_SLOTS = 7


def default_origin():
    """Reuses world_import/config.json's paste origin if present, so a real
    turtle build lines up with wherever world_import/ already pastes this
    same structure for preview - one shared "where does this go in the
    world" answer instead of a second place to keep in sync by hand. Falls
    back to (0, 0, 0) if config.json doesn't exist (gitignored,
    machine-specific - see world_import/config.example.json)."""
    cfg_path = REPO_ROOT / "world_import" / "config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
        if "origin" in cfg:
            return tuple(int(v) for v in cfg["origin"])
    return (0, 0, 0)


def find_islands(structure, min_blocks=1):
    """Labels 6-connected components of solid voxels. Returns a list of
    dicts (bbox_min, bbox_max, local_idx, block_ids), sorted by descending
    block count so T01 is always the biggest build - typically the
    host island with its spire/tower attached.

    Components smaller than `min_blocks` are dropped (printed, not silently
    lost) rather than turned into a plan - a real generator quirk, not
    anything to do with hollowing: some themes' underside decoration (e.g.
    crystal.py's individual crystal points) can place a block or two that
    never actually touches the theme's own carved body, so on a real
    (non-toy) scene there can be a handful of 1-2 voxel floating specks
    alongside the actual islands. Sending a turtle to build a single block
    is pointless, so these are excluded from the batch entirely rather than
    forcing every tiny speck to burn its own turtle."""
    solid = structure.data != 0
    labels, n = ndimage.label(solid)  # default structuring element = 6-connectivity
    islands = []
    dropped = 0
    for label_id in range(1, n + 1):
        idx = np.argwhere(labels == label_id)
        if len(idx) < min_blocks:
            dropped += 1
            continue
        bbox_min = idx.min(axis=0)
        bbox_max = idx.max(axis=0)
        block_ids = structure.data[idx[:, 0], idx[:, 1], idx[:, 2]]
        islands.append(dict(
            bbox_min=bbox_min, bbox_max=bbox_max,
            local_idx=idx - bbox_min, block_ids=block_ids,
        ))
    islands.sort(key=lambda isl: -len(isl["block_ids"]))
    if dropped:
        print(f"dropped {dropped} component(s) smaller than --min-blocks {min_blocks} "
              f"(floating decoration specks, not real islands)")
    return islands


def build_palette(atlas, block_ids):
    """Assigns material-slot indices 1..k to this island's distinct blocks,
    most-placed first (slot 1 then needs refilling least often). Raises if
    an island needs more than MAX_MATERIAL_SLOTS distinct blocks - a turtle
    only has 7 material slots and there's no automatic way to fall back,
    same "fail loudly, no guessed substitute" spirit as
    world_import/block_compat.py's LEGACY_MAP."""
    counts = Counter(block_ids.tolist())
    by_count = sorted(counts, key=lambda idx: -counts[idx])
    if len(by_count) > MAX_MATERIAL_SLOTS:
        names = [atlas.name(i) for i in by_count]
        raise ValueError(
            f"island needs {len(by_count)} distinct blocks but a turtle only has "
            f"{MAX_MATERIAL_SLOTS} material slots: {names}"
        )
    return {block_idx: slot for slot, block_idx in enumerate(by_count, start=1)}


def write_plan(path, bbox_min, bbox_max, atlas, local_idx, block_ids, palette):
    size = bbox_max - bbox_min
    lines = [
        f"OFFSET {int(bbox_min[0])} {int(bbox_min[1])} {int(bbox_min[2])}",
        f"BOUNDS 0 {int(size[0])} 0 {int(size[1])} 0 {int(size[2])}",
        f"BLOCKS {len(block_ids)}",
    ]
    for block_idx, slot in sorted(palette.items(), key=lambda kv: kv[1]):
        lines.append(f"# PALETTE {slot} {atlas.name(block_idx)}")

    # Bottom-up, then x, then z: a readable build order for progress
    # printouts. Not functionally required - turtles aren't affected by
    # gravity, so a placed block never needs support from underneath.
    order = np.lexsort((local_idx[:, 2], local_idx[:, 0], local_idx[:, 1]))
    for i in order:
        x, y, z = local_idx[i]
        slot = palette[int(block_ids[i])]
        lines.append(f"B {int(x)} {int(y)} {int(z)} {slot}")

    path.write_text("\n".join(lines) + "\n")


def write_tower_cfg(path, origin):
    path.write_text(
        "# generated by turtle_export/plan_from_structure.py\n"
        f"origin={origin[0]} {origin[1]} {origin[2]}\n"
        "xvec=1 0\n"
        "zvec=0 1\n"
    )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("structure_path", type=Path,
                     help="Structure .npz to convert (e.g. generate/output/scene_tiny.npz)")
    ap.add_argument("--turtles", type=int, default=None,
                     help="number of turtles/plans to produce (default: one per island found)")
    ap.add_argument("--origin", type=str, default=None,
                     help="world x,y,z that the structure's local (0,0,0) maps to "
                          "(default: world_import/config.json's origin, else 0,0,0)")
    ap.add_argument("--out-dir", type=Path, default=None,
                     help="output directory (default: turtle_export/output/<structure name>/)")
    ap.add_argument("--min-blocks", type=int, default=8,
                     help="drop connected components smaller than this many blocks - filters out "
                          "floating decoration specks that never touch their own island's main "
                          "body (default: 8; 1 keeps everything)")
    args = ap.parse_args()

    structure = Structure.load(args.structure_path)
    print(f"loaded {args.structure_path} - shape {structure.shape}")

    islands = find_islands(structure, min_blocks=args.min_blocks)
    print(f"found {len(islands)} island(s) (connected component(s) of solid voxels)")
    if not islands:
        raise SystemExit("no solid voxels found - nothing to export")

    if args.turtles is not None and args.turtles < len(islands):
        raise SystemExit(
            f"--turtles {args.turtles} is fewer than the {len(islands)} island(s) found; "
            f"this tool builds one plan per island, one island per turtle - "
            f"re-run with --turtles {len(islands)} or higher."
        )

    origin = (tuple(int(v) for v in args.origin.split(","))
              if args.origin else default_origin())
    out_dir = args.out_dir or (HERE / "output" / args.structure_path.stem)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Clear stale Txx.plan files from a previous run into this same
    # directory before writing the new batch - otherwise a re-run that
    # finds fewer islands than last time (a filter tightened, a theme
    # tweaked, ...) only overwrites T01..Tk and leaves higher-numbered
    # plans from the old, larger batch sitting there unchanged.
    for stale in out_dir.glob("T*.plan"):
        stale.unlink()

    write_tower_cfg(out_dir / "tower.cfg", origin)
    print(f"tower origin: {origin}  (world x,y,z that structure-space 0,0,0 maps to)")

    manifest = {
        "structure": str(args.structure_path),
        "origin": list(origin),
        "turtles": [],
    }
    for i, island in enumerate(islands, start=1):
        turtle_id = f"T{i:02d}"
        palette = build_palette(structure.atlas, island["block_ids"])
        write_plan(out_dir / f"{turtle_id}.plan", island["bbox_min"], island["bbox_max"],
                   structure.atlas, island["local_idx"], island["block_ids"], palette)

        bbox_min, bbox_max = island["bbox_min"], island["bbox_max"]
        size = bbox_max - bbox_min + 1
        # Where nexus_deploy.lua will send this turtle (identity xvec/zvec):
        # world x/z = origin + OFFSET; world y = origin_y + OFFSET_y + 1
        # (the turtle stands one block above its first build layer).
        start_world = [origin[0] + int(bbox_min[0]), origin[1] + int(bbox_min[1]) + 1,
                        origin[2] + int(bbox_min[2])]
        materials = {structure.atlas.name(idx): int(Counter(island["block_ids"].tolist())[idx])
                     for idx in palette}

        manifest["turtles"].append(dict(
            turtle=turtle_id,
            offset=[int(v) for v in bbox_min],
            size=[int(v) for v in size],
            blocks=len(island["block_ids"]),
            start_world=start_world,
            materials=materials,
        ))
        print(f"  {turtle_id}: {len(island['block_ids']):>6} blocks  size={tuple(int(v) for v in size)}  "
              f"start_world={tuple(start_world)}  materials={list(materials)}")

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(islands)} plan(s) + tower.cfg + manifest.json to {out_dir}")
    print("copy tower.cfg and each Txx.plan next to printer_david/turtles/*.lua on that "
          "turtle's computer, then run: nexus_deploy Txx.plan   (then nexus_builder_gps Txx.plan)")


if __name__ == "__main__":
    main()
