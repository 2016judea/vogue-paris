"""Visual QA for cropped pages: score every page, flag the doubtful ones, and draw
contact sheets of their edges for a human (or Claude) to look at.

Run after scripts/page_crop.py has written mirror-crop/<ark>/ and its crop.json.

Checks, per page (every one is a way the 15 aout 1920 cover went wrong):
  * crop failed or the detector was unsure (conf < 0.9)
  * a weak edge: no clear colour change was found on a side (median edge score
    low), so that side may still hold background or may have been cut inside
  * a dirty border: the outermost 1% band of the cropped page differs from the
    band just inside it (foreign text, gutter shadow, a leaf edge, scanner bed),
    or holds dark specks that look like another page's type
  * an odd shape: aspect ratio more than 2.5% off the issue's median, which
    would also break a uniform trim size for print
Overrides from data/crop_overrides.json are applied by page_crop.py; this
script only reports.

Output:
  qa/<ark>.json         per-page metrics and flags
  qa/sheets/<ark>-NN.jpg  contact sheets: for each flagged page, the page plus
                          its four corners and four mid-edges at 1:1-ish zoom
Usage: python qa_pages.py <ark> [<ark> ...]   (or --all)
"""
import sys, os, json
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CROP = os.path.join(ROOT, 'mirror-crop')
OUT = os.path.join(ROOT, 'qa')


def border_metrics(img):
    lab = cv2.cvtColor(cv2.resize(img, (600, int(600 * img.shape[0] / img.shape[1]))), cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = lab.shape[:2]
    b1, b2 = max(2, int(0.01 * w)), max(4, int(0.03 * w))
    res = {}
    for name, outer, inner in (
        ('top', lab[:b1, b2:-b2], lab[b1:b2, b2:-b2]),
        ('bottom', lab[-b1:, b2:-b2], lab[-b2:-b1, b2:-b2]),
        ('left', lab[b2:-b2, :b1], lab[b2:-b2, b1:b2]),
        ('right', lab[b2:-b2, -b1:], lab[b2:-b2, -b2:-b1]),
    ):
        d = float(np.linalg.norm(outer.reshape(-1, 3).mean(0) - inner.reshape(-1, 3).mean(0)))
        dark = float((outer[..., 0] < 70).mean())
        res[name] = {'diff': round(d, 1), 'dark': round(dark, 3)}
    return res


def qa_issue(ark):
    d = os.path.join(CROP, ark)
    meta = json.load(open(os.path.join(d, 'crop.json')))
    pages = sorted(f for f in meta if f.endswith('.jpg'))
    aspects = {f: meta[f]['size'][0] / meta[f]['size'][1] for f in pages if meta[f].get('ok')}
    med = float(np.median(list(aspects.values()))) if aspects else None
    report = {}
    for f in pages:
        m = meta[f]; flags = []
        if not m.get('ok'):
            flags.append('crop failed: ' + m.get('why', '?'))
        else:
            if m.get('conf', 1) < 0.9: flags.append(f"detector unsure ({m['conf']:.2f})")
            weak = [k for k, v in m.get('edge_scores', {}).items() if v < 12]
            if weak: flags.append('weak edge: ' + ','.join(weak))
            if med and abs(aspects[f] / med - 1) > 0.025: flags.append(f'aspect {aspects[f]:.3f} vs {med:.3f}')
            img = cv2.imread(os.path.join(d, f))
            bm = border_metrics(img)
            dirty = [k for k, v in bm.items() if v['diff'] > 9 or v['dark'] > 0.04]
            if dirty: flags.append('dirty border: ' + ','.join(dirty))
            m['border'] = bm
        report[f] = {'flags': flags, **{k: m[k] for k in ('conf', 'edge_scores', 'tilt', 'area', 'border') if k in m}}
    os.makedirs(OUT, exist_ok=True)
    json.dump(report, open(os.path.join(OUT, ark + '.json'), 'w'), indent=0)
    flagged = [f for f in pages if report[f]['flags']]
    sheets(ark, flagged, report)
    return len(pages), len(flagged)


def tile(ark, f, flags):
    """One row: the cropped page small, then 8 zoomed edge windows of the crop."""
    img = cv2.imread(os.path.join(CROP, ark, f)); h, w = img.shape[:2]
    H = 260
    thumb = cv2.resize(img, (int(w * H / h), H))
    z = int(0.07 * w)
    wins = [(0, 0), (w // 2 - z // 2, 0), (w - z, 0), (w - z, h // 2 - z // 2),
            (w - z, h - z), (w // 2 - z // 2, h - z), (0, h - z), (0, h // 2 - z // 2)]
    zs = [cv2.resize(img[y:y + z, x:x + z], (H // 2, H // 2)) for x, y in wins]
    grid = np.vstack([np.hstack(zs[:4]), np.hstack(zs[4:])])
    row = np.hstack([thumb, np.full((H, 6, 3), 255, np.uint8), grid])
    lab = np.full((24, row.shape[1], 3), 255, np.uint8)
    cv2.putText(lab, f'{ark} {f}  ' + '; '.join(flags)[:110], (4, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 200), 1)
    return np.vstack([lab, row])


def sheets(ark, flagged, report, per=8):
    os.makedirs(os.path.join(OUT, 'sheets'), exist_ok=True)
    for i in range(0, len(flagged), per):
        rows = [tile(ark, f, report[f]['flags']) for f in flagged[i:i + per]]
        W = max(r.shape[1] for r in rows)
        rows = [np.hstack([r, np.full((r.shape[0], W - r.shape[1], 3), 255, np.uint8)]) for r in rows]
        cv2.imwrite(os.path.join(OUT, 'sheets', f'{ark}-{i // per + 1:02d}.jpg'), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])


if __name__ == '__main__':
    arks = sorted(os.listdir(CROP)) if sys.argv[1] == '--all' else sys.argv[1:]
    tot = fl = 0
    for a in arks:
        if not os.path.exists(os.path.join(CROP, a, 'crop.json')): continue
        n, f = qa_issue(a); tot += n; fl += f
        print(f'{a}: {f}/{n} flagged')
    print(f'TOTAL {fl}/{tot} flagged')
