# TripleSumm — Project Page & Interactive Demo (ICLR 2026)

Project page for **TripleSumm: Adaptive Triple-Modality Fusion for Video Summarization**
(Kim et al., ICLR 2026) — live at **https://smkim37.github.io/TripleSumm-page/**

The centerpiece is an interactive demo of 20 curated videos from the MoSu test split.
As each video plays, time-synced charts show the model's predicted importance against the
Most-Replayed ground truth, the selected summary segments, and the per-frame attention the
model assigns to the visual / text / audio modalities. A *Summary only* toggle plays just the
15% of the video the model would keep.

## Repository layout

```
index.html                   single-page site (no build step)
css/style.css                design system + layout (mobile-first, 90% base scale ≥768px)
js/player.js                 DemoPlayer: video + canvas charts, sync, seek, summary-skip
js/main.js                   gallery, TOC, scroll autoplay, poster zoom viewer, BibTeX copy
assets/                      poster (png/pdf), paper figures, logo
data/videos.json             demo manifest (20 videos, ordering = gallery order)
data/v/{id}.json             per-video time series: scores, segments, attention
videos/{id}.mp4, thumbs/     540p H.264 demo videos (≤30 MB each) + poster frames
pipeline/                    offline scripts that produced everything above
```

## Demo video pipeline

Scripts expect the TripleSumm research code at `../TripleSumm` (checkpoint + attention h5)
and the MoSu dataset at `/data/dataset/VideoSummarization/mosu` (read-only). Run in order:

| Step | Script | Output |
|---|---|---|
| 1. Inference | `dump_pred_scores.py` (GPU) | `work/test_pred_scores.h5`, sanity-checked against published per-video ktau+srho |
| 2. Selection | `select_candidates.py` | ~45 candidates: raw mp4 exists · 120–300 s · top ktau+srho · **multi-peak GT (≥4 prominent peaks)** · summary dispersion · cluster diversity |
| 3. Review | `make_contact_sheets.py`¹ | one sheet per candidate (frames + curves) for manual curation → write 20 ids to `work/selected.json` |
| 4. Assets | `build_web_assets.py` | mp4 (540p, faststart), thumbnails, per-video JSON, manifest. Display scores are min-max normalized and lightly gaussian-smoothed (σ=2); metrics stay on raw scores. Attention = mean over 2 layers × 4 heads, truncated to GT length, row-renormalized. Titles via YouTube oEmbed (cached in `work/titles.json`). |
| 5. Verify | `verify_site.py`² | checks across iPhone/Galaxy/iPad/Galaxy Tab/desktop viewports |

¹ needs `LD_LIBRARY_PATH=$CONDA_PREFIX/lib` for matplotlib on the cluster.
² needs `pip install playwright && python -m playwright install chromium`.

## Local preview

```bash
pip install rangehttpserver
python -m RangeHTTPServer 8741        # NOT python -m http.server
```

Plain `http.server` does not support HTTP Range requests, so video **seeking will not work**
locally with it (GitHub Pages serves ranges fine — production is unaffected).

## Deploy

```bash
git push origin main   # GitHub Pages: deploy from branch, root
```

All asset paths are relative, so the site works at any subpath. `.nojekyll` keeps Pages from
running Jekyll. Keep each mp4 under 100 MB (GitHub hard limit); the build script re-encodes
anything over 30 MB automatically.

## Citation

```bibtex
@inproceedings{kim2026triplesumm,
  title     = {TripleSumm: Adaptive Triple-Modality Fusion for Video Summarization},
  author    = {Sumin Kim and Hyemin Jeong and Mingu Kang and Yejin Kim and Yoori Oh and Joonseok Lee},
  booktitle = {The Fourteenth International Conference on Learning Representations},
  year      = {2026}
}
```
