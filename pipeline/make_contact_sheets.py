"""Render one review sheet per candidate: frame strip + score/summary/attention plots.

Usage:
    LD_LIBRARY_PATH=$CONDA_PREFIX/lib python pipeline/make_contact_sheets.py
"""
import json
import os
import subprocess
import sys
import tempfile

import h5py
import numpy as np
from scipy.ndimage import gaussian_filter1d
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
CODE = os.path.join(HERE, '..', 'TripleSumm')
MOSU = '/data/dataset/VideoSummarization/mosu'

sys.path.insert(0, CODE)
from utils.generate_summary import generate_summary  # noqa: E402

MOD_COLORS = ['#3b82f6', '#10b981', '#f59e0b']  # visual, text, audio
MOD_NAMES = ['visual', 'text', 'audio']
N_FRAMES = 8


def mean_attention(attn_group, T):
    """Average layers and heads -> (T, 3), truncated to gt length, rows renormalized."""
    layers = [attn_group[k][...] for k in attn_group]
    a = np.mean(np.stack(layers), axis=(0, 2))  # (T_pad, 3)
    assert a.shape[0] >= T, f'attn shorter than gt: {a.shape[0]} < {T}'
    a = a[:T]
    return a / a.sum(axis=1, keepdims=True)


def grab_frames(mp4, duration, n):
    """n evenly spaced frames as RGB arrays."""
    frames = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            t = duration * (i + 0.5) / n
            out = os.path.join(td, f'{i}.jpg')
            subprocess.run(
                ['ffmpeg', '-v', 'error', '-ss', f'{t:.2f}', '-i', mp4,
                 '-vf', 'scale=320:-2', '-frames:v', '1', '-q:v', '4', out],
                check=True)
            frames.append(mpimg.imread(out))
    return frames


def minmax(x):
    lo, hi = x.min(), x.max()
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


def display_score(x, sigma=2.0):
    """Light smoothing for display only (matches build_web_assets.py)."""
    return minmax(gaussian_filter1d(minmax(np.asarray(x, dtype=float)), sigma))


def main():
    cands = json.load(open(os.path.join(WORK, 'candidates.json')))
    pred_h5 = h5py.File(os.path.join(WORK, 'test_pred_scores.h5'), 'r')
    attn_h5 = h5py.File(os.path.join(CODE, 'checkpoints', 'test_attn_weights.h5'), 'r')
    gt_h5 = h5py.File(os.path.join(MOSU, 'mosu_gt.h5'), 'r')
    sheets = os.path.join(WORK, 'sheets')
    os.makedirs(sheets, exist_ok=True)

    for c in cands:
        vid = c['video_id']
        out_png = os.path.join(sheets, f"{c['ktau_srho']:.3f}_{vid}.png")
        if os.path.exists(out_png):
            continue
        mp4 = os.path.join(MOSU, 'rawdata', 'video', c['youtube_id'] + '.mp4')
        gt_score = gt_h5[vid]['gt_score'][...]
        gt_sum = gt_h5[vid]['gt_summary'][...]
        cps = gt_h5[vid]['change_points'][...]
        pred = pred_h5[vid][...]
        T = len(gt_score)
        attn = mean_attention(attn_h5[vid], T)
        # change_points' last end index == T, so generate_summary returns T+1 frames
        pred_sum = generate_summary([pred], [cps], [T], [np.arange(T)])[0][:T]

        frames = grab_frames(mp4, c['duration'], N_FRAMES)
        t = np.arange(T)

        fig = plt.figure(figsize=(16, 9))
        gs = fig.add_gridspec(4, N_FRAMES, height_ratios=[2.2, 1.2, 0.7, 1.2], hspace=0.35)

        for i, fr in enumerate(frames):
            ax = fig.add_subplot(gs[0, i])
            ax.imshow(fr)
            ax.set_title(f'{int(c["duration"] * (i + 0.5) / N_FRAMES)}s', fontsize=8)
            ax.axis('off')

        ax1 = fig.add_subplot(gs[1, :])
        ax1.plot(t, display_score(gt_score), color='#9ca3af', lw=1.2, label='GT score')
        ax1.plot(t, display_score(pred), color='#e11d48', lw=1.2, label='Pred score')
        ax1.set_xlim(0, T); ax1.set_yticks([]); ax1.legend(loc='upper right', fontsize=8)

        ax2 = fig.add_subplot(gs[2, :])
        ax2.fill_between(t, 0, gt_sum, step='post', color='#9ca3af', alpha=0.9)
        ax2.fill_between(t, -pred_sum, 0, step='post', color='#e11d48', alpha=0.8)
        ax2.set_xlim(0, T); ax2.set_yticks([-0.5, 0.5])
        ax2.set_yticklabels(['Pred summary', 'GT summary'], fontsize=8)

        ax3 = fig.add_subplot(gs[3, :])
        ax3.stackplot(t, attn.T, colors=MOD_COLORS, labels=MOD_NAMES, alpha=0.85)
        ax3.set_xlim(0, T); ax3.set_ylim(0, 1)
        ax3.legend(loc='upper right', fontsize=8, ncol=3)
        ax3.set_xlabel('time (s)')

        fig.suptitle(
            f"{vid}  ({c['youtube_id']})  dur={c['duration']}s  cluster={c['cluster_id']}  "
            f"ktau+srho={c['ktau_srho']:.3f}  n_seg={c['n_seg']}  spread={c['spread']}",
            fontsize=11)
        fig.savefig(out_png, dpi=80, bbox_inches='tight')
        plt.close(fig)
        print('sheet:', os.path.basename(out_png))


if __name__ == '__main__':
    main()
