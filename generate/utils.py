"""
Shared utilities for the procedural structure generators in generate/
(island.py, tree.py, ...).

Canonical data model
---------------------
Every generator ultimately produces a `Structure`: a 3D array of block
indices (X, Y, Z, Y up, 0 = air) plus an `Atlas` naming each index. That's
the boundary format between "generate a shape" and everything downstream:

  1. render_screenshot() -> a PNG, for quick iteration on the shape.
  2. Structure.to_schematic() -> a .schem, to paste into a creative-mode
     game save with WorldEdit and see it live.
  3. Structure.save() -> a .npz, the format the turtle printer pipeline
     (voxel.py / slice.py) will eventually ingest directly.

Right now only (1) is wired up end to end in the generator scripts; (2) and
(3) are implemented here so they're a one-line call away once we need them.
"""

import json
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Atlas / Structure
# ---------------------------------------------------------------------------

class Atlas:
    """Bidirectional legend mapping block names (e.g. "minecraft:stone") to
    small integer indices for a Structure's voxel array. Index 0 is always
    reserved for air."""

    AIR = "minecraft:air"

    def __init__(self):
        self._names = [self.AIR]
        self._index = {self.AIR: 0}

    def add(self, name):
        """Registers `name` if new and returns its index (idempotent)."""
        if name not in self._index:
            self._index[name] = len(self._names)
            self._names.append(name)
        return self._index[name]

    def name(self, index):
        return self._names[index]

    def index(self, name):
        return self._index[name]

    def __len__(self):
        return len(self._names)

    @property
    def names(self):
        return list(self._names)

    def to_dict(self):
        return {"names": self._names}

    @classmethod
    def from_dict(cls, d):
        atlas = cls()
        atlas._names = list(d["names"])
        atlas._index = {name: i for i, name in enumerate(atlas._names)}
        return atlas


class Structure:
    """A generated build: `data` is a 3D int16 array of Atlas indices
    (X, Y, Z, Y up, 0 = air)."""

    def __init__(self, data, atlas):
        self.data = data
        self.atlas = atlas

    @classmethod
    def from_data(cls, data, atlas):
        return cls(np.asarray(data, dtype=np.int16), atlas)

    @property
    def shape(self):
        return self.data.shape

    def save(self, path):
        """Saves to a .npz containing the voxel array and the atlas legend.
        Returns the path actually written (suffix forced to .npz)."""
        path = Path(path).with_suffix(".npz")
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, data=self.data, atlas=json.dumps(self.atlas.to_dict()))
        return path

    @classmethod
    def load(cls, path):
        npz = np.load(path)
        atlas = Atlas.from_dict(json.loads(str(npz["atlas"])))
        return cls(npz["data"], atlas)

    def to_schematic(self, path_folder, name):
        """Exports directly to a WorldEdit-loadable .schem, so a generated
        structure can be dropped into a creative-mode save to see it live
        before committing to a real turtle build. Returns None (with a
        message) if mcschematic isn't installed."""
        try:
            import mcschematic
        except ImportError:
            print("mcschematic not installed -- run `pip install mcschematic` "
                  "to export a .schem for WorldEdit.")
            return None

        schem = mcschematic.MCSchematic()
        xs, ys, zs = np.nonzero(self.data)
        for x, y, z in zip(xs.tolist(), ys.tolist(), zs.tolist()):
            block = self.atlas.name(int(self.data[x, y, z]))
            # mcschematic axes are (x, y, z) with y = up -> map our z to y
            schem.setBlock((x, z, y), block)

        path_folder = Path(path_folder)
        path_folder.mkdir(parents=True, exist_ok=True)
        schem.save(str(path_folder), name, mcschematic.Version.JE_1_20_1)
        out_path = path_folder / f"{name}.schem"
        print(f"Saved {out_path} ({len(xs)} blocks) -- load it in-game with "
              f"WorldEdit: //schem load {name}  then  //paste")
        return out_path


# ---------------------------------------------------------------------------
# Noise helpers (pure numpy -- no external noise library needed)
# ---------------------------------------------------------------------------

def value_noise_2d(res, grid_size, seed):
    """Smooth 2D value noise on an res x res grid, roughly in [-1, 1]."""
    rng = np.random.default_rng(seed)
    coarse = rng.uniform(-1, 1, (grid_size + 1, grid_size + 1))

    coords = np.linspace(0, grid_size - 1e-9, res)
    xi = np.floor(coords).astype(int)
    xf = coords - xi

    def smoothstep(t):
        return t * t * (3 - 2 * t)

    X, Y = np.meshgrid(xi, xi, indexing="ij")
    XF, YF = np.meshgrid(xf, xf, indexing="ij")
    sx, sy = smoothstep(XF), smoothstep(YF)

    top = coarse[X, Y] * (1 - sx) + coarse[X + 1, Y] * sx
    bot = coarse[X, Y + 1] * (1 - sx) + coarse[X + 1, Y + 1] * sx
    return top * (1 - sy) + bot * sy


def fractal_noise_2d(X, Y, seed, n=5, base_freq=0.02, amp=1.0, freq_growth=1.8, amp_decay=0.55):
    """Fractal-ish 2D value noise built from a handful of randomly-oriented
    sine waves (Fourier synthesis), evaluated at arbitrary (X, Y) coordinate
    arrays (unlike value_noise_2d, which is grid-index based)."""
    rng = np.random.RandomState(seed)
    val = np.zeros_like(X, dtype=np.float64)
    freq, a = base_freq, amp
    for _ in range(n):
        ang = rng.uniform(0, 2 * np.pi)
        kx, ky = np.cos(ang) * freq, np.sin(ang) * freq
        phase = rng.uniform(0, 2 * np.pi)
        val += a * np.sin(kx * X + ky * Y + phase)
        freq *= freq_growth
        a *= amp_decay
    return val


def angular_noise_1d(theta, seed, n=5, amp=1.0):
    """1D angular noise for an organic (non-circular) footprint edge."""
    rng = np.random.RandomState(seed)
    val = np.zeros_like(theta, dtype=np.float64)
    for _ in range(n):
        f = rng.uniform(2, 7)
        p = rng.uniform(0, 2 * np.pi)
        val += np.sin(f * theta + p)
    return amp * val / n


def spherical_bump_noise(theta, phi, seed, n=4, amp=1.0):
    """Cheap pseudo-noise over spherical angles (sum of sines), used to add
    bark/surface roughness to radius profiles."""
    rng = np.random.RandomState(seed)
    f1 = rng.uniform(1.5, 5.0, n)
    f2 = rng.uniform(1.5, 5.0, n)
    p1 = rng.uniform(0, 2 * np.pi, n)
    p2 = rng.uniform(0, 2 * np.pi, n)
    val = np.zeros_like(theta, dtype=np.float64)
    for k in range(n):
        val += np.sin(f1[k] * theta + p1[k]) * np.cos(f2[k] * phi + p2[k])
    return amp * val / n


# ---------------------------------------------------------------------------
# Preview rendering
# ---------------------------------------------------------------------------

def _downsample(data, atlas, target_max_dim):
    """Anti-aliased downsample for preview rendering: box-filter (average)
    occupancy and per-block-type fraction BEFORE subsampling, so fine
    surface texture is band-limited into a coherent lower-res shape instead
    of aliasing into a noisy checkerboard. Naive point-sampling looks wrong
    AND renders far slower, since the aliased checkerboard defeats
    matplotlib's hidden-face culling."""
    factor = max(1, max(data.shape) // target_max_dim)
    if factor == 1:
        filled = data != 0
        return filled, data, factor

    from scipy.ndimage import uniform_filter

    occ = (data != 0).astype(np.float32)
    occ_smooth = uniform_filter(occ, size=factor, mode="constant")
    sub = tuple(slice(factor // 2, None, factor) for _ in range(3))
    filled = occ_smooth[sub] > 0.5

    best_id = np.zeros(filled.shape, dtype=data.dtype)
    best_frac = np.zeros(filled.shape, dtype=np.float32)
    for block_id in range(1, len(atlas)):
        frac = uniform_filter((data == block_id).astype(np.float32), size=factor, mode="constant")[sub]
        better = frac > best_frac
        best_frac = np.where(better, frac, best_frac)
        best_id = np.where(better, block_id, best_id)
    best_id = np.where(filled, best_id, 0)
    return filled, best_id, factor


def _ids_to_colors(best_id, atlas, palette, default_color=(0.6, 0.6, 0.6)):
    from matplotlib.colors import to_hex

    colors = np.empty(best_id.shape, dtype=object)
    for idx in range(1, len(atlas)):
        # to_hex() normalizes both hex strings and RGB(A) tuples to a plain
        # hex string, which numpy always treats as a scalar object -- an
        # RGB tuple assigned directly gets broadcast elementwise across the
        # masked positions instead of being stored as one object per voxel.
        color = to_hex(palette.get(atlas.name(idx), default_color))
        colors[best_id == idx] = color
    return colors


BG_COLOR = "#bfe3ff"


def _autocrop(rgb, bg_color=BG_COLOR, pad=20, tol=6):
    """Crops away the (uniformly-colored) background margin matplotlib's 3D
    axes always reserve around the actual voxel silhouette -- Axes3D
    reserves a roughly cubic viewport sized for any viewing angle, so a
    near-edge-on view (low elevation, a flat/wide structure, ...) leaves
    huge unused bands above/below the content that plain tight_layout
    can't remove."""
    from matplotlib.colors import to_rgb

    bg = np.array([round(c * 255) for c in to_rgb(bg_color)], dtype=np.int16)
    diff = np.abs(rgb.astype(np.int16) - bg).sum(axis=-1)
    mask = diff > tol
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return rgb
    r0, r1 = max(0, rows.min() - pad), min(rgb.shape[0], rows.max() + 1 + pad)
    c0, c1 = max(0, cols.min() - pad), min(rgb.shape[1], cols.max() + 1 + pad)
    return rgb[r0:r1, c0:c1]


def _add_title_bar(img, title, bg_color=BG_COLOR, text_color="#1a1a1a", font_size=28, pad=14):
    """Composites a title caption above `img` as a flat color bar sized to
    fit -- drawn with PIL rather than matplotlib's own title, since a
    matplotlib title reserves layout space at figure-render time (before
    the content's actual on-screen size is known) and re-introduces the
    same wasted-space problem _autocrop fixes."""
    from PIL import Image, ImageDraw, ImageFont

    font = None
    for candidate in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(candidate, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(size=font_size)

    width, height = img.size
    bar_height = font_size + pad * 2
    bar = Image.new("RGB", (width, bar_height), bg_color)
    draw = ImageDraw.Draw(bar)
    bbox = draw.textbbox((0, 0), title, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text(((width - text_w) / 2, pad), title, fill=text_color, font=font)

    combined = Image.new("RGB", (width, height + bar_height), bg_color)
    combined.paste(bar, (0, 0))
    combined.paste(img, (0, bar_height))
    return combined


def _render_one_view(filled, colors, factor, view, title, out_path):
    import io

    import matplotlib.pyplot as plt
    from PIL import Image

    fig = plt.figure(figsize=(12, 12))
    fig.patch.set_facecolor(BG_COLOR)
    ax = fig.add_axes([0, 0, 1, 1], projection="3d")
    ax.set_facecolor(BG_COLOR)
    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.set_facecolor(BG_COLOR)
        pane.set_edgecolor(BG_COLOR)
    ax.voxels(filled, facecolors=colors, edgecolor=None, shade=True)
    ax.set_box_aspect(filled.shape)
    ax.set_axis_off()
    ax.view_init(elev=view.get("elev", 11), azim=view.get("azim", -55))

    view_title = title
    if view.get("ruler"):
        # A vertical ruler beside the structure with tick marks every
        # tick_step real blocks, so foreshortening from the isometric angle
        # can't make the scale misleading.
        nz = np.nonzero(filled)
        z_max_idx = int(nz[2].max()) if len(nz[2]) else filled.shape[2]
        real_h = z_max_idx * factor
        tick_step = view.get("tick_step", 50)
        ruler_x = -filled.shape[0] * 0.12
        ruler_y = filled.shape[1] / 2
        ax.plot([ruler_x, ruler_x], [ruler_y, ruler_y], [0, z_max_idx], color="black", linewidth=1.5)
        for real_z in range(0, real_h + 1, tick_step):
            zi = real_z / factor
            ax.plot([ruler_x - filled.shape[0] * 0.02, ruler_x + filled.shape[0] * 0.02],
                    [ruler_y, ruler_y], [zi, zi], color="black", linewidth=1.2)
            ax.text(ruler_x - filled.shape[0] * 0.07, ruler_y, zi, f"{real_z}",
                    fontsize=9, ha="right", va="center")
        view_title = f"{title + ' - ' if title else ''}actual height: {real_h} blocks"

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, facecolor=BG_COLOR)
    plt.close(fig)
    buf.seek(0)
    cropped = _autocrop(np.array(Image.open(buf).convert("RGB")))
    img = Image.fromarray(cropped)
    if view_title:
        img = _add_title_bar(img, view_title)
    img.save(out_path)
    print(f"Saved render to {out_path}")


def render_screenshot(structure, out_path, title=None, palette=None, target_max_dim=100, views=None):
    """Renders `structure` as full shaded blocks and saves PNG(s).

    palette   - dict of block name -> matplotlib color spec (hex string or
                RGB(A) tuple). Blocks missing from the palette fall back to
                a neutral gray.
    views     - optional list of dicts, each with any of:
                  elev, azim   - camera angles (default: isometric)
                  ruler        - draw a labeled height ruler (default: off)
                  tick_step    - ruler label spacing in real blocks
                  suffix       - appended to out_path's stem for this view
                Defaults to a single isometric view saved to out_path.
                When explicitly given, returns a list of paths (one per
                view) instead of a single path.
    """
    # Structure.data is (X, Y, Z) with Y (axis 1) vertical, per the Atlas/
    # Structure contract -- but matplotlib's ax.voxels() always treats an
    # array's 3rd axis as the vertical one. Swap Y/Z once here so every
    # caller gets a correctly-oriented render regardless of which axis their
    # generator happens to consider "up" internally.
    display_data = np.swapaxes(structure.data, 1, 2)
    filled, best_id, factor = _downsample(display_data, structure.atlas, target_max_dim)
    colors = _ids_to_colors(best_id, structure.atlas, palette or {})

    out_path = Path(out_path)
    view_specs = views if views is not None else [{}]

    saved = []
    for view in view_specs:
        suffix = view.get("suffix", "")
        view_path = out_path.with_stem(out_path.stem + suffix) if suffix else out_path
        _render_one_view(filled, colors, factor, view, title, view_path)
        saved.append(view_path)

    return saved if views is not None else saved[0]
