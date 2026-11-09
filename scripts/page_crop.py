"""Cut each Gallica scan down to the physical page, square and level.

Gallica's scans are photographs of bound originals: around the page sit the
scanner bed, the gutter, the binding, the edges of neighbouring leaves, and
sometimes a strip of the facing page with its text (15 août 1920 cover,
Aidan, 2026-11-08). Brightness rules can't tell a neighbouring page from this
one, so the crop runs in two stages:

1. Coarse: Apple's on-device document segmentation model (bin/pagequad, the
   Notes/Files document scanner) returns the page's four corners. It picks
   the right sheet but its edges are off by 1-2%.
2. Fine: along each side, ~40 cross-sections are taken through the coarse
   edge. On each, the edge is where the colour just outside differs most from
   the colour just inside (Lab distance between two short strips). A printed
   frame rule has the same paper on both sides, so it scores low; the true
   paper edge scores high. A robust line is fitted through the 40 points.
   The four lines meet in four corners, and a perspective warp turns the page
   into an upright rectangle (orientation is kept: corners are matched
   tl/tr/br/bl as found, and only small tilts are accepted).

Writes the cropped JPEG plus a JSON sidecar with the quad and the QA metrics
(scripts/qa_pages.py reads them).

Usage: python page_crop.py <in_dir> <out_dir> [page.jpg ...]
"""
import sys, os, json, subprocess
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = 40          # cross-sections per side
WIN = 0.035           # search ± this fraction of the page dimension around the coarse edge
STRIP = 22            # px (at working scale) of colour compared on each side; wide, so thin rules dilute
INSET = 0.0025        # trim inside the refined edge to lose the shadow line
WORK = 1400           # working height for refinement


def quads(paths):
    out = subprocess.run([os.path.join(ROOT, 'bin/pagequad'), *paths], capture_output=True, text=True).stdout
    res, cur = [], []
    for line in out.split('\n'):
        if line == '--':
            res.append(cur); cur = []
        elif line.startswith('{'):
            cur.append(json.loads(line))
    return res


def refine_side(lab, p0, p1, inward, paper):
    """Refine the edge running p0->p1 (px). `inward` is the unit normal into the page.

    For each cross-section, the Lab profile along the normal is sampled at 1px
    steps. At each candidate offset the mean colour of a STRIP-wide band just
    outside is compared with one just inside. The score is that difference,
    weighted by how unlike this page's paper the outside band is. A printed rule
    near the edge (15 aout 1920: a thick red frame) has paper beyond it, so its
    outside band stays paper-like and scores low; the real edge has bed, gutter
    or another leaf outside and scores high.
    """
    h, w = lab.shape[:2]
    span = int(WIN * max(h, w))
    offs = np.arange(-span - STRIP - 2, span + STRIP + 3, dtype=np.float32)
    pts, scores = [], []
    for t in np.linspace(0.08, 0.92, SAMPLES):
        base = p0 + t * (p1 - p0)
        xs = (base[0] + offs * inward[0]).reshape(1, -1).astype(np.float32)
        ys = (base[1] + offs * inward[1]).reshape(1, -1).astype(np.float32)
        prof = cv2.remap(lab, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)[0]   # (n, 3)
        cs = np.vstack([np.zeros((1, 3), np.float32), np.cumsum(prof, axis=0)])
        def band(i0, i1): return (cs[i1] - cs[i0]) / (i1 - i0)
        best, best_s = None, 0.0
        for j in range(STRIP + 2, len(offs) - STRIP - 2):
            out = band(j - 2 - STRIP, j - 2)
            inn = band(j + 2, j + 2 + STRIP)
            diff = float(np.linalg.norm(out - inn))
            foreign = min(1.0, float(np.linalg.norm(out - paper)) / 18.0)
            sc = diff * foreign
            if sc > best_s:
                best_s, best = sc, base + offs[j] * inward
        if best is not None:
            pts.append(best); scores.append(best_s)
    if len(pts) < SAMPLES // 3:
        return None, 0.0
    pts = np.array(pts, np.float32)
    line = cv2.fitLine(pts, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
    return line, float(np.median(scores))


def intersect(a, b):
    (vx1, vy1, x1, y1), (vx2, vy2, x2, y2) = a, b
    A = np.array([[vx1, -vx2], [vy1, -vy2]]); B = np.array([x2 - x1, y2 - y1])
    t = np.linalg.solve(A, B)[0]
    return np.array([x1 + t * vx1, y1 + t * vy1])


def crop_one(src, q):
    img = cv2.imread(src)
    H, W = img.shape[:2]
    seg = [d for d in q if d['kind'] == 'segment']
    meta = {'src': os.path.basename(src), 'ok': False}
    if not seg:
        meta['why'] = 'no page found'
        return img, meta
    d = seg[0]
    meta['conf'] = d['conf']
    s = WORK / H
    small = cv2.resize(img, (int(W * s), WORK), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = small.shape[:2]
    P = {k: np.array([d[k][0] * w, d[k][1] * h]) for k in ('tl', 'tr', 'br', 'bl')}
    centre = sum(P.values()) / 4
    # this page's paper: median colour of a band just inside the coarse edges (mostly margin)
    m = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(m, np.int32([P['tl'], P['tr'], P['br'], P['bl']]), 255)
    inner = cv2.erode(m, np.ones((int(0.06 * h),) * 2, np.uint8))
    ring = (m > 0) & (cv2.erode(m, np.ones((int(0.015 * h),) * 2, np.uint8)) > 0) & (inner == 0)
    paper = np.median(lab[ring], axis=0) if ring.any() else np.median(lab.reshape(-1, 3), axis=0)
    lines, edge_scores = {}, {}
    for name, a, b in (('top', 'tl', 'tr'), ('right', 'tr', 'br'), ('bottom', 'br', 'bl'), ('left', 'bl', 'tl')):
        v = P[b] - P[a]; n = np.array([-v[1], v[0]]) / np.linalg.norm(v)
        if np.dot(centre - P[a], n) < 0: n = -n
        line, sc = refine_side(lab, P[a], P[b], n, paper)
        lines[name], edge_scores[name] = line, sc
    meta['edge_scores'] = edge_scores
    if any(l is None for l in lines.values()):
        meta['why'] = 'edge refinement failed'
        return img, meta
    C = {
        'tl': intersect(lines['top'], lines['left']), 'tr': intersect(lines['top'], lines['right']),
        'br': intersect(lines['bottom'], lines['right']), 'bl': intersect(lines['bottom'], lines['left']),
    }
    # sanity: refined corners must stay near the coarse ones, and the page must be upright-ish
    drift = max(np.linalg.norm(C[k] - P[k]) for k in C) / max(h, w)
    top = C['tr'] - C['tl']; tilt = abs(np.degrees(np.arctan2(top[1], top[0])))
    meta.update(drift=round(float(drift), 4), tilt=round(float(tilt), 2))
    if drift > WIN * 1.2 or tilt > 4:
        meta['why'] = 'refined edges implausible'
        return img, meta
    Cf = {k: v / s for k, v in C.items()}
    wid = (np.linalg.norm(Cf['tr'] - Cf['tl']) + np.linalg.norm(Cf['br'] - Cf['bl'])) / 2
    hei = (np.linalg.norm(Cf['bl'] - Cf['tl']) + np.linalg.norm(Cf['br'] - Cf['tr'])) / 2
    iw, ih = int(round(wid)), int(round(hei))
    dx, dy = INSET * iw, INSET * ih
    dst = np.float32([[-dx, -dy], [iw + dx, -dy], [iw + dx, ih + dy], [-dx, ih + dy]])
    M = cv2.getPerspectiveTransform(np.float32([Cf['tl'], Cf['tr'], Cf['br'], Cf['bl']]), dst)
    out = cv2.warpPerspective(img, M, (iw, ih), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    meta.update(ok=True, quad={k: [round(float(v[0] / w), 5), round(float(v[1] / h), 5)] for k, v in C.items()},
                size=[iw, ih], area=round(float(iw * ih / (W * H)), 3))
    return out, meta


def main():
    src_dir, dst_dir = sys.argv[1], sys.argv[2]
    os.makedirs(dst_dir, exist_ok=True)
    files = sys.argv[3:] or sorted(f for f in os.listdir(src_dir) if f.endswith('.jpg'))
    paths = [os.path.join(src_dir, f) for f in files]
    allmeta = {}
    for f, p, q in zip(files, paths, quads(paths)):
        out, meta = crop_one(p, q)
        cv2.imwrite(os.path.join(dst_dir, f), out, [cv2.IMWRITE_JPEG_QUALITY, 93])
        allmeta[f] = meta
    mp = os.path.join(dst_dir, 'crop.json')
    prev = json.load(open(mp)) if os.path.exists(mp) else {}
    prev.update(allmeta)
    json.dump(prev, open(mp, 'w'), indent=0)
    ok = sum(m['ok'] for m in allmeta.values())
    print(f'{ok}/{len(allmeta)} cropped')


if __name__ == '__main__':
    main()
