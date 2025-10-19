import numpy as np
from pathlib import Path
import cv2

def tsp_solver(points):
    # Handle empty or single-point cases
    if not points:
        return []
    n = len(points)
    if n < 2:
        return points + [points[0]] if n > 0 else []

    # Convert points to numpy array and validate
    try:
        points = np.array(points, dtype=float)
    except Exception as e:
        raise ValueError(f"Failed to convert points to numpy array: {e}")
    
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError(f"Points must be a list of (x, y) coordinates with shape (n, 2), got shape {points.shape}")
    
    if np.any(~np.isfinite(points)):
        raise ValueError("Points contain non-finite values (NaN or Inf)")

    # Compute Manhattan distance matrix with +1 cost for 90-degree turns
    try:
        # Corrected broadcasting for dx and dy
        x = points[:, 0]  # Shape: (n,)
        y = points[:, 1]  # Shape: (n,)
        dx = np.abs(x[:, np.newaxis] - x[np.newaxis, :])  # Shape: (n, n)
        dy = np.abs(y[:, np.newaxis] - y[np.newaxis, :])  # Shape: (n, n)
        dist = dx + dy + np.logical_and(dx > 0, dy > 0).astype(float)  # Manhattan + turn cost
    except Exception as e:
        raise ValueError(f"Failed to compute distance matrix: {e}")

    # Verify distance matrix shape
    if dist.shape != (n, n):
        raise ValueError(f"Distance matrix has incorrect shape {dist.shape}, expected ({n}, {n})")
    if np.any(~np.isfinite(dist)):
        raise ValueError("Distance matrix contains non-finite values")

    # Nearest Neighbor heuristic for initial tour
    tour = [0]
    visited = np.zeros(n, dtype=bool)
    visited[0] = True
    current = 0

    for _ in range(1, n):
        # Find nearest unvisited node
        candidates = dist[current].copy()  # Shape: (n,)
        if candidates.shape != (n,):
            raise ValueError(f"Candidates has incorrect shape {candidates.shape}, expected ({n},)")
        if visited.shape != (n,):
            raise ValueError(f"Visited has incorrect shape {visited.shape}, expected ({n},)")
        
        candidates[visited] = np.inf  # Mask visited nodes
        next_node = np.argmin(candidates)
        if np.isinf(candidates[next_node]):
            raise ValueError("No valid unvisited nodes remain; graph may be disconnected")
        tour.append(next_node)
        visited[next_node] = True
        current = next_node

    improvement = True
    while improvement:
        improvement = False
        for i in range(1, n - 1):
            for j in range(i + 2, n):
                # Calculate change in distance for 2-opt swap
                old_dist = dist[tour[i - 1], tour[i]] + dist[tour[j], tour[(j + 1) % n]]
                new_dist = dist[tour[i - 1], tour[j]] + dist[tour[i], tour[(j + 1) % n]]
                if new_dist < old_dist - 1e-9:  # Small epsilon for floating-point precision
                    # Reverse the segment from i to j
                    tour[i:j + 1] = tour[i:j + 1][::-1]
                    improvement = True

    # Convert tour indices to list of (x, y) coordinates
    result = [points[i].astype(int).tolist() for i in tour]
    return result

def plot_coords(points, shp_x, shp_y):

    SCALE = 32
    img = np.zeros(((shp_x+1)*SCALE, (shp_y+1)*SCALE, 3))

    for i in range(len(points) - 1):
        y1, x1 = points[i]
        y2, x2 = points[i + 1]
        cv2.circle(img, (x1*SCALE+SCALE, y1*SCALE+SCALE), int(SCALE/2), (255,0,0), int(SCALE/8))
        cv2.circle(img, (x2*SCALE+SCALE, y2*SCALE+SCALE), int(SCALE/2), (255,0,0), int(SCALE/8))
        cv2.line(img, (x1*SCALE+SCALE, y1*SCALE+SCALE), (x2*SCALE+SCALE, y2*SCALE+SCALE), (0,0,255), int(SCALE/8))
    cv2.imshow("img", img)
    cv2.waitKey()

def get_chunk_indices(chunk_sizes, num_slices):
    if not chunk_sizes or num_slices <= 0 or num_slices > len(chunk_sizes):
        return []
    
    total_sum = sum(chunk_sizes)
    target_size = total_sum / num_slices
    result = [0]
    current_sum = 0
    current_slice = 1
    
    for i in range(len(chunk_sizes)):
        current_sum += chunk_sizes[i]
        
        # If we've reached or exceeded the target size and haven't used all slices
        if current_sum >= target_size * current_slice and current_slice < num_slices:
            # Start the next slice at the next index
            result.append(i + 1)
            current_slice += 1
    
    # Ensure we have exactly num_slices indices
    while len(result) < num_slices:
        result.append(len(chunk_sizes))
        
    return result

def slice_voxels(voxels:np.ndarray, x_offset:int, debug:bool, indent=" "*8):
    chunks = []
    for y in range(voxels.shape[1]):
        coords = []
        if not voxels[:,y,:].any():
            continue
        for x in range(voxels.shape[0]):
            if not voxels[x,y,:].any():
                continue
            for z in range(voxels.shape[2]):
                if voxels[x,y,z]:
                    coords.append((x+x_offset,z))
        
        tsp_coords = tsp_solver(coords)
        if debug:
            plot_coords(coords, voxels.shape[0], voxels.shape[2])
            plot_coords(tsp_coords, voxels.shape[0], voxels.shape[2])

        str_coords = ["{" + f"{x},{z}" + "}" for x,z in tsp_coords]
        chunks.append(indent + "{" + ",".join(str_coords) + "}")
    return ",\n".join(chunks)

def main(shell_path:Path, out_name:str, turtles:int, debug:bool):
    shell_voxels = np.load(shell_path)

    shell_to_int = shell_voxels.astype(np.int32)
    x_slice_sizes = [int(np.sum(shell_to_int[x,:,:])) for x in range(shell_to_int.shape[0])]
    x_turtle_starts = get_chunk_indices(x_slice_sizes, num_slices=turtles)
    x_turtle_starts.append(int(shell_to_int.shape[0]))
    # assert False, x_turtle_starts

    entries = []
    for i in range(turtles):
        entry = slice_voxels(shell_voxels[x_turtle_starts[i]:x_turtle_starts[i+1]], x_turtle_starts[i], debug)
        entries.append("    {\n" + entry + "\n    }")

    data = "local all_data = {\n" + ",\n".join(entries) + "\n}"

    save_path = shell_path.parent / out_name
    with open(save_path, "w") as f:
        f.write(data)
    print(f"Saved data to {save_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("shell_path", type=Path)
    parser.add_argument("--turtles", type=int, default=8)
    parser.add_argument("--out-name", type=str, default="data.txt")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    main(args.shell_path, args.out_name, args.turtles, args.debug)
