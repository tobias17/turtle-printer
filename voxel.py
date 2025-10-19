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


def main(
    mesh_path:Path,
    # palette_path:Path,
    out_name:Path,
    rotate_x:int,
    rotate_y:int,
    rotate_z:int,
    voxel_scale:float,
    show:bool,
):
    mesh = o3d.io.read_triangle_mesh(mesh_path)

    if not mesh.has_vertex_normals():
        mesh.compute_vertex_normals()

    for i, amnt in enumerate([rotate_x, rotate_y, rotate_z]):
        if amnt != 0:
            rotation_matrix = o3d.geometry.get_rotation_matrix_from_axis_angle([np.deg2rad(amnt) if i==j else 0 for j in range(3)])
            mesh.rotate(rotation_matrix, center=(0, 0, 0))

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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh_path", type=Path)
    # parser.add_argument("palette_path", type=Path)
    parser.add_argument("--out-name", type=str, default="shell")
    parser.add_argument("--rotate-x", type=int, default=0)
    parser.add_argument("--rotate-y", type=int, default=0)
    parser.add_argument("--rotate-z", type=int, default=0)
    parser.add_argument("--voxel-scale", type=float, default=200)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    main(
        args.mesh_path,
        # args.palette_path,
        args.out_name,
        args.rotate_x,
        args.rotate_y,
        args.rotate_z,
        args.voxel_scale,
        args.show,
    )
