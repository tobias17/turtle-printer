# AGENTS.md

Operating notes for AI agents working in this repo. Read this before making
changes.

## What this repo is

Generates Lua scripts for a swarm of ComputerCraft turtles in Minecraft that
3D-print large structures. There are two pipelines, at different stages of
maturity:

1. **Mesh-to-turtle pipeline (production).** `voxel.py` converts a 3D mesh
   (e.g. a statue `.obj`) into a hollow voxel shell (`.npy`, boolean array).
   `slice.py` slices that shell into per-turtle build paths (TSP-ordered
   coordinates per layer) and injects them into the Lua templates in
   `templates/` to produce a runnable `main.lua`. This is the path used for
   real builds so far (see `workspaces/statue/`).
2. **Procedural generators (`generate/`, work in progress).** Python scripts
   that generate structures algorithmically instead of from a mesh —
   `island.py` (floating islands), `tree.py` (a giant fantasy tree). These
   are being built out for a new base design (a massive central tree
   surrounded by floating islands) and are **not yet wired into the
   mesh-to-turtle pipeline** — that integration is deliberately deferred
   until the generation tooling itself settles. Don't assume `slice.py`
   can currently consume their output.

## `generate/` conventions

- **`generate/utils.py`** is the shared library both generator scripts use.
  Don't duplicate logic across generator scripts — if two generators need
  the same helper (noise, rendering, export), it belongs in `utils.py`.
- **Canonical format: `Atlas` + `Structure`.** A `Structure` wraps a 3D
  `int16` array of block indices, shape `(X, Y, Z)` with **Y (axis 1)
  vertical**, 0 = air. An `Atlas` is the index-to-block-name legend. This is
  the boundary format between "generate a shape" and everything downstream.
  - If a generator's own internal grid uses a different up-axis (e.g.
    `tree.py`'s raw grid is `(X, Y, Z)` with **Z** vertical, inherited from
    how it was originally written), transpose to the Y-up convention at the
    point you build the `Structure` — see `tree.py`'s `grid_to_structure`
    for the pattern. Don't let that transpose leak into the generator's
    internal math; keep it a one-line boundary conversion.
  - `render_screenshot()` in `utils.py` already accounts for the Y-up
    convention (it swaps axes internally for matplotlib, which expects the
    3rd array axis to be vertical). If a preview ever looks rotated/sideways
    after adding a new generator, check that generator's axis convention
    first before touching the renderer.
- **Three intended outputs per generator**, in order of current priority:
  1. PNG preview via `render_screenshot()` — the only one actively used
     right now, for fast iteration on shape/look.
  2. `.schem` via `Structure.to_schematic()` — load into a creative-mode
     game save with WorldEdit to see it live. Wired up (`--schem` flag) but
     secondary.
  3. `.npz` via `Structure.save()` — the format the mesh-to-turtle pipeline
     will eventually ingest directly. Not consumed by anything yet; treat
     it as forward-compatibility, not a working integration.
- **Preview before hollowing.** If a generator hollows out buried interior
  voxels for efficiency (see `tree.py`'s `hollow_out`), render the preview
  from the *unhollowed* grid first, then hollow before saving/exporting.
  Downsampling a hollowed thin shell for preview can drop it below the
  fill threshold and make solid structures (e.g. a tree trunk) disappear
  from the render entirely — this is a real bug that happened once already,
  not a hypothetical.
- matplotlib's 3D `voxels()` reserves a viewport sized for the object's full
  bounding box regardless of the current view angle, which leaves large
  blank margins at low elevation angles or for flat/wide structures.
  `utils.py`'s renderer works around this with `_autocrop` (crop the
  rendered PNG to actual content) plus a PIL-composited title bar rather
  than matplotlib's own title. Don't reintroduce `ax.set_title()` /
  `plt.tight_layout()` as the layout mechanism — it doesn't solve this.

## Environment

- Python deps are in `requirements.txt` (numpy, scipy, matplotlib, Pillow
  for `generate/`; open3d for `voxel.py`; opencv-python for `slice.py
  --debug`; mcschematic, optional, for `.schem` export). A `.venv/` is
  expected locally (gitignored) — there was no dependency tracking before,
  so don't assume any of this is globally installed.
- `generate/out/` (and any `**/out/*`) is gitignored — it's scratch output
  from running the generators, not build artifacts to commit.

## Working style for this repo

- **Verify by running the script, not just reading it.** This codebase is
  numerically/visually driven (noise fields, voxel geometry, rendered
  previews) — a change that type-checks or "looks right" can still produce
  a visibly wrong structure (sideways, missing a trunk, etc.). When you
  change generation or rendering code, actually run it and look at the
  output PNG before calling it done.
- **Don't run ad hoc `python -c "..."` one-liners directly.** Write a small
  script to a file (put throwaway/diagnostic scripts in `generate/out/`,
  which is gitignored) and run it with the venv's Python directly, e.g.
  `.venv/Scripts/python.exe generate/out/test.py`, rather than
  `source .venv/Scripts/activate && python -c ...`.
- **Keep shell commands simple and atomic**, especially anything touching
  git — don't chain unrelated operations (cleanup + add + status, etc.)
  into one command. Let the user drive git themselves unless they
  explicitly ask you to stage/commit.
- **Don't delete gitignored output for "cleanliness."** If it's under
  `generate/out/` or similar, leave it — it's not tracked and not in the
  user's way.
