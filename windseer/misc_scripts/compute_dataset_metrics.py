#!/usr/bin/env python3

from __future__ import print_function

import argparse
import json
import math

import torch
from tqdm import tqdm

import windseer.data as nn_data
import windseer.nn as nn
import windseer.utils as utils


DEFAULT_CHANNEL_ORDER = [
    'terrain', 'ux', 'uy', 'uz', 'turb', 'p', 'epsilon', 'nut'
    ]


def get_ordered_label_channels(label_channels):
    return [ch for ch in DEFAULT_CHANNEL_ORDER if ch in label_channels]


def parse_channels(requested_channels, available_channels):
    requested = [ch.lower() for ch in requested_channels]
    if len(requested) == 1 and requested[0] == 'all':
        return available_channels

    missing = [ch for ch in requested if ch not in available_channels]
    if len(missing) > 0:
        raise ValueError(
            'Requested channels not predicted by this model: {}. Available: {}'.format(
                missing, available_channels
                )
            )

    # keep user order while removing duplicates
    unique_requested = []
    for ch in requested:
        if ch not in unique_requested:
            unique_requested.append(ch)
    return unique_requested


def init_stats():
    return {
        'count': 0,
        'sum_true': 0.0,
        'sum_abs_true': 0.0,
        'sum_true_sq': 0.0,
        'sum_abs_err': 0.0,
        'sum_sq_err': 0.0,
        'min_true': float('inf'),
        'max_true': float('-inf'),
        }


def update_stats(stats, y_true, y_pred):
    y_true = y_true.double().reshape(-1)
    y_pred = y_pred.double().reshape(-1)

    diff = y_pred - y_true
    stats['count'] += y_true.numel()
    stats['sum_true'] += y_true.sum().item()
    stats['sum_abs_true'] += y_true.abs().sum().item()
    stats['sum_true_sq'] += torch.square(y_true).sum().item()
    stats['sum_abs_err'] += diff.abs().sum().item()
    stats['sum_sq_err'] += torch.square(diff).sum().item()

    y_true_min = y_true.min().item()
    y_true_max = y_true.max().item()
    if y_true_min < stats['min_true']:
        stats['min_true'] = y_true_min
    if y_true_max > stats['max_true']:
        stats['max_true'] = y_true_max


def compute_nrmse_denominator(stats, mode):
    count = float(stats['count'])
    if mode == 'rms':
        return math.sqrt(stats['sum_true_sq'] / count)
    if mode == 'mean_abs':
        return stats['sum_abs_true'] / count
    if mode == 'range':
        return stats['max_true'] - stats['min_true']
    if mode == 'std':
        mean_true = stats['sum_true'] / count
        variance = stats['sum_true_sq'] / count - mean_true * mean_true
        return math.sqrt(max(variance, 0.0))

    raise ValueError('Unknown nrmse mode: {}'.format(mode))


def finalize_stats(stats, nrmse_mode='rms', nrmse_eps=1e-12):
    if stats['count'] == 0:
        return {
            'mse': float('nan'),
            'rmse': float('nan'),
            'mae': float('nan'),
            'r2': float('nan'),
            'nrmse': float('nan'),
            'nrmse_denominator': float('nan'),
            }

    count = float(stats['count'])
    mse = stats['sum_sq_err'] / count
    rmse = math.sqrt(mse)
    mae = stats['sum_abs_err'] / count

    # Equivalent to sum((y_true - mean(y_true))^2) without storing all y_true.
    sst = stats['sum_true_sq'] - (stats['sum_true'] * stats['sum_true'] / count)
    if abs(sst) < 1e-20:
        r2 = 1.0 if abs(stats['sum_sq_err']) < 1e-20 else 0.0
    else:
        r2 = 1.0 - stats['sum_sq_err'] / sst

    nrmse_denominator = compute_nrmse_denominator(stats, nrmse_mode)
    if abs(nrmse_denominator) <= nrmse_eps:
        nrmse = float('nan')
    else:
        nrmse = rmse / nrmse_denominator

    return {
        'mse': mse,
        'rmse': rmse,
        'mae': mae,
        'r2': r2,
        'nrmse': nrmse,
        'nrmse_denominator': nrmse_denominator,
        }


def resolve_device(device_arg):
    if device_arg == 'cpu':
        return torch.device('cpu')
    if device_arg == 'cuda':
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA requested but no GPU is available.')
        return torch.device('cuda:0')
    return torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')


def main():
    parser = argparse.ArgumentParser(
        description='Compute aggregated MSE/RMSE/MAE/R2 over an HDF5 dataset.'
        )
    parser.add_argument(
        '-ds', '--dataset', required=True, help='Dataset filename (e.g. test_dataset.hdf5)'
        )
    parser.add_argument(
        '-model', dest='model_dir', required=True, help='Model directory path'
        )
    parser.add_argument(
        '-model_version', dest='model_version', default='latest', help='Model version'
        )
    parser.add_argument(
        '--device',
        default='auto',
        choices=['auto', 'cpu', 'cuda'],
        help='Inference device'
        )
    parser.add_argument(
        '--channels',
        nargs='+',
        default=['ux', 'uy', 'uz'],
        help='Channels to evaluate (default: ux uy uz). Use "all" for all predicted channels.'
        )
    parser.add_argument(
        '--max-samples',
        type=int,
        default=-1,
        help='Limit number of evaluated samples (default: -1 means all samples)'
        )
    parser.add_argument(
        '--save-json',
        type=str,
        default=None,
        help='Optional path to save results as JSON'
        )
    parser.add_argument(
        '--nrmse-mode',
        default='rms',
        choices=['rms', 'mean_abs', 'range', 'std'],
        help='Normalization used for NRMSE (default: rms)'
        )
    parser.add_argument(
        '--nrmse-eps',
        type=float,
        default=1e-12,
        help='Small threshold to avoid dividing by near-zero NRMSE denominator'
        )
    parser.add_argument(
        '--mask-terrain',
        dest='mask_terrain',
        action='store_true',
        help='Only evaluate cells where terrain > 0 (flow domain)'
        )
    parser.add_argument(
        '--no-mask-terrain',
        dest='mask_terrain',
        action='store_false',
        help='Evaluate all cells (including terrain/inside-ground cells)'
        )
    parser.set_defaults(mask_terrain=True)

    args = parser.parse_args()

    device = resolve_device(args.device)

    net, params = utils.load_model(
        args.model_dir, args.model_version, args.dataset, device, eval=True
        )
    testset = nn_data.HDF5Dataset(
        args.dataset, augmentation=False, return_grid_size=False, **params.Dataset_kwargs()
        )

    ordered_label_channels = get_ordered_label_channels(params.data['label_channels'])
    eval_channels = parse_channels(args.channels, ordered_label_channels)
    channel_indices = [ordered_label_channels.index(ch) for ch in eval_channels]

    total_samples = len(testset)
    if args.max_samples > 0:
        total_samples = min(total_samples, args.max_samples)

    overall_stats = init_stats()
    per_channel_stats = {ch: init_stats() for ch in eval_channels}

    evaluated_samples = 0
    skipped_samples = 0

    with torch.no_grad():
        for sample_index in tqdm(
            range(total_samples), total=total_samples, desc='Evaluating'
            ):
            data = testset[sample_index]
            input_tensor = data[0]
            label_tensor = data[1]

            scale = 1.0
            if params.data['autoscale']:
                scale = data[3].item()

            prediction, _, labels_rescaled = nn.get_prediction(
                input_tensor,
                label_tensor,
                scale,
                device,
                net,
                params,
                scale_input=False,
                verbose=False
                )

            pred_rescaled = prediction['pred'].squeeze(0).cpu()
            labels_rescaled = labels_rescaled.squeeze(0).cpu()
            terrain = input_tensor[0].cpu()

            if args.mask_terrain:
                mask = (terrain > 0.0)
            else:
                mask = torch.ones_like(terrain, dtype=torch.bool)

            if mask.sum().item() == 0:
                skipped_samples += 1
                continue

            selected_pred = pred_rescaled[channel_indices]
            selected_true = labels_rescaled[channel_indices]

            update_stats(overall_stats, selected_true[:, mask], selected_pred[:, mask])
            for ch, idx in zip(eval_channels, channel_indices):
                update_stats(
                    per_channel_stats[ch], labels_rescaled[idx][mask], pred_rescaled[idx][mask]
                    )

            evaluated_samples += 1

    overall_metrics = finalize_stats(
        overall_stats, nrmse_mode=args.nrmse_mode, nrmse_eps=args.nrmse_eps
        )
    per_channel_metrics = {
        ch: finalize_stats(
            per_channel_stats[ch], nrmse_mode=args.nrmse_mode, nrmse_eps=args.nrmse_eps
            ) for ch in eval_channels
        }

    print('\nDataset metrics')
    print('model: {}'.format(args.model_dir))
    print('model_version: {}'.format(args.model_version))
    print('dataset: {}'.format(args.dataset))
    print('device: {}'.format(device))
    print('channels: {}'.format(eval_channels))
    print('mask_terrain: {}'.format(args.mask_terrain))
    print('nrmse_mode: {}'.format(args.nrmse_mode))
    print('evaluated_samples: {}'.format(evaluated_samples))
    print('skipped_samples: {}'.format(skipped_samples))
    print('num_values: {}'.format(overall_stats['count']))

    print('\nOverall (all selected channels combined)')
    print('MSE : {:.8f}'.format(overall_metrics['mse']))
    print('RMSE: {:.8f}'.format(overall_metrics['rmse']))
    print(
        'NRMSE denominator ({}) : {:.8f}'.format(
            args.nrmse_mode, overall_metrics['nrmse_denominator']
            )
        )
    print('NRMSE ({}) : {:.8f}'.format(args.nrmse_mode, overall_metrics['nrmse']))
    print('MAE : {:.8f}'.format(overall_metrics['mae']))
    print('R2  : {:.8f}'.format(overall_metrics['r2']))

    print('\nPer-channel')
    for ch in eval_channels:
        ch_metrics = per_channel_metrics[ch]
        print(
            '{} -> MSE: {:.8f}, RMSE: {:.8f}, NRMSE_den({}): {:.8f}, NRMSE({}): {:.8f}, MAE: {:.8f}, R2: {:.8f}'.
            format(
                ch,
                ch_metrics['mse'],
                ch_metrics['rmse'],
                args.nrmse_mode,
                ch_metrics['nrmse_denominator'],
                args.nrmse_mode,
                ch_metrics['nrmse'],
                ch_metrics['mae'],
                ch_metrics['r2'],
                )
            )

    if args.save_json is not None:
        output = {
            'model': args.model_dir,
            'model_version': args.model_version,
            'dataset': args.dataset,
            'device': str(device),
            'channels': eval_channels,
            'mask_terrain': args.mask_terrain,
            'nrmse_mode': args.nrmse_mode,
            'nrmse_eps': args.nrmse_eps,
            'evaluated_samples': evaluated_samples,
            'skipped_samples': skipped_samples,
            'num_values': int(overall_stats['count']),
            'overall': overall_metrics,
            'per_channel': per_channel_metrics,
            }
        with open(args.save_json, 'w') as f:
            json.dump(output, f, indent=2)
        print('\nSaved metrics JSON to {}'.format(args.save_json))


if __name__ == '__main__':
    main()
