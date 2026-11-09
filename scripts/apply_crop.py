"""Write the final, reviewed crop of every page of an issue.

Quad per page = the auto proposal (data/crop_auto/<ark>.json, from page_crop.py)
moved by Claude's per-side correction (data/crop_review/<ark>.json), see
scripts/review_sheet.py for the format. The page is warped from its four corners
to an upright rectangle, so a slightly skewed scan comes out level.

Usage: python apply_crop.py <ark> <out_dir>
"""
import sys, os, json
import cv2
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from review_sheet import final_quad, ROOT

ark, out = sys.argv[1], sys.argv[2]
auto = json.load(open(os.path.join(ROOT, 'data/crop_auto', ark + '.json')))
rev = json.load(open(os.path.join(ROOT, 'data/crop_review', ark + '.json')))
os.makedirs(out, exist_ok=True)
for f, ov in rev.items():
    img = cv2.imread(os.path.join(ROOT, 'mirror-hi', ark, f))
    H, W = img.shape[:2]
    C, _ = final_quad(auto.get(f, {}), ov, W, H)
    wid = (np.linalg.norm(C['tr'] - C['tl']) + np.linalg.norm(C['br'] - C['bl'])) / 2
    hei = (np.linalg.norm(C['bl'] - C['tl']) + np.linalg.norm(C['br'] - C['tr'])) / 2
    iw, ih = int(round(wid)), int(round(hei))
    M = cv2.getPerspectiveTransform(np.float32([C['tl'], C['tr'], C['br'], C['bl']]),
                                    np.float32([[0, 0], [iw, 0], [iw, ih], [0, ih]]))
    cv2.imwrite(os.path.join(out, f), cv2.warpPerspective(img, M, (iw, ih), flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE), [cv2.IMWRITE_JPEG_QUALITY, 93])
open(os.path.join(out, 'DONE'), 'w').close()
print(f'{len(rev)} pages written')
