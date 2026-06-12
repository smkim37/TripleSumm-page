"""Dump per-video predicted importance scores for the MoSu test split.

Standalone inference (no changes to the research repo). Run from the
TripleSumm/ code directory:

    cd TripleSumm && python ../pipeline/dump_pred_scores.py
"""
import os
import sys
import json

import h5py
import numpy as np
import torch

CODE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'TripleSumm'))
WORK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'work'))
DATA_DIR = '/data/dataset/VideoSummarization'

sys.path.insert(0, CODE_DIR)
os.chdir(CODE_DIR)

from dataset import Dataset, CollateFn          # noqa: E402
from models import build_model                  # noqa: E402
from utils.config import get_config             # noqa: E402
from utils.compute_metrics import evaluate_summary  # noqa: E402


def main():
    sys.argv = [
        'main.py',
        '--exp_name', 'dump-pred',
        '--mode', 'test',
        '--dataset', 'mosu',
        '--model', 'triplesumm',
        '--data_dir', DATA_DIR,
        '--model_ckpt', os.path.join(CODE_DIR, 'checkpoints', 'best_model_ckpt_mosu.pth'),
    ]
    cfg = get_config()
    cfg.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'device: {cfg.device}')

    dataset = Dataset(cfg, split='test')
    loader = torch.utils.data.DataLoader(
        dataset, batch_size=cfg.batch_size, shuffle=False,
        num_workers=cfg.num_workers, collate_fn=CollateFn(), pin_memory=True)

    model = build_model(cfg).to(cfg.device)
    state = torch.load(cfg.model_ckpt, map_location=cfg.device, weights_only=True)
    model.load_state_dict(state)
    model.eval()

    os.makedirs(WORK_DIR, exist_ok=True)
    out_path = os.path.join(WORK_DIR, 'test_pred_scores.h5')

    n_done = 0
    sample_check = {}
    with h5py.File(out_path, 'w') as out, torch.no_grad():
        for batch in loader:
            visual = batch['visual_feat'].to(cfg.device, non_blocking=True)
            text = batch['text_feat'].to(cfg.device, non_blocking=True)
            audio = batch['audio_feat'].to(cfg.device, non_blocking=True)
            mask = batch['mask'].to(cfg.device, non_blocking=True)

            output, _ = model(visual, text, audio, mask=mask)
            if output.dim() == 3:
                output = output.squeeze(-1)
            output = output.detach().cpu().numpy()
            mask_np = mask.detach().cpu().numpy()

            for i, video_id in enumerate(batch['video_id']):
                T = int(np.where(mask_np[i])[0][-1]) + 1
                pred = output[i, :T].astype(np.float32)
                out.create_dataset(video_id, data=pred)
                if len(sample_check) < 50:
                    gt = batch['gt_score'][i, :T].numpy()
                    sample_check[video_id] = (pred.copy(), gt.copy())
                n_done += 1
            if n_done % 1280 < cfg.batch_size:
                print(f'  {n_done} videos done')

    print(f'wrote {n_done} videos -> {out_path}')

    # sanity check against the published per-video scores
    ref = json.load(open(os.path.join(CODE_DIR, 'checkpoints', 'test_video_scores.json')))
    max_diff = 0.0
    for vid, (pred, gt) in sample_check.items():
        ktau, srho = evaluate_summary([pred], [gt], np.ones((1, len(pred)), dtype=bool), per_sample=True)
        diff = abs((ktau[0] + srho[0]) - ref[vid])
        max_diff = max(max_diff, diff)
    print(f'sanity check on {len(sample_check)} videos: max |ktau+srho - ref| = {max_diff:.2e}')
    # rank metrics flip on near-ties under float nondeterminism; ~1e-3 is reproduction
    assert max_diff < 5e-3, 'pred scores do not reproduce published per-video metrics'


if __name__ == '__main__':
    main()
