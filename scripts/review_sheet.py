"""Review sheets for the per-page crop: Claude looks at every page (Aidan, 2026-11-08:
"we need to be manually inspecting every page and custom cropping it").

For each page of an issue, draws the current crop (auto quad from page_crop.py,
with any correction from data/crop_overrides.json applied) over the ORIGINAL scan,
plus the four corners zoomed in, so a reviewer can see what is in and what is out.

Workflow per issue: scripts/review_issue.sh <ark> proposes quads into
data/crop_auto/<ark>.json and renders the sheets; the reviewer writes
data/crop_review/<ark>.json; scripts/apply_crop.py and sync.mjs do the rest.

In the corner zooms, red ticks on each window's border mark every 5 thousandths of
the scan (long tick = 25), so 1 tick = 5 units of correction.

A correction is per side, in thousandths of the scan's width (left/right) or
height (top/bottom); positive moves that edge INTO the page, negative out:
  data/crop_review/<ark>.json  {"p001.jpg": {"left": 6, "top": -3}, "p002.jpg": "ok", ...}
The crop is always a rectangle (see final_quad). "rot" sets its angle in degrees
when the auto angle is wrong: {"rot": 0.4, "right": 12}.
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


def final_quad(meta, ov, W, H):
    """Pixel corners tl/tr/br/bl of the final crop: always a true rectangle.

    A printed page is a rectangle, so the crop is one too: a small rotation plus
    four straight sides. (2026-11-09: letting the auto quad's corners move freely
    meant a sloped bottom edge got warped "straight" and skewed the 15 juin 1920
    cover.) The angle is the median slope of the auto quad's four sides, unless
    the review sets "rot" (degrees, + = clockwise). Each side sits at the mean
    position of the auto quad's two corners on it, measured in the rotated frame,
    then moves by the reviewer's per-side correction.
    """
    q = meta.get('quad') or {'tl': [0, 0], 'tr': [1, 0], 'br': [1, 1], 'bl': [0, 1]}
    P = {k: np.array(v, float) * [W, H] for k, v in q.items()}
    ang = lambda a, b: np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0]))
    slopes = [ang(P['tl'], P['tr']), ang(P['bl'], P['br']),
              ang(P['tl'], P['bl']) - 90, ang(P['tr'], P['br']) - 90]
    th = float(np.clip(np.median(slopes), -3, 3))
    if isinstance(ov, dict) and 'rot' in ov: th = float(ov['rot'])
    c, s_ = np.cos(np.radians(th)), np.sin(np.radians(th))
    to = lambda p: np.array([c * p[0] + s_ * p[1], -s_ * p[0] + c * p[1]])      # into the page's frame
    fr = lambda p: np.array([c * p[0] - s_ * p[1], s_ * p[0] + c * p[1]])       # back to the scan
    R = {k: to(v) for k, v in P.items()}
    L, Rt = (R['tl'][0] + R['bl'][0]) / 2, (R['tr'][0] + R['br'][0]) / 2
    T, B = (R['tl'][1] + R['tr'][1]) / 2, (R['bl'][1] + R['br'][1]) / 2
    if isinstance(ov, dict):
        L += ov.get('left', 0) * W / 1000; Rt -= ov.get('right', 0) * W / 1000
        T += ov.get('top', 0) * H / 1000; B -= ov.get('bottom', 0) * H / 1000
    return {'tl': fr([L, T]), 'tr': fr([Rt, T]), 'br': fr([Rt, B]), 'bl': fr([L, B])}, th


def tile(img, q, label, flag):
    H, W = img.shape[:2]
    P = {k: np.float32(v) for k, v in q.items()}
    poly = np.int32([P['tl'], P['tr'], P['br'], P['bl']])
    raw = img
    # tint everything the crop throws away, so in vs out reads at a glance
    mask = np.zeros((H, W), np.uint8); cv2.fillConvexPoly(mask, poly, 255)
    tint = (img * 0.45 + np.array([200, 0, 200]) * 0.55).astype(np.uint8)
    img = np.where(mask[..., None] > 0, img, tint)
    TH = 600; s = TH / H
    th = cv2.resize(img, (int(W * s), TH), interpolation=cv2.INTER_AREA)
    cv2.polylines(th, [np.int32(poly * s)], True, CYAN, 1, cv2.LINE_AA)
    # Corner zooms show the RAW scan (no tint: 2026-11-09, tinting the paper outside
    # the line made a cream margin look like scanner bed, and two reviewers cut into
    # the 15 juin 1920 cover). Ticks on the window border every 5 thousandths of the
    # scan (long tick every 25) let a reviewer count the distance from line to edge.
    Z = int(0.05 * H); ZS = 300
    zs = []
    for k in ('tl', 'tr', 'bl', 'br'):
        cx, cy = P[k]
        x0 = int(np.clip(cx - Z / 2, 0, W - Z)); y0 = int(np.clip(cy - Z / 2, 0, H - Z))
        f = ZS / Z
        win = cv2.resize(raw[y0:y0 + Z, x0:x0 + Z], (ZS, ZS), interpolation=cv2.INTER_AREA)
        cv2.polylines(win, [np.int32((poly - [x0, y0]) * f)], True, CYAN, 1, cv2.LINE_AA)
        for axis, size, o in ((0, W, x0), (1, H, y0)):
            step = size * 0.005
            first = int(np.ceil(o / step))
            for i in range(first, int((o + Z) / step) + 1):
                v = int((i * step - o) * f); L = 14 if i % 5 == 0 else 6
                if axis == 0: cv2.line(win, (v, 0), (v, L), (0, 0, 255), 1); cv2.line(win, (v, ZS - 1), (v, ZS - 1 - L), (0, 0, 255), 1)
                else: cv2.line(win, (0, v), (L, v), (0, 0, 255), 1); cv2.line(win, (ZS - 1, v), (ZS - 1 - L, v), (0, 0, 255), 1)
        cv2.rectangle(win, (0, 0), (ZS - 1, ZS - 1), (90, 90, 90), 1)
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
        img = cv2.imread(os.path.join(src, f))
        q, th = final_quad(m, ov.get(f), img.shape[1], img.shape[0])
        flag = '' if m.get('ok') else ' AUTO FAILED: ' + m.get('why', '?')
        rows.append(tile(img, q, f'{f}{flag}  rot={th:+.2f}  ov={ov.get(f, "-")}', flag))
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
