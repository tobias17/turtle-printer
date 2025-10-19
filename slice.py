import numpy as np
from pathlib import Path

def main(shell_path:Path, out_name:str):
    shell_voxels = np.load(shell_path)

    chunks = []
    # for y in range(1):
    for y in range(shell_voxels.shape[1]):
        coords = []
        if not shell_voxels[:,y,:].any():
            continue
        for x in range(shell_voxels.shape[0]):
            if not shell_voxels[x,y,:].any():
                continue
            for z in range(shell_voxels.shape[2]):
                if shell_voxels[x,y,z]:
                    coords.append("{" + f"{x},{z}" + "}")
        chunks.append("    {" + ",".join(coords) + "}")
    data = "data = {\n" + ",\n".join(chunks) + "\n}"

    save_path = shell_path.parent / out_name
    with open(save_path, "w") as f:
        f.write(data)
    print(f"Saved data to {save_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("shell_path", type=Path)
    parser.add_argument("--out-name", type=str, default="data.txt")
    args = parser.parse_args()
    main(args.shell_path, args.out_name)
