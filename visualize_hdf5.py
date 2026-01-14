import argparse
import h5py
import torch
import numpy as np
import sys
import os

# Ensure windseer module is importable
sys.path.append(os.getcwd())

try:
    import windseer.plotting.plotting_mayavi as plotting_mayavi
except ImportError:
    print("Error: Could not import windseer.plotting.plotting_mayavi. Make sure you are in the project root.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Visualize WindSeer HDF5 datasets')
    parser.add_argument('-i', '--input', required=True, help='Path to HDF5 file')
    parser.add_argument('-idx', '--index', type=int, default=0, help='Sample index (default: 0)')
    parser.add_argument('-n', '--name', help='Sample name (overrides index if provided)')
    parser.add_argument('-m', '--mode', choices=['slice', 'quiver', 'streamlines'], default='slice', 
                        help='Visualization mode: slice (interactive), quiver (vector field), streamlines')
    parser.add_argument('-c', '--channels', nargs='+', default=['ux', 'uy', 'uz'], 
                        help='Channels to visualize (default: ux uy uz)')
    parser.add_argument('--list', action='store_true', help='List all sample names in the file and exit')

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File not found {args.input}")
        return

    try:
        with h5py.File(args.input, 'r') as h5_file:
            members = sorted(list(h5_file.keys()))
            
            if args.list:
                print(f"File {args.input} contains {len(members)} samples:")
                for m in members:
                    print(f"  - {m}")
                return

            if len(members) == 0:
                print("Error: HDF5 file is empty")
                return

            # Determine sample name
            if args.name:
                sample_name = args.name
            else:
                if args.index >= len(members):
                    print(f"Error: Index {args.index} out of range (max {len(members)-1})")
                    return
                sample_name = members[args.index]

            if sample_name not in h5_file:
                print(f"Error: Sample {sample_name} not found in file")
                return

            print(f"Loading sample: {sample_name}")
            sample = h5_file[sample_name]
            
            # Load terrain
            if 'terrain' not in sample:
                print("Error: 'terrain' channel not found in sample")
                return
            terrain = torch.from_numpy(sample['terrain'][...]).float()
            
            # Load requested channels
            data_list = []
            available_channels = []
            for c in args.channels:
                if c in sample:
                    # HDF5 shape is [Z, Y, X], plotting expects [C, Z, Y, X]
                    data_list.append(torch.from_numpy(sample[c][...]).float().unsqueeze(0))
                    available_channels.append(c)
                else:
                    print(f"Warning: Channel {c} not found, skipping")
            
            if not data_list:
                print("Error: No valid data channels found for visualization")
                return

            data = torch.cat(data_list, 0)

            # Mayavi plotting
            if args.mode == 'slice':
                print("Launching interactive slice viewer...")
                # mlab_plot_slice expects [C, X, Y, Z] for input_data internally if passed to image_plane_widget
                # Actually, plotting_mayavi.py L155 does: data_np = input_data.permute(0, 3, 2, 1).numpy()
                # Wait, looking at L155 in read_file output: input_data is already a numpy array there.
                # Let's re-verify the input to mlab_plot_slice in plotting_mayavi.py
                # It takes input_data and prediction_channels.
                # L171: self.data = input_data
                # L211: self.scalar = mlab.pipeline.scalar_field(self.data[0])
                # scalar_field on a 3D array [Z, Y, X] works fine.
                
                # In plotting_mayavi.py:
                # prediction_np = prediction.cpu().squeeze().permute(0, 3, 2, 1).numpy()
                # ui = mlab_plot_slice(..., prediction_np, ...)
                
                # So we should follow the same permutation: [C, Z, Y, X] -> [C, X, Y, Z]
                data_np = data.permute(0, 3, 2, 1).numpy()
                
                plotting_mayavi.mlab_plot_slice(
                    title=f"Sample: {sample_name}",
                    input_data=data_np,
                    terrain=terrain,
                    prediction_channels=available_channels,
                    blocking=True
                )
            elif args.mode == 'quiver':
                if data.shape[0] >= 3:
                    print("Launching quiver plot...")
                    plotting_mayavi.mlab_plot_prediction(
                        prediction=data[:3],
                        terrain=terrain,
                        prediction_channels=available_channels[:3],
                        blocking=True
                    )
                else:
                    print("Error: Quiver mode requires at least 3 channels (e.g., ux, uy, uz)")
            elif args.mode == 'streamlines':
                if data.shape[0] >= 3:
                    print("Launching streamlines plot...")
                    plotting_mayavi.mlab_plot_streamlines(
                        flow=data[:3],
                        terrain=terrain,
                        blocking=True
                    )
                else:
                    print("Error: Streamlines mode requires at least 3 channels (e.g., ux, uy, uz)")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
