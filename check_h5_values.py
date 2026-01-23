import h5py
import numpy as np
import sys

def check_file(filename):
    print(f"--- Checking {filename} ---")
    with h5py.File(filename, 'r') as f:
        for key in list(f.keys())[:3]:  # Check first 3 samples
            print(f"Sample: {key}")
            terrain = f[key]['terrain']
            ds = f[key]['ds']
            print(f"  Terrain shape: {terrain.shape}")
            print(f"  ds values: {ds[...]}")
            # Calculate physical dimensions
            nz, ny, nx = terrain.shape
            dx, dy, dz = ds[...]
            print(f"  Physical dims: {nx*dx:.2f} x {ny*dy:.2f} x {nz*dz:.2f}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        for f in sys.argv[1:]:
            check_file(f)
    else:
        check_file('data/my_dataset.hdf5')
