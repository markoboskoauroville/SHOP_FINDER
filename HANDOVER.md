# HANDOVER: SHOP_FINDER (12.9.2026)

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

## Still to do

- Restrict the Google key by IP to the machine and by API (Places API (New), Map Tiles API) in the
  Google Cloud console; enable the Map Tiles API there if Google's own tiles are wanted in paid mode
  (config.js reports googleTiles:false until it works; the journal says why).
- The Termux copy on the phone still runs the old five-pool version at ~/storage/downloads/webserver;
  copy this repo to ~/storage/downloads/SHOP_FINDER and run shopfinder-v1.sh, or just open
  shopfinder.pages.dev.
- Overpass has no opening hours for some shops (they stay listed as "hours unknown" under Today);
  Google knows more. That is the trade of the free option.
