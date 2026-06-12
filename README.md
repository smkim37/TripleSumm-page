# TripleSumm — Project Page & Interactive Demo (ICLR 2026)

Static project page for **TripleSumm: Adaptive Triple-Modality Fusion for Video Summarization**,
with an interactive demo of 20 curated MoSu test-split videos: synced GT/predicted importance,
summary segments, per-frame modality attention, and summary-only playback.

## Structure

```
index.html, css/, js/        the site (vanilla HTML/CSS/JS, no build step)
assets/                      poster, paper figures, logo
data/videos.json             demo manifest (20 videos)
data/v/{id}.json             per-video time series (scores, segments, attention)
videos/{id}.mp4 + thumbs/    540p H.264 demo videos + poster frames
pipeline/                    offline scripts that produced the assets
```

## Pipeline (reproducing the demo assets)

Run on a GPU node with the TripleSumm code checkout next to this repo
(`../TripleSumm` or adjust paths at the top of each script):

1. `python pipeline/dump_pred_scores.py` — inference over the MoSu test split → `work/test_pred_scores.h5`
2. `python pipeline/select_candidates.py` — metric + multi-peak GT + dispersion + cluster-diversity funnel → ~45 candidates
3. `LD_LIBRARY_PATH=$CONDA_PREFIX/lib python pipeline/make_contact_sheets.py` — review sheets; pick 20 ids into `work/selected.json`
4. `python pipeline/build_web_assets.py` — encodes videos, builds per-video JSON + manifest
   (scores are lightly gaussian-smoothed for display; ktau/srho metrics stay on raw scores)
5. `python pipeline/verify_site.py` — headless checks (needs `pip install playwright` + a local `python -m http.server 8741`)

## Local preview

```bash
python -m http.server 8000   # then open http://localhost:8000
```

## Deploy

Push to a GitHub repo and enable **Settings → Pages → Deploy from branch** (root).
All asset paths are relative, so the site works at any subpath (e.g. `user.github.io/TripleSumm`).
