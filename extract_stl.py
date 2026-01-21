import argparse
import h5py
import numpy as np
import sys
import os
from stl import mesh

# Add paths for project modules
sys.path.append(os.path.abspath("data_generation"))
from python_stl.read_grd import create_trimesh

def extract_stl(hdf5_path, output_filename, sample_name=None, sample_index=0):
    try:
        with h5py.File(hdf5_path, 'r') as f:
            keys = sorted(list(f.keys()))
            
            # Determine sample name
            if sample_name is None:
                if sample_index >= len(keys):
                    print(f"Error: Index {sample_index} out of range (max {len(keys)-1})")
                    return
                sample_name = keys[sample_index]
            
            if sample_name not in f:
                print(f"Error: Sample '{sample_name}' not found in {hdf5_path}")
                return

            print(f"Extracting sample: {sample_name} (index: {keys.index(sample_name)})")
            group = f[sample_name]
            
            if 'terrain' not in group:
                print("Error: 'terrain' field not found.")
                return

            terrain_mask = group['terrain'][...] # Shape (nz, ny, nx)
            
            if 'ds' in group:
                ds = group['ds'][...]
            else:
                print("Warning: 'ds' not found, assuming grid spacing of 1.0")
                ds = np.array([1.0, 1.0, 1.0])

            nz, ny, nx = terrain_mask.shape
            dx, dy, dz = ds[0], ds[1], ds[2]
            
            x_coords = np.arange(nx) * dx
            y_coords = np.arange(ny) * dy
            
            is_air = terrain_mask > 0
            surface_index = np.argmax(is_air, axis=0) # Shape (ny, nx)
            
            z_heights = surface_index.astype(float) * dz
            z_heights = z_heights.T 
            
            terrain_mesh = create_trimesh(x_coords, y_coords, z_heights, verbose=False)
            terrain_mesh.save(output_filename)
            print(f"Saved STL to {output_filename}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

def list_samples(hdf5_path):
    try:
        with h5py.File(hdf5_path, 'r') as f:
            keys = sorted(list(f.keys()))
            print(f"File {hdf5_path} contains {len(keys)} samples:")
            for i, k in enumerate(keys):
                print(f"  [{i}] {k}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract STL from WindSeer HDF5 dataset")
    parser.add_argument("hdf5_path", help="Path to the HDF5 file")
    parser.add_argument("output_stl", nargs='?', default=None, help="Path to save the output STL file (required unless --list is used)")
    parser.add_argument("-n", "--name", dest='sample_name', help="Name of the sample to extract")
    parser.add_argument("-idx", "--index", dest='sample_index', type=int, default=0, help="Index of the sample to extract (default: 0)")
    parser.add_argument('--list', action='store_true', help='List all sample names in the file and exit')
    
    args = parser.parse_args()
    
    if args.list:
        list_samples(args.hdf5_path)
    else:
        if not args.output_stl:
            parser.error("The argument output_stl is required when not using --list.")
        extract_stl(args.hdf5_path, args.output_stl, args.sample_name, args.sample_index)