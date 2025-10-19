import open3d as o3d
import numpy as np
from pathlib import Path


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

    neighbors = np.array([
        [1, 0, 0], [-1, 0, 0],
        [0, 1, 0], [0, -1, 0],
        [0, 0, 1], [0, 0, -1],
    ])

    full_voxels = np.zeros(shp, dtype=np.bool)
    for voxel in voxels:
        gi = voxel.grid_index
        full_voxels[gi[0], gi[1], gi[2]] = np.True_
    shell_voxels = np.zeros_like(full_voxels, np.bool)
    for voxel in voxels:
        gi = voxel.grid_index
        if not any(gi[i] - 1 < 0 or gi[i] + 1 >= full_voxels.shape[i] for i in range(3)):
            for n in range(6):
                idx = gi + neighbors[n]
                if not full_voxels[idx[0], idx[1], idx[2]]:
                    break
            else:
                continue
        shell_voxels[gi[0], gi[1], gi[2]] = np.True_

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
