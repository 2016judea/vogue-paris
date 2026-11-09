"""Review sheets for the per-page crop: Claude looks at every page (Aidan, 2026-11-08:
"we need to be manually inspecting every page and custom cropping it").

For each page of an issue, draws the current crop (auto quad from page_crop.py,
with any correction from data/crop_overrides.json applied) over the ORIGINAL scan,
plus the four corners zoomed in, so a reviewer can see what is in and what is out.

Workflow per issue: scripts/review_issue.sh <ark> proposes quads into
data/crop_auto/<ark>.json and renders the sheets; the reviewer writes
data/crop_review/<ark>.json; scripts/apply_crop.py and sync.mjs do the rest.

A correction is per side, in thousandths of the scan's width (left/right) or
height (top/bottom); positive moves that edge INTO the page, negative out:
  data/crop_review/<ark>.json  {"p001.jpg": {"left": 6, "top": -3}, "p002.jpg": "ok", ...}
"ok" marks a page as reviewed with no change: {"p002.jpg": "ok"}.

Usage: python review_sheet.py <ark> <out_dir> [page.jpg ...]   (default: every page the site shows)
"""
import sys, os, json
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RED, GRN, CYAN = (40, 40, 230), (40, 180, 40), (255, 255, 0)


def load_review(ark):
    p = os.path.join(ROOT, 'data/crop_review', ark + '.json')
    return json.load(open(p)) if os.path.exists(p) else {}


def site_pages(ark):
    u = json.load(open(os.path.join(ROOT, 'data/uploaded.json')))[ark]
    return [f'p{n:03d}.jpg' for n in range(u['first'], u['last'] + 1)]


def final_quad(meta, ov):
    """Normalised tl/tr/br/bl after the per-side correction."""
    q = meta.get('quad') or {'tl': [0, 0], 'tr': [1, 0], 'br': [1, 1], 'bl': [0, 1]}
    q = {k: np.array(v, float) for k, v in q.items()}
    if isinstance(ov, dict):
        d = {k: ov.get(k, 0) / 1000 for k in ('left', 'right', 'top', 'bottom')}
        q['tl'] += [d['left'], d['top']]; q['bl'] += [d['left'], -d['bottom']]
        q['tr'] += [-d['right'], d['top']]; q['br'] += [-d['right'], -d['bottom']]
    return q


def tile(img, q, label, flag):
    H, W = img.shape[:2]
    P = {k: (v * [W, H]).astype(np.float32) for k, v in q.items()}
    poly = np.int32([P['tl'], P['tr'], P['br'], P['bl']])
    # tint everything the crop throws away, so in vs out reads at a glance
    mask = np.zeros((H, W), np.uint8); cv2.fillConvexPoly(mask, poly, 255)
    tint = (img * 0.45 + np.array([200, 0, 200]) * 0.55).astype(np.uint8)
    img = np.where(mask[..., None] > 0, img, tint)
    TH = 600; s = TH / H
    th = cv2.resize(img, (int(W * s), TH), interpolation=cv2.INTER_AREA)
    cv2.polylines(th, [np.int32(poly * s)], True, CYAN, 1, cv2.LINE_AA)
    Z = int(0.05 * H); ZS = 300
    zs = []
    for k in ('tl', 'tr', 'bl', 'br'):
        cx, cy = P[k]
        x0 = int(np.clip(cx - Z / 2, 0, W - Z)); y0 = int(np.clip(cy - Z / 2, 0, H - Z))
        win = img[y0:y0 + Z, x0:x0 + Z].copy()
        f = ZS / Z
        win = cv2.resize(win, (ZS, ZS), interpolation=cv2.INTER_AREA)
        cv2.polylines(win, [np.int32((poly - [x0, y0]) * f)], True, CYAN, 1, cv2.LINE_AA)
        zs.append(win)
    grid = np.vstack([np.hstack(zs[:2]), np.hstack(zs[2:])])
    row = np.hstack([th, np.full((TH, 6, 3), 255, np.uint8), grid])
    lab = np.full((30, row.shape[1], 3), 255, np.uint8)
    cv2.putText(lab, label, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, GRN if not flag else RED, 2)
    return np.vstack([lab, row])


def main():
    ark, out = sys.argv[1], sys.argv[2]
    per = 4
    meta = json.load(open(os.path.join(ROOT, 'data/crop_auto', ark + '.json')))
    ov = load_review(ark)
    src = os.path.join(ROOT, 'mirror-hi', ark)
    pages = sys.argv[3:] or site_pages(ark)
    os.makedirs(out, exist_ok=True)
    rows = []
    for f in pages:
        m = meta.get(f, {})
        q = final_quad(m, ov.get(f))
        flag = '' if m.get('ok') else ' AUTO FAILED: ' + m.get('why', '?')
        rows.append(tile(cv2.imread(os.path.join(src, f)), q, f'{f}{flag}  ov={ov.get(f, "-")}', flag))
    paths = []
    for i in range(0, len(rows), per):
        chunk = rows[i:i + per]
        W = max(r.shape[1] for r in chunk)
        # two tiles per row of the sheet
        padded = [np.hstack([r, np.full((r.shape[0], W - r.shape[1], 3), 255, np.uint8)]) for r in chunk]
        pairs = [np.hstack(padded[j:j + 2]) if j + 1 < len(padded) else np.hstack([padded[j], np.full_like(padded[j], 255)]) for j in range(0, len(padded), 2)]
        p = os.path.join(out, f'{ark}-{i // per + 1:03d}.jpg')
        cv2.imwrite(p, np.vstack(pairs), [cv2.IMWRITE_JPEG_QUALITY, 82]); paths.append(p)
    print('\n'.join(paths))


if __name__ == '__main__':
    main()
