# Per-page crop review

Every page the site shows is checked by eye and cropped to the physical page, at
print grade (a Mixam order must show no scanner bed, gutter, binding strip or
neighbouring leaf, and must not lose any of this page). Aidan, 2026-11-08: *"we
need to be manually inspecting every page and custom cropping it."*

## Per issue

1. `scripts/review_issue.sh <ark> <sheet_dir>` proposes a crop for every page
   (data/crop_auto/<ark>.json) and prints the review sheet paths, 4 pages each.
2. Each page tile:
   - **left:** the whole scan; what the crop throws away is tinted magenta; cyan outline.
   - **right:** the four corners zoomed (top-left, top-right / bottom-left,
     bottom-right) from the **raw, untinted** scan, with the cyan crop line. Red
     ticks on each zoom's border = 5 thousandths of the scan; a long tick = 25.
3. Judge the corner zooms, not the tinted thumbnail. Aged paper is cream and the
   scanner bed is a cooler, brighter white; the gutter and binding are grey or
   dark. On 2026-11-09 the tint made a cream margin look like bed, and a whole
   cover's bottom margin got cut.
4. Write data/crop_review/<ark>.json, one key per page:
   - `"ok"` when the line already sits on the paper edge, or
   - `{"left": n, "right": n, "top": n, "bottom": n, "rot": deg}`, giving only
     what changes.

   The units:
   - **Sides:** in thousandths of the scan width (left/right) or height
     (top/bottom). **Positive moves that edge into the page; negative moves it
     out.** Count the ticks: 1 tick = 5.
   - **rot:** the crop's angle in degrees (+ = clockwise), given as an absolute
     value. The tile label shows the current one. Use it when the page edge and
     the line diverge along a side: for example, when the paper's left edge is
     further left at the bottom than at the top, and the right edge is too.
5. The crop is always a rectangle: a page is one. A worn edge that isn't straight
   gets a line a hair inside the paper. A hair of plain margin is invisible in
   print; a dark strip or white bed is not. Never cut printed matter that belongs
   to this page.
6. Re-render only the pages you changed to check them:
   `.venv/bin/python scripts/review_sheet.py <ark> <dir> p002.jpg p005.jpg`.
   The zoom windows re-centre on the new corners.
7. Write the review file after every sheet; it is resumable.

When every page shown on the site has an entry, scripts/sync.mjs re-cuts the
issue with scripts/apply_crop.py and re-uploads it.
