import open3d as o3d
import numpy as np
from pathlib import Path
from collections import deque

def create_voxel_shell(voxels: np.ndarray) -> np.ndarray:
    if not voxels.ndim == 3:
        raise ValueError("Input must be a 3D numpy array.")
    
    shape = voxels.shape
    # Create a visited array for flood fill (initialize all as False)
    external_air = np.zeros(shape, dtype=bool)
    
    # Directions for 6-connectivity (x, y, z offsets)
    directions = [
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1)
    ]
    
    # Queue for BFS
    queue = deque()
    
    # Enqueue all boundary air voxels as starting points for flood fill
    for i in range(shape[0]):
        for j in range(shape[1]):
            for k in range(shape[2]):
                if (i == 0 or i == shape[0]-1 or
                    j == 0 or j == shape[1]-1 or
                    k == 0 or k == shape[2]-1) and not voxels[i, j, k]:
                    queue.append((i, j, k))
                    external_air[i, j, k] = True
    
    # Flood fill to mark all external air
    while queue:
        x, y, z = queue.popleft()
        for dx, dy, dz in directions:
            nx, ny, nz = x + dx, y + dy, z + dz
            if (0 <= nx < shape[0] and 0 <= ny < shape[1] and 0 <= nz < shape[2] and
                not voxels[nx, ny, nz] and not external_air[nx, ny, nz]):
                external_air[nx, ny, nz] = True
                queue.append((nx, ny, nz))
    
    # Create the shell: keep solid voxels adjacent to external air
    shell = np.zeros(shape, dtype=bool)
    for i in range(shape[0]):
        for j in range(shape[1]):
            for k in range(shape[2]):
                if voxels[i, j, k]:  # Original solid
                    # Check if adjacent to any external air
                    adjacent_to_external = False
                    for dx, dy, dz in directions:
                        nx, ny, nz = i + dx, j + dy, k + dz
                        if (0 <= nx < shape[0] and 0 <= ny < shape[1] and 0 <= nz < shape[2] and
                            external_air[nx, ny, nz]):
                            adjacent_to_external = True
                            break
                    if adjacent_to_external:
                        shell[i, j, k] = True
    
    return shell


def create_textured_cube(center, size, texture_path):
    cube = o3d.geometry.TriangleMesh.create_box(width=size, height=size, depth=size)
    cube.translate(np.array(center) - np.array([size / 2, size / 2, size / 2]))
    cube.compute_vertex_normals()
    cube.triangle_uvs = o3d.utility.Vector2dVector([
        [0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1],
        [0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1],
        [0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1],
        [0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1],
        [0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1],
        [0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1],
    ])
    try:
        texture_img = o3d.io.read_image(texture_path)
        cube.textures = [texture_img]
        cube.triangle_material_ids = o3d.utility.IntVector([0] * len(cube.triangles))
    except Exception as e:
        print(f"Error loading texture: {e}")
        cube.paint_uniform_color([1.0, 0.5, 0.5])
        return cube
    return cube

def visualize_shell(voxel_array, texture_path, flip_x, voxel_size=1.0):
    voxel_positions = np.argwhere(voxel_array)
    meshes = []
    for pos in voxel_positions:
        cube_center = pos * voxel_size
        cube = create_textured_cube(cube_center, voxel_size, texture_path)
        meshes.append(cube)
    combined_mesh = o3d.geometry.TriangleMesh()
    for mesh in meshes:
        combined_mesh += mesh
    coord_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=8.0, origin=[0, 0, 0])
    transform = np.array([
        [-1 if flip_x else 1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, -1, 0],
        [0, 0, 0, 1]
    ])
    combined_mesh.transform(transform)
    combined_mesh.compute_vertex_normals()
    coord_frame.transform(transform)
    coord_frame.compute_vertex_normals()
    vis = o3d.visualization.Visualizer()
    vis.create_window(window_name="Textured Voxel Grid")
    vis.add_geometry(combined_mesh)
    vis.add_geometry(coord_frame)
    render_option = vis.get_render_option()
    render_option.mesh_show_back_face = True
    render_option.background_color = np.array([44/255, 44/255, 46/255])
    render_option.light_on = True
    render_option.point_size = 1.0  # Minimize point artifacts
    render_option.line_width = 0.0  # Disable line drawing
    vis.run()
    vis.destroy_window()


def main(
    mesh_path:Path,
    # palette_path:Path,
    out_name:Path,
    rotate_x:int,
    rotate_y:int,
    rotate_z:int,
    flip_x:bool,
    flip_y:bool,
    flip_z:bool,
    voxel_scale:float,
    show:bool,
    visualize:bool,
    texture:Path|None,
    reference:str,
):
    mesh = o3d.io.read_triangle_mesh(mesh_path)

    if not mesh.has_vertex_normals():
        mesh.compute_vertex_normals()

    for i, amnt in enumerate([rotate_x, rotate_y, rotate_z]):
        if amnt != 0:
            rotation_matrix = o3d.geometry.get_rotation_matrix_from_axis_angle([np.deg2rad(amnt) if i==j else 0 for j in range(3)])
            mesh.rotate(rotation_matrix, center=(0, 0, 0))
    
    if reference == "right":
        flip_x = not flip_x
    for i, flip in enumerate([flip_x, flip_y, flip_z]):
        if flip:
            transform = np.array([
                [-1 if i==0 else 1, 0, 0, 0],
                [0, -1 if i==1 else 1, 0, 0],
                [0, 0, -1 if i==2 else 1, 0],
                [0, 0, 0, 1]
            ])
            mesh.transform(transform)

    voxel_grid = o3d.geometry.VoxelGrid.create_from_triangle_mesh(mesh, voxel_size=1.0/voxel_scale)
    
    voxels = voxel_grid.get_voxels()
    voxel_indices = np.array([v.grid_index for v in voxels])

    mins = np.array([np.min(voxel_indices[:,i]) for i in range(3)])
    maxs = np.array([np.max(voxel_indices[:,i]) for i in range(3)])
    shp = (maxs + 1 - mins).tolist()
    print(f"Shape: {shp}")

    full_voxels = np.zeros(shp, dtype=np.bool)
    for voxel in voxels:
        gi = voxel.grid_index
        full_voxels[gi[0], gi[1], gi[2]] = np.True_

    gapped_voxel = np.zeros([s + 2 for s in shp], dtype=np.bool)
    gapped_voxel[1:-1,1:-1,1:-1] = full_voxels
    shell_voxels = create_voxel_shell(gapped_voxel)[1:-1,1:-1,1:-1]

    np.save(mesh_path.parent / out_name, shell_voxels)

    if show:
        o3d.visualization.draw_geometries([voxel_grid])
    
    if visualize:
        assert texture is not None, f"Must pass in a texture path with --texture <path> if visualizing"
        assert texture.exists(), f"Texture not found, searched for '{texture}'"
        visualize_shell(shell_voxels, texture, reference=="right")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh_path", type=Path)
    # parser.add_argument("palette_path", type=Path)
    parser.add_argument("--out-name", type=str, default="shell")
    parser.add_argument("--rotate-x", type=int, default=0)
    parser.add_argument("--rotate-y", type=int, default=0)
    parser.add_argument("--rotate-z", type=int, default=0)
    parser.add_argument("--flip-x", action="store_true")
    parser.add_argument("--flip-y", action="store_true")
    parser.add_argument("--flip-z", action="store_true")
    parser.add_argument("--voxel-scale", type=float, default=100)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--visualize", action="store_true")
    parser.add_argument("--texture", type=Path)
    parser.add_argument("--reference", choices=["left", "right"], default="left")
    args = parser.parse_args()
    main(
        args.mesh_path,
        # args.palette_path,
        args.out_name,
        args.rotate_x,
        args.rotate_y,
        args.rotate_z,
        args.flip_x,
        args.flip_y,
        args.flip_z,
        args.voxel_scale,
        args.show,
        args.visualize,
        args.texture,
        args.reference,
    )
