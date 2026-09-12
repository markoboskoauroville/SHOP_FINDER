#!/bin/bash
# deploy.sh, from the Mac: the Pages project (the pages.dev domain) and the deploy, the keys to the
# machine. NO SECRETS ON CLOUDFLARE (Marko, 12.9.2026: "the secrets are living on my server, not in
# the web page"): the Groq key and the Google key live in /home/ubuntu/.shopfinder on the machine,
# written over ssh from the API folder, never printed, never in the repo. The Cloudflare account
# token is read from the API folder for the deploy only.
#   bash deploy.sh            deploy the page
#   bash deploy.sh key        put the Groq key and the Google key on the machine (~/.shopfinder/)
#   bash deploy.sh machine    run install.sh on the machine over ssh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT=${PROJECT:-shopfinder}

if [ "${1:-}" = "key" ]; then
  echo "== the keys to the machine (from ~/Downloads/API, never printed)"
  python3 - <<'KEYS' | ssh teacher-vm 'mkdir -p ~/.shopfinder && umask 077 && cd ~/.shopfinder && python3 -c "
import sys
for line in sys.stdin:
    name, value = line.rstrip(\"\\n\").split(\" \", 1)
    open(name, \"w\").write(value)
    print(name + \": \" + str(len(value)) + \" bytes on the machine\")
"; sudo systemctl restart shopfinder 2>/dev/null || true'
import re, os
raw = open(os.path.expanduser('~/Downloads/API/groq-api.txt')).read()
g = [l.strip() for l in raw.splitlines() if re.fullmatch(r'gsk_[A-Za-z0-9_\-]{20,}', l.strip())]
if g: print('groq_key ' + g[-1])
raw = open(os.path.expanduser('~/Downloads/API/Google-maps-api.txt')).read()
m = re.findall(r'AIza[0-9A-Za-z_\-]{35}', raw)
if m: print('google_maps_key ' + m[-1])
KEYS
  exit 0
fi
if [ "${1:-}" = "machine" ]; then
  ssh teacher-vm 'bash -s' < "$HERE/install.sh"
  exit 0
fi

export CLOUDFLARE_ACCOUNT_ID=b9255970e1438e7e5c4446260c6a320d
export CLOUDFLARE_API_TOKEN=$(python3 -c "
import re,os; raw=open(os.path.expanduser('~/Downloads/API/Cloudflare.api.txt')).read(); print([l.strip() for l in raw.splitlines() if re.fullmatch(r'[A-Za-z0-9_\-]{30,}', l.strip())][-1])")
cd "$HERE"
echo "== the project $PROJECT"
npx --yes wrangler pages project list 2>/dev/null | grep -q " $PROJECT " || npx --yes wrangler pages project create "$PROJECT" --production-branch main
echo "== the deploy"
npx --yes wrangler pages deploy public --project-name "$PROJECT" --branch main --commit-dirty=true 2>&1 | grep -E "Deploying|Uploading|https://|Success|error|Error" | head -6
echo "== the page"
sleep 5
curl -s -o /dev/null -w "https://$PROJECT.pages.dev/  -> %{http_code} (200, the app)\n" --max-time 25 "https://$PROJECT.pages.dev/"
curl -s --max-time 30 "https://$PROJECT.pages.dev/config.js"; echo "   (google true when the key is on the machine)"
curl -s --max-time 30 "https://$PROJECT.pages.dev/pools.json" | head -c 200; echo
