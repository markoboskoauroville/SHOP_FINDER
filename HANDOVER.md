# HANDOVER: SHOP_FINDER (12.9.2026, updated 13.9.2026)

## What it is

The Store & Pool Finder: a single page (`public/index.html`) that, from your position, lists the
nearest Spar, dm, bio&bio, Mlinar and malls with today's hours and a walking route, and the eight
Zagreb city pools with today's public-swim hours read from the official site. Written for Marko's
phone (a Termux server), moved on 12.9.2026 to the Oracle machine and to Cloudflare Pages.

## Where it runs

    https://shopfinder.pages.dev            the page, served by Cloudflare (static, always up)
      /pools.json /update /health           relayed by functions/_middleware.js to the machine,
      /config.js /places /gtile/...         no secret in the function: the machine's public name only
         -> https://130-61-181-83.sslip.io/shopfinder/...   Caddy on the machine; this path needs no
                                            door key (a public app), the portal's paths still do
            -> 127.0.0.1:8900               shopfinder.service: serve.py (PREFIX=/shopfinder)
                                            data in /home/ubuntu/.shopfinder: pools.json, groq_key,
                                            google_maps_key (0600)

**The secrets live on the machine, and only there** (Marko, 12.9.2026, after the first version put the
Google key into the page: "modify my app so the secrets are living on my server, not in the web
page"). The page holds no key and asks its own origin for everything; the machine's server makes the
Google calls (`/places` for Places API text search, `/gtile/z/x/y.png` for Google's map tiles through
the Map Tiles API) with the key from its file, and answers `config.js` with only `{google: true|false,
googleTiles: true|false}`. Nothing is stored on Cloudflare: no Pages secret, no key in the function.

The machine sleeps when Marko puts it to sleep (the door's power switch at ttt-lll.pages.dev/machine).
Asleep, the page still opens: the pools show without hours in free mode, with Google hours in paid
mode, and the status says to wake the machine. Nothing breaks.

GitHub is the hub: https://github.com/markoboskoauroville/SHOP_FINDER. A push is on the machine
within a minute (`shopfinder-update.timer` pulls and restarts the service). The page itself is
deployed by `bash deploy.sh` from the Mac (wrangler through npx).

## The machine (Ubuntu, Python 3.12, no venv needed)

    systemctl status shopfinder                 the server
    systemctl list-timers | grep shopfinder     the GitHub check (1 min) and the pool timer (06:15 Zagreb, and 5 min after boot)
    journalctl -u shopfinder-pools -n 30        the last timer run (the button's runs log to journalctl -u shopfinder)
    curl -s http://127.0.0.1:8900/shopfinder/health
    cat /home/ubuntu/.shopfinder/pools.json

Caddy's route (`/shopfinder` -> 8900) is in `/etc/caddy/Caddyfile` and in its source of truth,
`ABLETON_TEACHER/oracle/second.sh` (a rerun of that script keeps it).

To install again from nothing: `bash deploy.sh machine` (runs install.sh over ssh), then
`bash deploy.sh key`.

## The secrets, and where they live

    Groq key              ~/Downloads/API/groq-api.txt on the Mac; /home/ubuntu/.shopfinder/groq_key
                          on the machine (bash deploy.sh key writes both keys; 0600; never in the repo)
    Google Maps key       ~/Downloads/API/Google-maps-api.txt on the Mac; /home/ubuntu/.shopfinder/
                          google_maps_key on the machine. Used only by serve.py there. In the Google
                          Cloud console restrict it as a SERVER key: by IP address 130.61.181.83 (an
                          HTTP-referrer restriction would refuse the machine's calls), APIs: Places API
                          (New) and, for Google's own map tiles, Map Tiles API. On a phone or a Mac:
                          env GOOGLE_MAPS_KEY, or the file google_maps_key in the data folder.
    Cloudflare token      ~/Downloads/API/Cloudflare.api.txt (deploy.sh reads it for the deploy, never prints it)
    door key              not used by this app since 12.9.2026 (Caddy passes /shopfinder without it)

Nothing on Cloudflare. `bash deploy.sh key` is the only key step, from the Mac, over ssh.

## What is paid, what is free

Free mode (the default, "OSM · free", green): OpenStreetMap tiles through Leaflet (cdnjs),
Overpass API (overpass-api.de, then overpass.kumi.systems) for the shops and their `opening_hours`
tag, read by a small parser in the page (Mo-Fr/Sa/Su/PH rules, two ranges, over midnight, 24/7;
an unreadable value is shown raw as "hours unknown"), OSRM at routing.openstreetmap.de for the walk.
The pool hours come from pools.json, which the machine produces with one Groq call per pool
(Groq's free tier: `openai/gpt-oss-120b`, then gpt-oss-20b, qwen3.8-27b, whichever answers; the
old llama-3.3-70b was retired), one pool at a time with only the hours-related part of each page
(a few thousand tokens a minute is the whole allowance, eight whole pages at once got 429), eight a
day plus the refresh button, never more than once in ten minutes. A run takes one to three minutes;
the button starts it and the page polls /health until pools.json is rewritten.

Paid mode ("Google · paid", orange): Places API (New) text search per brand query and, when
pools.json is not there, per pool, all made by the machine; Google's map tiles through the Map
Tiles API, fetched by the machine (`/gtile/...`), when that API is enabled on the key, otherwise the
OSM tiles with Google's data ("Google data · paid"). Each call is billed to the key on the machine.
Because the addresses are public, serve.py limits them: per address 40 searches and 1500 tiles in
ten minutes, per day 600 searches and 15,000 tiles (PLACES_PER_10MIN, TILES_PER_10MIN,
PLACES_DAILY_CAP, TILES_DAILY_CAP in the service); over the limit the page says so. The choice is
remembered in the browser (localStorage sf_maps).

## Decisions of 12.9.2026

- **Static page on Pages, data from the machine.** Marko asked for the app on Oracle with a
  pages.dev domain. The page is served by Cloudflare so it opens in a moment and stays up while the
  machine sleeps; only the two data addresses go to the machine, through the same door key the
  portal uses. Its own Pages project (`shopfinder`), not behind the portal's login: a finder is public.
- **The keys left the code, then the page.** The Termux version had the Groq key hardcoded and the
  Google key in the page; the first deploy of the day served the Google key from a Pages secret; the
  same afternoon Marko asked for the secrets on his server only, so the machine makes every Google
  call and the page never sees a key. The Pages Function holds nothing but the machine's name. Now: env, or a `groq_key`
  file in the data folder, ignored by git. Groq's edge answers 403 to Python's bare User-Agent, so
  the updater names itself (`shopfinder-pools/1.0`).
- **Eight pools, corrected.** The list had five, two with the wrong official link (a generic
  "Bazeni" page) and positions off by up to 1.5 km (Utrina, Šalata, both Mladost pools). Now the
  eight the city runs, with the address from each official page and the position from OpenStreetMap:
  Špansko (new, 9.9.2026), Bazeni Mladost outdoor, Zimsko plivalište Mladost (Trg Krešimira Ćosića,
  not Jarun), Utrina, Šalata, Svetice, Jelkovec, Iver.
- **Free and paid map, both complete.** Marko's rule, the same day, for every app with a map.
- **The refresh button is public** (anyone with the URL). serve.py refuses a second run within ten
  minutes and runs one at a time; the timer refreshes every morning anyway.

## 13.9.2026: the console, mapool, the week, the visits, Claude Haiku

Marko, in one morning: "Q as a quit key, U as update key, the same as my other Termux apps";
the street and the B/N distances in every shop title; "you always need to use Haiku to actually
scrape the working hours", a compact weekly list, Špansko first, a visit counter with hours, km,
laps and money and monthly/yearly reports; and "mapool, build this as a global run command".

- **The console is console.py**, the shape of MAHA_TRANSCRIBE_TERMUX_TERMINAL/console.py (and
  GOOGLE_TTS_STT, MAHA_COMMUTE): plain lines, never a box; `q quit  o open page  u check for
  update  r restart`; U checks first and shows both numbers, then asks for y; the restart is an
  execv on the main thread (same pid, same port). selfupdate.py reads version.py off origin/main;
  version.py holds one whole number (modules/versioning.md), v1 on 13.9.2026. serve.py stays
  standard library; the http.server runs in a daemon thread while the main thread reads keys.
  `is_interactive()` treats "no controlling terminal" (ENOTTY from tcgetpgrp) as interactive: a
  pty from a harness cannot SIGTTIN the process, only a real background job can.
- **mapool** replaces shopfinder-v1.sh (the nohup menu). `mapool install` writes a wrapper into
  $PREFIX/bin and ~/.local/bin (a wrapper, not a symlink: the repo is on the sdcard, mounted
  noexec). On this phone the clone is
  `~/storage/downloads/claudecode/poolandshopfinder/SHOP_FINDER`.
- **Claude Haiku** (`claude-haiku-4-5`, raw Messages API through urllib, no package) reads each
  pool's own text (the site's shared lines removed as before) and answers today's ranges, the week
  as `[{days, hours}]`, a notice. Measured 13.9.2026: eight pools in about a minute, the week on
  four of them (the others were closed: Šalata's season ended that day, Svetice a technical
  fault, Zimsko plivalište Mladost closed since March, Utrina a heating cut until 19.9); Iver
  timed out once on the site's side, so fetch_page tries three times. Groq is the fallback when
  there is no Anthropic key. The key: `~/.shopfinder/anthropic_key` on the machine (deploy.sh key
  reads `~/Downloads/API/[Cc]laude*.txt` on the Mac); on the phone mapool passes it in the
  environment from `~/storage/downloads/Api/Claude_api.txt`.
- **The visit log is in the browser** (localStorage `sf_visits`), not on the machine: the
  machine's addresses are public behind pages.dev and a public counter would be anyone's. Copy /
  paste moves it between phones. Sorting: visits desc, then Špansko, then distance.
- **The four tests** are in tests/ (`python3 tests/run_all.py`, about four minutes on the phone):
  test1 the mechanism (selfupdate against a bare repo, week_list, the page's arithmetic in node),
  test2 the running app on a pty (banner, keys, a stand-in termux-open-url, q leaves nothing),
  test3 the ugly cases (no tty, a busy port, no .git, GitHub unreachable, n, a stray key, r, a pool
  update in the way, SIGHUP, Ctrl-C, the terminal restored, no key, a wrong key against the real
  API), test4 the upgrade (v1 running with its pools.json, v2 lands, u, y: v2 on the same port and
  pid, the data untouched, idempotent). Not tested: the page in a browser (code inspection and
  node on its functions only), Termux:Boot, the machine's systemd path.

## 13.9.2026, later: v2 of the server, v17 of the page

- **The settings gear** (Marko: "add a settings gear to this app; file pick the API keys and test
  them; check my API Key Tester application and use their code"): serve.py answers
  `/settings/state`, `/settings/import` (POST, the picked file's text) and `/settings/test?provider=`
  only to a request made on the same machine with no proxy header; through Caddy or the pages.dev
  door they are 404. The probes are `probes.py`, the exact file of KEYRING_TERMUX with a header
  saying so (fix it there, copy it back). The keys go to the data folder as 0600 files, written
  beside their name and renamed over.
- **The keys are in the app folder on the phone** (`google_maps_key`, `anthropic_key`, 0600,
  ignored by git) because Marko asked for them in the installation directory; the same keys are in
  the keyring (`keyring get google`, `keyring get anthropic`), which serve.py and update_pools.py
  ask when neither the environment nor the file has one.
- **portpick.py** (from KEYRING_TERMUX, from Maha Transcribe): the app never fails to start on
  the phone; with PREFIX it still refuses, for systemd.
- **The four tests grew** (36 + 22 + 46 + 16 checks): the gear's three addresses, local and through
  a proxy, a picked file of the right shapes written 0600, a test with a key of the right shape
  that Google rejects for real, the second copy moving to the next port, and the no-key case run
  against the clone (the app folder itself holds the real key files now; the first version of that
  test found them and ran a whole Haiku update inside a test).

## Still to do

- Restrict the Google key by IP to the machine and by API (Places API (New), Map Tiles API) in the
  Google Cloud console; enable the Map Tiles API there if Google's own tiles are wanted in paid mode
  (config.js reports googleTiles:false until it works; the journal says why).
- The old Termux:Boot script on the phone (~/.termux/boot/start-server.sh) still points at the old
  five-pool copy in ~/storage/downloads/webserver; `mapool boot` writes the new one, then delete the old.
- Put the Anthropic key on the machine (`bash deploy.sh key` from the Mac) so the morning timer uses
  Haiku; until then it falls back to Groq and pools.json has no week.
- Overpass has no opening hours for some shops (they stay listed as "hours unknown" under Today);
  Google knows more. That is the trade of the free option.
