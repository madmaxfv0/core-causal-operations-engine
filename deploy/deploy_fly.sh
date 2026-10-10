#!/bin/sh
# Put CORE on a public link. Safe to run again to ship an update.
#
#   sh deploy/deploy_fly.sh              picks a name for you
#   sh deploy/deploy_fly.sh my-name      uses my-name (becomes my-name.fly.dev)
#
# Before the first run:  install flyctl, then `fly auth login`.
set -e
cd "$(dirname "$0")/.."
export PATH="$HOME/.fly/bin:$PATH"

command -v fly >/dev/null || { echo "flyctl is not installed: https://fly.io/docs/flyctl/install/"; exit 1; }
fly auth whoami >/dev/null 2>&1 || { echo "Not signed in. Run: fly auth login"; exit 1; }
[ -f frontend/dist/index.html ] || { echo "frontend/dist is missing: the built UI must be present."; exit 1; }
[ -d data/processed ] || { echo "data/processed is missing: run scripts/init_demo.py first."; exit 1; }

NAME="$1"
STATE=deploy/.app_name
[ -z "$NAME" ] && [ -f "$STATE" ] && NAME="$(cat $STATE)"

# `fly status` is the existence check: it does not depend on the layout of
# `fly apps list`, which changed between flyctl versions.
if [ -n "$NAME" ] && fly status -a "$NAME" >/dev/null 2>&1; then
  echo "== updating existing app $NAME"
else
  BASE="${NAME:-core-demo}"
  NAME=""
  for try in "$BASE" "$BASE-$(date +%s | tail -c 5)" "$BASE-$(date +%s | tail -c 5)x"; do
    if fly apps create "$try" >/dev/null 2>&1; then NAME="$try"; break; fi
    echo "name '$try' is taken, trying another"
  done
  [ -n "$NAME" ] || { echo "Could not create an app. Pass your own name: sh deploy/deploy_fly.sh my-core-name"; exit 1; }
  echo "== created app $NAME"
fi
echo "$NAME" > "$STATE"

fly deploy -a "$NAME" --ha=false --env CORE_PUBLIC_DEMO=1

echo
echo "CORE is live:  https://$NAME.fly.dev"
echo "The first visit after it has been idle takes about 40 seconds to wake."
