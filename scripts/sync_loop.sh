#!/bin/zsh
# Upload finished issues and redeploy, every 15 minutes, until the mirror is done.
cd "$(dirname $0)/.."
set -a; source ~/Desktop/workspace/bricks/.env; set +a
while true; do
  before=$(shasum public/data/issues.json 2>/dev/null)
  node scripts/sync.mjs
  if [ "$before" != "$(shasum public/data/issues.json)" ]; then
    npx -y vercel@latest deploy --prod --yes --token "$VERCEL_TOKEN" >/dev/null 2>&1 && echo "$(date) deployed"
    git add -A public data scripts && git commit -qm "Sync: $(python3 -c "import json;print(sum(x['ready'] for x in json.load(open('public/data/issues.json'))))") of 231 issues readable" && git push -q
  fi
  grep -q "ALL DONE" mirror.log && [ -z "$(node -e "const s=require('./data/issues_seed.json'),u=require('./data/uploaded.json');console.log(s.filter(x=>!u[x.ark]).length||'')")" ] && { echo "$(date) finished"; exit 0; }
  sleep 900
done
