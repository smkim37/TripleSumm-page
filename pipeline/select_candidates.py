"""Select demo candidate videos from the MoSu test split.

Filter funnel:
  1. raw mp4 exists for the youtube_id
  2. duration in [120, 300] s
  3. ktau+srho high (cut tuned to keep a pool of >= 300)
  4. gt_score is multi-peaked: n_peaks >= 4 (backfill from 3 if short)
  5. gt_summary dispersion: n_seg >= 3, position spread >= 0.18, all thirds covered
  6. cluster round-robin (<= 5 per cluster) -> ~45 candidates

Usage: python pipeline/select_candidates.py
"""
import csv
import json
import os

import h5py
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

MOSU = '/data/dataset/VideoSummarization/mosu'
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
SCORES_JSON = os.path.join(HERE, '..', 'TripleSumm', 'checkpoints', 'test_video_scores.json')

N_CANDIDATES = 45
MAX_PER_CLUSTER = 5


def peak_count(g, sigma=3, prom=0.15, dist=15):
    """Prominent local maxima in the (smoothed, normalized) gt score curve."""
    g = np.asarray(g, dtype=float)
    rng = g.max() - g.min()
    if rng <= 0:
        return 0
    s = gaussian_filter1d((g - g.min()) / rng, sigma)
    pk, _ = find_peaks(s, prominence=prom, distance=dist)
    return len(pk)


def segments_of(binary):
    """Run-length [start, end) segments where binary == 1."""
    idx = np.where(binary > 0)[0]
    if len(idx) == 0:
        return []
    breaks = np.where(np.diff(idx) > 1)[0]
    starts = np.concatenate([[idx[0]], idx[breaks + 1]])
    ends = np.concatenate([idx[breaks] + 1, [idx[-1] + 1]])
    return list(zip(starts.tolist(), ends.tolist()))


def main():
    scores = json.load(open(SCORES_JSON))
    meta = {}
    with open(os.path.join(MOSU, 'mosu_metadata.csv'), encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            meta[row['video_id']] = row

    test_ids = list(scores.keys())
    print(f'test videos: {len(test_ids)}')

    # 1. raw mp4 exists
    have_mp4 = [v for v in test_ids
                if v in meta and os.path.exists(os.path.join(MOSU, 'rawdata', 'video', meta[v]['youtube_id'] + '.mp4'))]
    print(f'has raw mp4: {len(have_mp4)}')

    # 2. duration filter
    pool = [v for v in have_mp4 if 120 <= int(meta[v]['duration']) <= 300]
    print(f'duration 120-300s: {len(pool)}')

    # 3. metric cut: keep top by ktau+srho such that pool >= 300 after dispersion;
    #    start from a generous top-N and report the implied threshold
    pool.sort(key=lambda v: -scores[v])
    top = pool[:1500]
    print(f'metric top-1500 cut: ktau+srho >= {scores[top[-1]]:.3f} (best {scores[top[0]]:.3f})')

    # 4+5. multi-peak gt_score and dispersion of gt_summary
    rows = []
    with h5py.File(os.path.join(MOSU, 'mosu_gt.h5'), 'r') as gt:
        for v in top:
            n_peaks = peak_count(gt[v]['gt_score'][...])
            if n_peaks < 3:
                continue
            gs = gt[v]['gt_summary'][...]
            T = len(gs)
            segs = segments_of(gs)
            n_seg = len(segs)
            sel = np.where(gs > 0)[0]
            if len(sel) == 0:
                continue
            p = sel / T
            spread = float(p.std())
            coverage3 = len({min(int(x * 3), 2) for x in p})
            if n_seg >= 3 and spread >= 0.18 and coverage3 == 3:
                rows.append({
                    'video_id': v,
                    'youtube_id': meta[v]['youtube_id'],
                    'duration': int(meta[v]['duration']),
                    'cluster_id': int(meta[v]['cluster_id']),
                    'ktau_srho': round(scores[v], 4),
                    'n_peaks': n_peaks,
                    'n_seg': n_seg,
                    'spread': round(spread, 3),
                })
    n4 = sum(1 for r in rows if r['n_peaks'] >= 4)
    print(f'multi-peak + dispersion pass: {len(rows)} (n_peaks>=4: {n4})')

    # 6. cluster round-robin over n_peaks>=4 first, backfill from n_peaks==3
    selected = []
    for tier in (4, 3):
        pool_t = [r for r in rows if (r['n_peaks'] >= 4) == (tier == 4)]
        by_cluster = {}
        for r in sorted(pool_t, key=lambda r: -r['ktau_srho']):
            by_cluster.setdefault(r['cluster_id'], []).append(r)
        if tier == 4:
            print('clusters (n_peaks>=4):', {c: len(v) for c, v in sorted(by_cluster.items())})
        for rank in range(MAX_PER_CLUSTER):
            for c in sorted(by_cluster, key=lambda c: -by_cluster[c][0]['ktau_srho']):
                if rank < len(by_cluster[c]) and len(selected) < N_CANDIDATES:
                    selected.append(by_cluster[c][rank])
            if len(selected) >= N_CANDIDATES:
                break
        if len(selected) >= N_CANDIDATES:
            break

    selected.sort(key=lambda r: -r['ktau_srho'])
    os.makedirs(WORK, exist_ok=True)
    out = os.path.join(WORK, 'candidates.json')
    json.dump(selected, open(out, 'w'), indent=2)
    print(f'wrote {len(selected)} candidates -> {out}')
    for r in selected[:10]:
        print(' ', r)


if __name__ == '__main__':
    main()
