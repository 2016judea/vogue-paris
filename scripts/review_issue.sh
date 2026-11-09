#!/bin/sh
# Propose crops for one issue and render its review sheets. Prints the sheet paths.
# Usage: scripts/review_issue.sh <ark> <sheet_dir>
set -e
cd "$(dirname "$0")/.."
ARK=$1; OUT=$2; TMP=$(mktemp -d)
PAGES=$(node -e 'const u=require("./data/uploaded.json")["'$ARK'"];for(let n=u.first;n<=u.last;n++)console.log("p"+String(n).padStart(3,"0")+".jpg")')
mkdir -p data/crop_auto
if [ ! -f data/crop_auto/$ARK.json ]; then
  .venv/bin/python scripts/page_crop.py mirror-hi/$ARK $TMP $PAGES >/dev/null
  .venv/bin/python -c "import json,sys;m=json.load(open('$TMP/crop.json'));json.dump({k:{x:v[x] for x in ('ok','quad','why') if x in v} for k,v in m.items()},open('data/crop_auto/$ARK.json','w'),indent=0)"
fi
rm -rf $TMP
.venv/bin/python scripts/review_sheet.py $ARK $OUT
