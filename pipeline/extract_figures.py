"""Extract figures from the paper PDF.

Modes:
  render : render full pages at high zoom to work/figures_raw/page_N.png
  crop   : crop a region from a page: --crop PAGE X0 Y0 X1 Y1 OUT
           (coordinates in PDF points, as shown by `render` at zoom 1)

Usage:
  python pipeline/extract_figures.py render
  python pipeline/extract_figures.py crop --crop 2 50 80 550 280 assets/figures/fig1_motivation.png
"""
import argparse
import os

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
PDF = os.path.join(ROOT, 'TripleSumm-page', 'TripleSumm_iclr26.pdf')
RAW = os.path.join(HERE, 'work', 'figures_raw')
ZOOM = 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['render', 'crop'])
    ap.add_argument('--pages', type=str, default='1-10')
    ap.add_argument('--crop', nargs=6, metavar=('PAGE', 'X0', 'Y0', 'X1', 'Y1', 'OUT'))
    args = ap.parse_args()

    doc = fitz.open(PDF)
    if args.mode == 'render':
        os.makedirs(RAW, exist_ok=True)
        a, b = (int(x) for x in args.pages.split('-'))
        for i in range(a - 1, min(b, len(doc))):
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
            out = os.path.join(RAW, f'page_{i + 1}.png')
            pix.save(out)
            print(out, pix.width, pix.height)
    else:
        page, x0, y0, x1, y1, out = args.crop
        page = int(page)
        clip = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
        pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip)
        os.makedirs(os.path.dirname(os.path.join(ROOT, out)), exist_ok=True)
        pix.save(os.path.join(ROOT, out))
        print(os.path.join(ROOT, out), pix.width, pix.height)


if __name__ == '__main__':
    main()
