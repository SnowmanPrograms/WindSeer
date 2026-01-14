import os
import matplotlib
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

def get_segments(events):
    if not events:
        return []
    segments = []
    current_segment = [events[0]]
    for i in range(1, len(events)):
        if events[i].step < events[i-1].step:
            segments.append(current_segment)
            current_segment = []
        current_segment.append(events[i])
    segments.append(current_segment)
    return segments

def plot_loss(log_dir):
    # Find all tfevents files in the directory
    event_files = [os.path.join(log_dir, f) for f in os.listdir(log_dir) if 'events.out.tfevents' in f]
    if not event_files:
        print(f"No event files found in {log_dir}")
        return

    # Sort by modification time to process them in order if needed, 
    # but EventAccumulator can handle multiple files if we point to the directory
    acc = EventAccumulator(log_dir)
    acc.Reload()

    # Get the tags available in the logs
    tags = acc.Tags()['scalars']
    print(f"Available scalar tags: {tags}")

    plt.figure(figsize=(10, 6))

    if 'Train/Loss' in tags:
        train_loss = acc.Scalars('Train/Loss')
        segments = get_segments(train_loss)
        for i, seg in enumerate(segments):
            steps = [s.step for s in seg]
            values = [s.value for s in seg]
            label = f'Train Loss (Run {i+1})' if len(segments) > 1 else 'Train Loss'
            plt.plot(steps, values, label=label, color='tab:blue', alpha=1.0 if i == len(segments)-1 else 0.5)

    if 'Val/Loss' in tags:
        val_loss = acc.Scalars('Val/Loss')
        segments = get_segments(val_loss)
        for i, seg in enumerate(segments):
            steps = [s.step for s in seg]
            values = [s.value for s in seg]
            label = f'Validation Loss (Run {i+1})' if len(segments) > 1 else 'Validation Loss'
            plt.plot(steps, values, label=label, color='tab:orange', alpha=1.0 if i == len(segments)-1 else 0.5)

    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.title('Learning Curve')
    plt.legend()
    plt.grid(True)
    
    output_file = 'learning_curve.png'
    plt.savefig(output_file)
    print(f"Plot saved to {output_file}")
    plt.show()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Plot loss from TensorBoard logs')
    parser.add_argument('--logdir', type=str, default='trained_models/test_model/learningcurve', help='Path to the learningcurve directory')
    args = parser.parse_args()
    
    plot_loss(args.logdir)
