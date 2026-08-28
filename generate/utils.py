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

# Per-face-direction brightness multipliers, matching Minecraft's own fixed
# ambient shading per cube face (top brightest, bottom darkest, the two
# horizontal axis pairs in between) -- this is what gives the render a sense
# of form using flat color alone, with no lighting model or texture involved.
_FACE_SHADE = {0: (0.8, 0.6), 1: (1.0, 0.5), 2: (0.8, 0.6)}  # axis -> (+dir, -dir)


def _build_exposed_face_mesh(data, atlas, palette, default_color=(0.6, 0.6, 0.6)):
    """Builds a triangle mesh with one quad per exposed block face -- every
    face of every block that borders air, at full voxel resolution, no
    downsampling or approximation of any kind. Faces between two solid
    blocks are omitted because they are provably invisible from any
    exterior camera angle (the definition of `hollow_out`'s "buried"
    voxels), not because of any resolution shortcut -- so this produces
    exactly what the structure would look like assembled in Minecraft,
    just without block textures (flat per-face color only).

    Entirely vectorized: each of the 6 face directions is one array-wide
    boolean comparison (a voxel's face is exposed if its neighbor in that
    direction is air or out of bounds) plus a batch of numpy index math to
    place that direction's quads -- no per-voxel Python loop, so this stays
    fast even at tens of millions of exposed faces.
    """
    import open3d as o3d
    from matplotlib.colors import to_rgb

    id_to_rgb = np.zeros((len(atlas), 3), dtype=np.float64)
    for idx in range(1, len(atlas)):
        id_to_rgb[idx] = to_rgb(palette.get(atlas.name(idx), default_color))

    solid = data != 0
    corners = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
    tri_local = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)

    # Winding order for a quad spanning axes (a0, a1) at fixed `axis` faces
    # +axis_hat (via the right-hand rule) only when (a0, a1, axis) is a
    # *cyclic* permutation of (0, 1, 2) -- true for axis 0 ((1,2,0)) and
    # axis 2 ((0,1,2)), but axis 1's (a0, a1) = (0, 2) makes (0, 2, 1) an
    # *odd* permutation, so its natural winding faces -axis_hat instead.
    # Open3D culls backfaces by default, so getting this wrong silently
    # drops exactly the top/bottom faces -- which is what "only parts of
    # the face rendered" turned out to be.
    axis_parity = {0: 1, 1: -1, 2: 1}

    all_verts, all_tris, all_colors = [], [], []
    vert_offset = 0
    for axis in range(3):
        a0, a1 = [a for a in range(3) if a != axis]
        for direction in (1, -1):
            # neighbor[i] must hold solid[i + direction] (the block on the
            # `direction` side of voxel i), so exposed = solid & ~neighbor
            # finds voxels whose `direction`-side neighbor is air. Getting
            # src/dst backwards here (an earlier version of this code did)
            # doesn't just mislabel which set is which -- combined with the
            # `base[axis] += 1` below, it places direction=1's faces one
            # step short (at the *hidden* boundary between two solid
            # voxels) and direction=-1's faces one step short the other
            # way, leaving the real exposed boundary bare on both sides.
            # That reads as literal holes in the surface.
            neighbor = np.zeros_like(solid)
            src, dst = [slice(None)] * 3, [slice(None)] * 3
            if direction == 1:
                src[axis], dst[axis] = slice(1, None), slice(0, -1)
            else:
                src[axis], dst[axis] = slice(0, -1), slice(1, None)
            neighbor[tuple(dst)] = solid[tuple(src)]
            exposed = solid & ~neighbor

            idx_arr = np.argwhere(exposed)
            if len(idx_arr) == 0:
                continue
            shade = _FACE_SHADE[axis][0 if direction == 1 else 1]
            colors = id_to_rgb[data[exposed]] * shade

            base = idx_arr.astype(np.float64)
            if direction == 1:
                base[:, axis] += 1.0
            n = len(idx_arr)
            quad = np.repeat(base[:, None, :], 4, axis=1)
            quad[:, :, a0] += corners[None, :, 0]
            quad[:, :, a1] += corners[None, :, 1]

            tris = tri_local[:, ::-1] if direction != axis_parity[axis] else tri_local
            tris = (tris[None, :, :] + (np.arange(n, dtype=np.int64) * 4)[:, None, None]).reshape(-1, 3)
            tris += vert_offset

            all_verts.append(quad.reshape(-1, 3))
            all_tris.append(tris)
            all_colors.append(np.repeat(colors, 4, axis=0))
            vert_offset += n * 4

    mesh = o3d.geometry.TriangleMesh()
    if all_verts:
        mesh.vertices = o3d.utility.Vector3dVector(np.concatenate(all_verts))
        mesh.triangles = o3d.utility.Vector3iVector(np.concatenate(all_tris).astype(np.int32))
        mesh.vertex_colors = o3d.utility.Vector3dVector(np.concatenate(all_colors))
    return mesh


def _make_camera(center, radius, elev_deg, azim_deg, width, height, vfov_deg=25.0, margin=1.2):
    """Builds a pinhole camera (standard computer-vision convention: X
    right, Y down, Z forward) framing a sphere of `radius` around `center`,
    looking in from `elev_deg`/`azim_deg` (degrees above the horizontal
    plane / around the vertical Y axis). A narrow vertical FOV keeps
    perspective distortion small so the render reads like the orthographic
    isometric views these structures are normally judged by, while still
    giving exact, queryable pixel<->world math (see `_project_points`) for
    drawing the height ruler in the right place afterward."""
    import open3d as o3d

    elev, azim = np.radians(elev_deg), np.radians(azim_deg)
    cam_dir = np.array([np.cos(elev) * np.sin(azim), np.sin(elev), np.cos(elev) * np.cos(azim)])
    vfov = np.radians(vfov_deg)
    distance = (radius / np.sin(vfov / 2)) * margin
    cam_pos = center + cam_dir * distance

    forward = -cam_dir
    world_up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    up_cam = np.cross(right, forward)
    R = np.stack([right, -up_cam, forward], axis=0)
    extrinsic = np.eye(4)
    extrinsic[:3, :3] = R
    extrinsic[:3, 3] = -R @ cam_pos

    f = (height / 2) / np.tan(vfov / 2)
    cx, cy = width / 2 - 0.5, height / 2 - 0.5
    params = o3d.camera.PinholeCameraParameters()
    params.intrinsic = o3d.camera.PinholeCameraIntrinsic(width, height, f, f, cx, cy)
    params.extrinsic = extrinsic
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]])
    return params, extrinsic, K


def _project_points(points, K, extrinsic):
    """World-space (N, 3) points -> pixel (N, 2) coordinates, using the
    exact camera built by `_make_camera` -- lets the height ruler line up
    with the actual render instead of an approximated overlay."""
    homogeneous = np.hstack([points, np.ones((len(points), 1))])
    cam = (extrinsic @ homogeneous.T).T[:, :3]
    pix = (K @ cam.T).T
    return pix[:, :2] / pix[:, 2:3]


BG_COLOR = "#bfe3ff"


def _autocrop(rgb, bg_color=BG_COLOR, pad=20, tol=6):
    """Crops away the (uniformly-colored) background margin left by
    `_make_camera`'s fixed framing -- the camera is sized to fit the
    structure's bounding *sphere* from any angle, so a near-edge-on view
    (low elevation, a flat/wide structure, ...) leaves large unused bands
    above/below the content that the fixed framing alone can't remove."""
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
    same wasted-space problem _autocrop fixes.

    The bar widens (rather than clipping the text) when the title is wider
    than `img` -- a real case now that `_autocrop` can produce quite narrow
    crops (e.g. a side view's height-ruler caption easily exceeds a thin
    structure's own width)."""
    from PIL import Image, ImageDraw

    font = _load_font(font_size)
    width, height = img.size
    bar_height = font_size + pad * 2
    text_w = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), title, font=font)[2]
    bar_width = max(width, text_w + pad * 2)

    bar = Image.new("RGB", (bar_width, bar_height), bg_color)
    draw = ImageDraw.Draw(bar)
    draw.text(((bar_width - text_w) / 2, pad), title, fill=text_color, font=font)

    combined = Image.new("RGB", (bar_width, height + bar_height), bg_color)
    combined.paste(bar, (0, 0))
    combined.paste(img, ((bar_width - width) // 2, bar_height))
    return combined


def _load_font(size):
    from PIL import ImageFont

    for candidate in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _draw_ruler(img, K, extrinsic, bbox_min, bbox_max, y_max, tick_step):
    """Draws a vertical height ruler beside the structure directly onto the
    rendered pixels, using `_project_points` so its ticks land at their
    exact real-world height regardless of camera angle -- then returns the
    title-bar text to go with it. Drawn before `_autocrop` so the ruler
    rides along with the crop like any other non-background content."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    font = _load_font(16)
    x = bbox_min[0] - (bbox_max[0] - bbox_min[0]) * 0.15
    z = (bbox_min[2] + bbox_max[2]) / 2

    top, bottom = _project_points(np.array([[x, y_max, z], [x, 0, z]]), K, extrinsic)
    draw.line([tuple(bottom), tuple(top)], fill="black", width=2)
    for real_y in range(0, y_max + 1, tick_step):
        p = _project_points(np.array([[x, real_y, z]]), K, extrinsic)[0]
        draw.line([(p[0] - 10, p[1]), (p[0] + 10, p[1])], fill="black", width=2)
        draw.text((p[0] - 16, p[1]), str(real_y), fill="black", font=font, anchor="rm")
    return f"actual height: {y_max} blocks"


def render_screenshot(structure, out_path, title=None, palette=None, views=None, width=1000, height=1000):
    """Renders `structure` as full-resolution shaded blocks -- every
    exposed block face, flat-colored (no lighting, no texture) -- and saves
    PNG(s). This is meant to show exactly what the structure would look
    like assembled in Minecraft, minus block textures, not an approximation
    of it: see `_build_exposed_face_mesh`.

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
    width, height - render resolution in pixels, before autocrop.
    """
    import open3d as o3d
    from matplotlib.colors import to_rgb
    from PIL import Image

    # Structure.data is (X, Y, Z) with Y (axis 1) vertical -- used directly
    # here (the camera and mesh both treat axis 1 as "up"), unlike the old
    # matplotlib-based renderer, which needed a Y/Z axis swap to satisfy
    # ax.voxels()'s hardcoded "3rd axis is vertical" assumption.
    data = structure.data
    mesh = _build_exposed_face_mesh(data, structure.atlas, palette or {})
    bbox = mesh.get_axis_aligned_bounding_box()
    center, radius = bbox.get_center(), np.linalg.norm(bbox.get_extent()) / 2
    y_max = int(np.nonzero(data)[1].max())

    out_path = Path(out_path)
    view_specs = views if views is not None else [{}]

    vis = o3d.visualization.Visualizer()
    vis.create_window(visible=False, width=width, height=height)
    opt = vis.get_render_option()
    opt.light_on = False  # flat block colors only -- no lighting model, no texture
    opt.background_color = np.array(to_rgb(BG_COLOR))
    vis.add_geometry(mesh)

    saved = []
    try:
        for view in view_specs:
            suffix = view.get("suffix", "")
            view_path = out_path.with_stem(out_path.stem + suffix) if suffix else out_path

            params, extrinsic, K = _make_camera(
                center, radius, view.get("elev", 11), view.get("azim", -55), width, height)
            ctr = vis.get_view_control()
            ctr.convert_from_pinhole_camera_parameters(params, allow_arbitrary=True)
            vis.poll_events()
            vis.update_renderer()
            vis.capture_screen_image(str(view_path), do_render=True)

            img = Image.open(view_path).convert("RGB")
            view_title = title
            if view.get("ruler"):
                height_text = _draw_ruler(
                    img, K, extrinsic, bbox.min_bound, bbox.max_bound, y_max, view.get("tick_step", 50))
                view_title = f"{title + ' - ' if title else ''}{height_text}"

            cropped = _autocrop(np.array(img))
            img = Image.fromarray(cropped)
            if view_title:
                img = _add_title_bar(img, view_title)
            img.save(view_path)
            print(f"Saved render to {view_path}")
            saved.append(view_path)
    finally:
        vis.destroy_window()

    return saved if views is not None else saved[0]
