#!/bin/bash
# deploy.sh, from the Mac: the Pages project (the pages.dev domain), its two secrets, the Groq key on
# the machine, and the deploy. The Cloudflare account token is read from the API folder (never
# printed); the door key from ~/.oci/teacher-door.json, the same key Caddy on the machine expects.
#   bash deploy.sh            deploy the files
#   bash deploy.sh secrets    set ORIGIN, DOOR_KEY and GOOGLE_MAPS_KEY on the project, then deploy (Marko runs this one:
#                             the permission gate refuses secret-store writes from a session)
#   bash deploy.sh key        put the Groq key on the machine (~/.shopfinder/groq_key) over ssh
#   bash deploy.sh machine    run install.sh on the machine over ssh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT=${PROJECT:-shopfinder}
ORIGIN=${ORIGIN:-https://130-61-181-83.sslip.io}
export CLOUDFLARE_ACCOUNT_ID=b9255970e1438e7e5c4446260c6a320d
export CLOUDFLARE_API_TOKEN=$(python3 -c "
import re,os; raw=open(os.path.expanduser('~/Downloads/API/Cloudflare.api.txt')).read(); print([l.strip() for l in raw.splitlines() if re.fullmatch(r'[A-Za-z0-9_\-]{30,}', l.strip())][-1])")

if [ "${1:-}" = "key" ]; then
  echo "== the Groq key to the machine (from ~/Downloads/API/groq-api.txt, never printed)"
  python3 -c "
import re,os; raw=open(os.path.expanduser('~/Downloads/API/groq-api.txt')).read(); print([l.strip() for l in raw.splitlines() if re.fullmatch(r'gsk_[A-Za-z0-9_\-]{20,}', l.strip())][-1], end='')" \
    | ssh teacher-vm 'mkdir -p ~/.shopfinder && umask 077 && cat > ~/.shopfinder/groq_key && wc -c < ~/.shopfinder/groq_key | xargs echo "bytes on the machine:"'
  exit 0
fi
if [ "${1:-}" = "machine" ]; then
  ssh teacher-vm 'bash -s' < "$HERE/install.sh"
  exit 0
fi

cd "$HERE"
echo "== the project $PROJECT"
npx --yes wrangler pages project list 2>/dev/null | grep -q " $PROJECT " || npx --yes wrangler pages project create "$PROJECT" --production-branch main
if [ "${1:-}" = "secrets" ]; then
  DOOR_KEY=$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('~/.oci/teacher-door.json')))['door_key'])")
  echo "== the secrets"
  printf '%s' "$ORIGIN"   | npx --yes wrangler pages secret put ORIGIN   --project-name "$PROJECT" >/dev/null
  printf '%s' "$DOOR_KEY" | npx --yes wrangler pages secret put DOOR_KEY --project-name "$PROJECT" >/dev/null
  GMAPS_KEY=$(python3 -c "
import re,os; raw=open(os.path.expanduser('~/Downloads/API/Google-maps-api.txt')).read(); m=re.findall(r'AIza[0-9A-Za-z_\-]{35}', raw); print(m[-1] if m else '', end='')")
  if [ -n "$GMAPS_KEY" ]; then
    printf '%s' "$GMAPS_KEY" | npx --yes wrangler pages secret put GOOGLE_MAPS_KEY --project-name "$PROJECT" >/dev/null
    echo "three secrets set: ORIGIN, DOOR_KEY, GOOGLE_MAPS_KEY (the paid map option)"
  else
    echo "two secrets set: ORIGIN, DOOR_KEY; no Google key found in ~/Downloads/API/Google-maps-api.txt, the page offers the free map only"
  fi
fi
echo "== the deploy"
npx --yes wrangler pages deploy public --project-name "$PROJECT" --branch main --commit-dirty=true 2>&1 | grep -E "Deploying|Uploading|https://|Success|error|Error" | head -6
echo "== the page"
sleep 5
curl -s -o /dev/null -w "https://$PROJECT.pages.dev/  -> %{http_code} (200, the app)\n" --max-time 25 "https://$PROJECT.pages.dev/"
curl -s --max-time 30 "https://$PROJECT.pages.dev/pools.json" | head -c 300; echo
