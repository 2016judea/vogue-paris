"""Draw detected page quads over a scan: segment = green, rect = blue. Debug aid."""
import sys, json, subprocess, cv2, numpy as np
src, dst = sys.argv[1], sys.argv[2]
img = cv2.imread(src); h, w = img.shape[:2]
out = subprocess.run(['bin/pagequad', src], capture_output=True, text=True).stdout.split('\n')
for line in out:
    if not line.startswith('{'): continue
    d = json.loads(line)
    pts = np.array([[d[k][0] * w, d[k][1] * h] for k in ('tl', 'tr', 'br', 'bl')], np.int32)
    col = (0, 200, 0) if d['kind'] == 'segment' else (220, 80, 0)
    cv2.polylines(img, [pts], True, col, 6)
s = 900 / h
cv2.imwrite(dst, cv2.resize(img, (int(w * s), 900)))
