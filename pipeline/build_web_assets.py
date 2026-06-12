"""Build web assets for the selected demo videos.

Produces, for each video id in work/selected.json:
  - videos/{id}.mp4            (540p H.264 + AAC, faststart)
  - videos/thumbs/{id}.jpg     (640px-wide poster)
  - data/v/{id}.json           (time series for the interactive player)
and the manifest data/videos.json.

Usage: python pipeline/build_web_assets.py [--skip-encode]
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

import h5py
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.stats import kendalltau, spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
WORK = os.path.join(HERE, 'work')
CODE = os.path.join(ROOT, 'TripleSumm')
MOSU = '/data/dataset/VideoSummarization/mosu'

sys.path.insert(0, CODE)
from utils.generate_summary import generate_summary  # noqa: E402

MAX_MB = 30


def segments_of(binary):
    idx = np.where(np.asarray(binary) > 0)[0]
    if len(idx) == 0:
        return []
    breaks = np.where(np.diff(idx) > 1)[0]
    starts = np.concatenate([[idx[0]], idx[breaks + 1]])
    ends = np.concatenate([idx[breaks] + 1, [idx[-1] + 1]])
    return [[int(s), int(e)] for s, e in zip(starts, ends)]


def mean_attention(attn_group, T):
    layers = [attn_group[k][...] for k in attn_group]
    a = np.mean(np.stack(layers), axis=(0, 2))
    assert a.shape[0] >= T, f'attn shorter than gt: {a.shape[0]} < {T}'
    a = a[:T]
    return a / a.sum(axis=1, keepdims=True)


def minmax(x):
    lo, hi = float(x.min()), float(x.max())
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


def display_score(x, sigma=2.0):
    """Light smoothing for display only — metrics stay on raw scores."""
    return minmax(gaussian_filter1d(minmax(np.asarray(x, dtype=float)), sigma))


def rounded(arr, nd=3):
    return [round(float(v), nd) for v in arr]


def fetch_title(youtube_id):
    url = f'https://www.youtube.com/oembed?url=https://youtu.be/{youtube_id}&format=json'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)['title']
    except Exception as e:
        print(f'  oEmbed failed for {youtube_id}: {e}')
        return None


def encode_video(src, dst, crf=26, maxrate='1200k', bufsize='2400k'):
    subprocess.run([
        'ffmpeg', '-y', '-v', 'error', '-i', src,
        '-vf', 'scale=-2:540', '-c:v', 'libx264', '-profile:v', 'main', '-level', '4.0',
        '-preset', 'slow', '-crf', str(crf), '-maxrate', maxrate, '-bufsize', bufsize,
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-ac', '2',
        '-movflags', '+faststart', dst], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-encode', action='store_true')
    args = ap.parse_args()

    selected = json.load(open(os.path.join(WORK, 'selected.json')))
    cands = {c['video_id']: c for c in json.load(open(os.path.join(WORK, 'candidates.json')))}
    pred_h5 = h5py.File(os.path.join(WORK, 'test_pred_scores.h5'), 'r')
    attn_h5 = h5py.File(os.path.join(CODE, 'checkpoints', 'test_attn_weights.h5'), 'r')
    gt_h5 = h5py.File(os.path.join(MOSU, 'mosu_gt.h5'), 'r')

    os.makedirs(os.path.join(ROOT, 'data', 'v'), exist_ok=True)
    os.makedirs(os.path.join(ROOT, 'videos', 'thumbs'), exist_ok=True)

    titles_path = os.path.join(WORK, 'titles.json')
    titles = json.load(open(titles_path)) if os.path.exists(titles_path) else {}
    titles_todo = []
    manifest = []

    for vid in selected:
        c = cands[vid]
        yt = c['youtube_id']
        src = os.path.join(MOSU, 'rawdata', 'video', yt + '.mp4')
        dst = os.path.join(ROOT, 'videos', vid + '.mp4')
        thumb = os.path.join(ROOT, 'videos', 'thumbs', vid + '.jpg')

        gt_score = gt_h5[vid]['gt_score'][...]
        cps = gt_h5[vid]['change_points'][...]
        pred = pred_h5[vid][...]
        T = len(gt_score)
        assert len(pred) == T

        ktau = float(kendalltau(pred, gt_score)[0])
        srho = float(spearmanr(pred, gt_score)[0])

        attn = mean_attention(attn_h5[vid], T)
        gt_segs = segments_of(gt_h5[vid]['gt_summary'][...])
        # change_points' last end index == T, so generate_summary returns T+1 frames
        pred_sum = generate_summary([pred], [cps], [T], [np.arange(T)])[0][:T]
        pred_segs = segments_of(pred_sum)

        # title
        if vid not in titles:
            t = fetch_title(yt)
            if t is None:
                titles_todo.append({'video_id': vid, 'youtube_id': yt})
                t = f'MoSu video {vid}'
            titles[vid] = t

        vjson = {
            'id': vid,
            'youtube_id': yt,
            'title': titles[vid],
            'duration': T,
            'metrics': {'ktau': round(ktau, 3), 'srho': round(srho, 3)},
            'gt_score': rounded(display_score(gt_score)),
            'pred_score': rounded(display_score(pred)),
            'gt_segments': gt_segs,
            'pred_segments': pred_segs,
            'attn': [rounded(row) for row in attn],
        }
        # invariants
        assert len(vjson['gt_score']) == len(vjson['pred_score']) == len(vjson['attn']) == T
        assert all(abs(sum(r) - 1.0) < 2e-2 for r in vjson['attn'])
        assert all(0 <= s < e <= T for s, e in gt_segs + pred_segs)
        with open(os.path.join(ROOT, 'data', 'v', vid + '.json'), 'w') as f:
            json.dump(vjson, f, separators=(',', ':'))

        if not args.skip_encode or not os.path.exists(dst):
            encode_video(src, dst)
            mb = os.path.getsize(dst) / 1e6
            if mb > MAX_MB:
                print(f'  {vid}: {mb:.1f} MB > {MAX_MB} MB, re-encoding at crf 28')
                encode_video(src, dst, crf=28, maxrate='900k', bufsize='1800k')
        if not os.path.exists(thumb):
            subprocess.run([
                'ffmpeg', '-y', '-v', 'error', '-ss', f'{0.25 * T:.1f}', '-i', dst,
                '-vf', 'scale=640:-2', '-frames:v', '1', '-q:v', '4', thumb], check=True)

        mb = os.path.getsize(dst) / 1e6
        print(f'{vid}: T={T}s mp4={mb:.1f}MB ktau={ktau:.3f} srho={srho:.3f} '
              f'segs gt={len(gt_segs)} pred={len(pred_segs)} title={titles[vid][:50]!r}')

        manifest.append({
            'id': vid, 'title': titles[vid], 'duration': T,
            'cluster': c['cluster_id'],
            'ktau': round(ktau, 3), 'srho': round(srho, 3),
        })

    json.dump(titles, open(titles_path, 'w'), indent=2)
    if titles_todo:
        json.dump(titles_todo, open(os.path.join(WORK, 'titles_todo.json'), 'w'), indent=2)
        print(f'NOTE: {len(titles_todo)} titles missing -> work/titles_todo.json')

    with open(os.path.join(ROOT, 'data', 'videos.json'), 'w') as f:
        json.dump({'modalities': ['visual', 'text', 'audio'], 'videos': manifest}, f, indent=1)
    total = sum(os.path.getsize(os.path.join(ROOT, 'videos', v + '.mp4')) for v in selected) / 1e6
    print(f'manifest: {len(manifest)} videos, total mp4 {total:.0f} MB')


if __name__ == '__main__':
    main()
