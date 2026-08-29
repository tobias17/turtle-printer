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
   `generate/islands/` (floating islands, one file per biome theme —
   `grass.py`, `volcano.py`, `snow.py`, `desert.py`, `crystal.py`,
   `mushroom.py`), `spire.py` (a dark central tower), `tree.py` (a giant
   fantasy tree). These are being built out for a new base design (a
   massive central tree/spire surrounded by floating islands) and are
   **not yet wired into the mesh-to-turtle pipeline** — that integration is
   deliberately deferred until the generation tooling itself settles. Don't
   assume `slice.py` can currently consume their output.

## `generate/` conventions

- **`generate/utils.py`** is the shared library every generator script
  uses. Don't duplicate logic across generator scripts — if two generators
  need the same helper (noise, rendering, export), it belongs in
  `utils.py`.
- **`generate/islands/common.py`** is the shared library for the island
  theme generators specifically (silhouette/taper carving, drip
  decoration, CLI plumbing). Each theme file (`grass.py`, `volcano.py`,
  ...) should only contain what's actually unique to that biome — its
  block palette, gradient, and decoration. If a new theme needs a tweak to
  the shared carve/drip loop itself, extend `common.py` rather than forking
  it.
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
  - `render_screenshot()` in `utils.py` uses axis 1 as vertical directly
    (no internal axis swap) — it renders via Open3D, not matplotlib, so
    there's no "3rd axis must be vertical" constraint to work around. If a
    preview ever looks rotated/sideways after adding a new generator, check
    that generator's own axis convention first before touching the
    renderer.
- **`render_screenshot()` renders every exposed block face at full voxel
  resolution** — flat per-face color (matching Minecraft's fixed per-face
  ambient shading: top brightest, bottom darkest), no texture, no lighting
  model, no downsampling. It builds a triangle mesh from only the
  air-adjacent faces (fully vectorized numpy, no per-voxel Python loop —
  see `_build_exposed_face_mesh`) and renders it offscreen with Open3D's
  legacy `Visualizer` (`visible=False`). Faces between two solid blocks are
  omitted because they're provably invisible from any outside camera angle,
  not because of a resolution shortcut — the render is meant to show
  exactly what the structure would look like assembled in Minecraft, minus
  block textures.
  - Open3D's newer offscreen renderer
    (`o3d.visualization.rendering.OffscreenRenderer`) does **not** work in
    this environment — it requires an EGL headless context, which errors
    with "EGL Headless is not supported on this platform" on Windows. Use
    the legacy `o3d.visualization.Visualizer` (`create_window(visible=False)`
    + `capture_screen_image`) instead; that one works headless here via a
    real (hidden) native GL context. Don't "fix" this by switching back to
    the newer API.
  - The camera is a hand-built pinhole (see `_make_camera`), not Open3D's
    `set_front`/`set_lookat` convenience API — this gives exact,
    recoverable pixel↔world math (`_project_points`), which the height
    ruler depends on to place its ticks precisely. If you change the camera
    setup, keep it as an explicit intrinsic/extrinsic construction, not a
    heuristic auto-fit, or the ruler will drift out of alignment.
  - `_make_camera` is a *perspective* camera, so a world point's projected
    height depends on its distance from the camera, not just its Y —
    `_draw_ruler` had a real bug from this (fixed once, don't reintroduce
    it): it used to offset the ruler sideways along raw world X, which for
    a side view (azim=-90) is the camera's own depth axis, so the ruler
    sat at a different distance than the structure and its ticks drifted
    out of vertical sync with it (only became obvious once a generator's
    base legitimately reached y=0 — before that a pre-existing gap at the
    bottom masked it). Any point used for on-image overlays (ruler,
    annotations, ...) must be offset along the camera's own screen-right
    vector (`extrinsic[0, :3]`, depth-neutral by construction), never
    along a raw world axis.
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
  This traces back to a real bug with the old matplotlib-based renderer,
  which downsampled and could drop a hollowed thin shell below its fill
  threshold, making solid structures (e.g. a tree trunk) disappear from the
  render entirely. The current Open3D-based renderer doesn't downsample at
  all, so that specific failure mode is gone — `hollow_out` only ever
  removes voxels with zero exposed faces, so rendering before or after
  hollowing is now visually identical either way. Keep rendering before
  hollowing anyway (it's the simpler pipeline order and costs nothing extra
  — see `render_screenshot`'s docstring), but don't assume this ordering is
  still load-bearing for correctness if you're touching this code.
- A fixed camera framing (see `_make_camera`'s `margin`) always leaves some
  blank space around the structure, and that space isn't uniform across
  view angles (a flat/wide structure viewed edge-on leaves huge blank bands
  above/below it). `utils.py`'s renderer crops this with `_autocrop` (trim
  the rendered PNG to actual content) plus a PIL-composited title bar,
  rather than trying to frame each view exactly. Don't reintroduce
  per-view manual framing as the fix for this — cropping after the fact is
  simpler and handles every view angle uniformly.

## Island theme design requirements

Every file in `generate/islands/` besides `common.py` and `rollup.py` (e.g.
`grass.py`, `volcano.py`, `crystal.py`, ...) is one biome "theme" built on
the shared carve/drip machinery in `common.py`. A theme was rejected once
already for breaking rule 1 (`cherry.py`'s first version reshaped the top
into a stepped ziggurat) - these rules are the concrete, checkable bar a
theme must clear, written down so that doesn't happen again:

1. **The top is ALWAYS perfectly flat and a single solid color.** Every
   column's top surface is the same Y level (`flat_top=True`) and the same
   one hardcoded block - no per-voxel/per-column randomness, no rare
   "fleck" swapped in at low probability, no exceptions carved into the top
   for any reason. If a theme's whole premise is reshaping the top surface
   (terraces, spikes, a hole), that premise is disqualified outright - move
   the theme's distinguishing shape onto the underside instead. This is the
   one rule with zero exceptions.
2. **The underside must be shaped around one concrete, nameable thing that
   fits the theme - not texture noise.** Pick ONE structural idea and
   implement it as a deliberate post-process over `columns`: flatten most
   columns to a shared shallow depth, exempt a specific set chosen by an
   explicit rule (a radius band, angular symmetry, distance from center,
   clumped noise, alternating wedges), and recolor/extend only that
   exempted set. Existing examples: crystal.py's geode floor + spikes,
   desert.py's mesa terraces, mushroom.py's cap + stem, coral.py's branching
   colonies, ruins.py's broken pillars, swamp.py's rim root trunks,
   prismarine.py's symmetric guard towers, snow.py's calved wedges. A
   smooth per-column depth blend, or a pile of independent per-voxel color
   choices, reads as texture, not shape, and does not satisfy this rule
   even if it's colorful.
3. **Keep the palette minimal and every band solid.** 2-3 blocks for the
   bulk crust/gradient list, chosen by rounding to the nearest band index
   (`idx = round(pos)`, not a probabilistic blend) so each band is one flat
   color - plus a small number of accent blocks reserved exclusively for the
   structural feature and optional decoration. No "fleck chance" that
   swaps in a random block at low probability anywhere in the bulk
   material. Any smooth-noise `jitter` passed into the gradient picker must
   come from a per-column field (`value_noise_2d`, indexed by `[xi, zi]`
   only) - never redraw it per-voxel (e.g. never add a fresh
   `rng.uniform(...)` inside `body_block_fn`, and never recolor a branch/
   vein/trunk with an independent random pick per voxel along its length)
   - that's what turns clean bands and clean structural features into
   static.
4. **Don't touch `common.py` or any other theme file** when adding or
   fixing a theme. Add new local functions/parameters within the theme's
   own file; if the shared carve/drip loop genuinely needs a new
   capability, extend `common.py` in a way that defaults to a no-op for
   every existing theme (a new optional parameter, not a behavior change).
5. **Verify by rendering, not by reading the code.** After writing or
   editing a theme, run `generate/islands/rollup.py` with **no arguments**
   - it regenerates THE canonical rollup (every theme at every standard
     diameter, one consolidated grid image, columns = theme, rows =
     diameter) always at the same fixed path,
     `generate/out/renders/rollup.png`, so a regression in one theme, or in
     an unrelated theme you didn't mean to touch, is visible immediately.
     That path and that grid shape are the single source of truth for "the
     rollup" - the script itself refuses to run a partial/non-standard
     render (fewer themes, different diameters, decorations on, ...)
     without an explicit `--out` pointed at a different file, specifically
     so a one-off debugging render can never silently overwrite the
     canonical one. Don't work around that guard - if you need `--out`,
     you're already making a scratch render, not the rollup.
   Confirm from the render: (a) the top is one solid color at every
   diameter, (b) the underside reads as the intended shape, not noise, and
   (c) check programmatically that every column's Y-values form one
   contiguous run (no gaps) - a gap can be invisible from outside the
   rendered mesh.

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
- **Don't run ad hoc `python -c "..."` one-liners directly.** Write the
  script to `generate/out/tmp.py` instead (gitignored scratch space) and run
  it by invoking the venv's Python **directly** on that one file:
  `c:\Users\tobia\Documents\repos\turtle-printer\.venv\Scripts\python.exe c:\Users\tobia\Documents\repos\turtle-printer\generate\out\tmp.py`
  - Reuse that same `generate/out/tmp.py` path for every throwaway/diagnostic
    script in a session — overwrite it each time rather than inventing new
    filenames (`test.py`, `hires_test.py`, ...). One well-known scratch file
    is easy for the user to glance at and approve; a new name each time is
    not.
  - Run it as a single, plain command: no `cd ... &&`, no `source
    .venv/Scripts/activate &&`, no chaining with other commands. Use the
    absolute path to `python.exe` and the absolute path to `tmp.py` so `cd`
    is never needed.
  - This applies to every one-off numeric/rendering check, not just the
    obvious ones — regenerating a structure to compare render settings,
    checking array stats, timing a function, etc.
- **Keep shell commands simple and atomic**, especially anything touching
  git — don't chain unrelated operations (cleanup + add + status, etc.)
  into one command. Let the user drive git themselves unless they
  explicitly ask you to stage/commit.
- **Don't delete gitignored output for "cleanliness."** If it's under
  `generate/out/` or similar, leave it — it's not tracked and not in the
  user's way.
