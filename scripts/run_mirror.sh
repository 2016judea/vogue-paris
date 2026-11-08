#!/bin/zsh
# Launch headless Chrome (normal UA) on a Gallica tab, then run mirror.js. Restarts on crash.
cd "$(dirname $0)/.."
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
PROFILE=/private/tmp/vogue-mirror-chrome
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  PORT=$((9300+attempt))
  rm -rf $PROFILE; mkdir -p $PROFILE
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --user-agent="$UA" --remote-debugging-port=$PORT --user-data-dir=$PROFILE --no-first-run --no-default-browser-check "https://gallica.bnf.fr/services/Issues?ark=ark:/12148/cb343833568/date" >/dev/null 2>&1 &
  sleep 8
  NODE_PATH=$HOME/.claude/skills/lomo-likes/scripts/node_modules WIDTH=2400 node scripts/mirror.js $PORT data/issues_seed.json mirror-hi && { pkill -f "remote-debugging-port=$PORT"; rm -rf $PROFILE; exit 0; }
  pkill -f "remote-debugging-port=$PORT"; sleep 60
done
