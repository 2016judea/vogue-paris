"""Crop each Gallica scan to the printed page and straighten it.

Gallica's scans are photographs of the bound originals: around the page there
are thin strips of the white scanner bed, the dark gutter and binding, and the
edges of the neighbouring leaves (2026-11-08, Aidan's screenshot of 15 juin 1920).

Method, per side of the page:
  * take the outer band (BAND of the width or height)
  * smooth along the edge's direction so print and pictures blur out and long
    straight boundaries survive
  * the page edge is the strongest brightness step in that band
It's measured twice per side (first and second half of the edge), so a tilted
page gives two points and therefore an angle. The page is levelled by the mean
of the left/right tilts (never more than MAX_TILT, so a page is never turned on
its side), then cropped inside all four edges.

Anything that doesn't look like a page edge (a weak step, or a crop that would
remove too much) leaves that side alone: a missed crop costs less than a wrong one.

Usage: python crop.py <in.jpg> <out.jpg>   or   python crop.py --dir <in> <out>
"""
import sys, os
import cv2
import numpy as np

BAND = 0.075        # how far in from each border an edge may be
MAX_TILT = 2.5      # degrees
MIN_STEP = 18       # minimum brightness step (0-255) that counts as an edge
INSET = 4           # px (at full size) trimmed inside the edge to drop the shadow line


MAX_SIDE = 0.06     # never remove more than this fraction from one side


def walk(lines, paper, paper_rb, limit):
    """Count leading lines (columns or rows, outermost first) that are background.

    Each line is (brightness, warmth) where warmth is red minus blue. Background is
    the scanner bed (as bright as or brighter than the paper, and neutral rather than
    warm like aged paper) or the gutter/binding (dark). The walk stops at the first
    line that isn't, so it only removes what is plainly not page.
    (2026-11-08: brightness alone cut the "1" off "15 Juin" — that paper is as
    bright as the bed. Warmth is what separates them.)
    """
    n = 0
    for m, rb in lines[:limit]:
        bed = m > max(paper - 4, 205) and rb < paper_rb - 3.5
        if bed or m < 105:
            n += 1
        else:
            break
    return n


def side_edges(small):
    """Return dict side -> [inset at first half, inset at second half] in px of `small`."""
    h, w = small.shape[:2]
    f = small.astype(np.float32)
    gray = f.mean(axis=2)
    rb = f[:, :, 2] - f[:, :, 0]
    cg = gray[int(h * .2):int(h * .8), int(w * .2):int(w * .8)]
    crb = rb[int(h * .2):int(h * .8), int(w * .2):int(w * .8)]
    paper = float(np.percentile(cg, 75))
    paper_rb = float(np.median(crb[cg > np.percentile(cg, 60)]))
    out = {}
    for k in (0, 1):
        r0, r1 = int(h * (0.08 + 0.42 * k)), int(h * (0.5 + 0.42 * k))
        c0, c1 = int(w * (0.08 + 0.42 * k)), int(w * (0.5 + 0.42 * k))
        col_m, col_rb = gray[r0:r1].mean(axis=0), rb[r0:r1].mean(axis=0)
        row_m, row_rb = gray[:, c0:c1].mean(axis=1), rb[:, c0:c1].mean(axis=1)
        cols = list(zip(col_m, col_rb)); rows = list(zip(row_m, row_rb))
        lim_w, lim_h = int(w * MAX_SIDE), int(h * MAX_SIDE)
        out.setdefault('left', []).append(walk(cols, paper, paper_rb, lim_w))
        out.setdefault('right', []).append(walk(cols[::-1], paper, paper_rb, lim_w))
        out.setdefault('top', []).append(walk(rows, paper, paper_rb, lim_h))
        out.setdefault('bottom', []).append(walk(rows[::-1], paper, paper_rb, lim_h))
    return out


def crop(img):
    H, W = img.shape[:2]
    s = 1000 / H
    small = cv2.resize(img, (int(W * s), 1000), interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    e = side_edges(small)
    # tilt: how the left/right insets change between the upper and lower half
    tilts = []
    for name, sign in (('left', 1), ('right', -1)):
        a, b = e[name]
        if a or b:
            tilts.append(np.degrees(np.arctan2(sign * (b - a), 0.42 * h)))
    ang = float(np.mean(tilts)) if tilts else 0.0
    if abs(ang) > MAX_TILT or (len(tilts) == 2 and abs(tilts[0] - tilts[1]) > 0.8):
        ang = 0.0
    if abs(ang) > 0.25:
        M = cv2.getRotationMatrix2D((W / 2, H / 2), ang, 1.0)
        img = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        e = side_edges(cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA))
    l, r, t, b = (max(e[k]) for k in ('left', 'right', 'top', 'bottom'))
    if not (l or r or t or b) and abs(ang) <= 0.25:
        return img, False
    x0 = int(l / s) + (INSET if l else 0); x1 = W - int(r / s) - (INSET if r else 0)
    y0 = int(t / s) + (INSET if t else 0); y1 = H - int(b / s) - (INSET if b else 0)
    return img[y0:y1, x0:x1], True


def one(src, dst):
    out, ok = crop(cv2.imread(src))
    cv2.imwrite(dst, out, [cv2.IMWRITE_JPEG_QUALITY, 93])
    return ok


if __name__ == '__main__':
    if sys.argv[1] == '--dir':
        src, dst = sys.argv[2], sys.argv[3]
        os.makedirs(dst, exist_ok=True)
        n = ok = 0
        for f in sorted(os.listdir(src)):
            if f.endswith('.jpg'):
                n += 1
                ok += one(os.path.join(src, f), os.path.join(dst, f))
        print(f'{ok}/{n} cropped')
    else:
        print(one(sys.argv[1], sys.argv[2]))
