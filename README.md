# SHOP_FINDER, the Store & Pool Finder

One page that finds the nearest Spar, dm, bio&bio, Mlinar or mall around you, and shows the eight
Zagreb city pools with today's public-swim hours. It lives at **https://shopfinder.pages.dev**
(Cloudflare Pages, free) and on the free Oracle machine, where a small Python server reads the
official pool pages every morning.

**Two map options, always** (Marko, 12.9.2026): the toggle next to *Today*.

| | free: **OSM** (default) | paid: **Google** |
|---|---|---|
| map | OpenStreetMap tiles, Leaflet | Google's tiles through the machine (Map Tiles API), else OSM tiles |
| the shops and their hours | Overpass API, the `opening_hours` tag | Places API text search, made by the machine |
| pool hours without pools.json | not loaded, the official link | Places API |
| walking route | OSRM on OpenStreetMap | OSRM on OpenStreetMap |
| bill | nothing | every call against the key, which lives on the machine only |

**The pools** (Upravljanje sportskim objektima, links checked 12.9.2026): Bazen Špansko (opened
9.9.2026, west), Bazeni Mladost outdoor, Zimsko plivalište Mladost, Utrina, Šalata, Svetice, Jelkovec,
Iver. The list is in `public/index.html` and again in `update_pools.py`; change both.

## How to install (Termux)

    curl -fsSL https://raw.githubusercontent.com/markoboskoauroville/SHOP_FINDER/main/install-termux.sh | bash

One line, no token: the repository is public and holds no key. It clones to
`~/SHOP_FINDER`, puts `mapool` on the PATH, and says what to do next. Keys come from the
keyring (`keyring get anthropic`, `keyring get google`) or from the ⚙ gear on the page.

## On the phone: `mapool`

    mapool             start the server, the page opens; the console has the keys every app here has:
                         q quit   o open page   u check for update   r restart
    mapool update      pull the newest version from GitHub and exit (u does it live, with a y to confirm)
    mapool boot        start at boot (Termux:Boot), no console
    mapool install     put the command on the PATH (once, after the clone)

The U key fetches GitHub, shows the installed and the available version (`version.py`, one whole
number), asks for `y`, pulls with `--ff-only` and restarts itself on the same port. Without a
terminal (systemd on the machine, nohup, a pipe) there are no keys: it serves, Ctrl-C stops it.

## The settings gear (v17)

⚙ at the far end of the controls row. On the machine the page runs on (a phone, a Mac) it shows
which keys the server holds (Google Maps, Anthropic, Groq) and where from (environment, a 0600
file in the data folder, or the keyring), a **choose a key file …** picker that stores the keys
found by shape, and a **test** per key that asks the provider for the smallest real thing it sells
with the keyring's probes (`probes.py`, vendored from KEYRING_TERMUX). A Google key restricted to
Places says `works for Places: Places ✓ · Tiles not enabled · Geocoding ✗`. Behind the pages.dev
door the settings addresses answer 404 and the panel says the keys live on the machine.

The server never fails to start because a port is taken (`portpick.py`): 8080, then the next
fifteen, then any, and the banner says which. On the machine (PREFIX set) a taken port is an error
for systemd, never a move, because Caddy routes to one number.

## The page (v16, 13.9.2026)

- **Shops**: the title carries the street and, in parentheses, the km from **B**ritish Square and
  from **N**ova TV: `Spar · Ilica 12 (B 0.4 · N 7.1)`.
- **Pools**: the week for the general public as one compact line per pool (`Mon-Fri 06:30-21:30 ·
  Sat-Sun 08:00-20:00 · Holidays 12:00-20:00`), read from the official pages by **Claude Haiku**
  (`update_pools.py`, the key on the machine). Bazen Špansko comes first; a pool with more visits
  comes before it.
- **Visits**: `Visited ✓` on a pool counts a visit; `stats` opens the log where each visit takes
  hours, km, laps and €, with this month / this year / all time, by month and by year; 📊 next to
  the Pools pill is the same for all pools together. The log lives in the browser (localStorage
  `sf_visits`); *copy the whole log* / *paste a log in* moves it to another phone.

## The files

    public/index.html        the app, one file, no build
    public/_headers          no-store for pools.json and /update on Pages
    (config.js)              not a file: serve.py answers it with {google, googleTiles}, never a key
    functions/_middleware.js the Pages Function: relays the data addresses to the machine; no secret in it
    serve.py                 the server: the page, pools.json, /update, /health, /places and /gtile (Google, with
                             the key on the machine), /config.js; standard library
    console.py               the terminal side: banner, q/o/u/r, the update offer (the shape of Maha Transcribe's)
    selfupdate.py            the U key: version.py here against origin/main, git pull --ff-only
    version.py               APP_VERSION, one whole number, bumped on every change
    update_pools.py          the official pages through Claude Haiku (Groq as the fallback) -> pools.json:
                             today's hours, the week, a notice (key: SHOPFINDER_DATA/anthropic_key)
    mapool                   the phone command (run, update, boot, install, where)
    install.sh               ON the machine: shopfinder.service (:8900, /shopfinder), the GitHub updater
                             every minute, the pool timer at 06:15 Zagreb
    deploy.sh                from the Mac: the Pages deploy; `key` puts the Anthropic, Groq and Google keys on the machine
    tests/                   the four tests (python3 tests/run_all.py): the mechanism, the running app on a
                             pty, the ugly cases, the upgrade over a running v1
    HANDOVER.md              the whole story: where it runs, the secrets, what is paid, what was decided

## Run it anywhere

    python3 serve.py            # http://localhost:8080, the console when in a terminal
    python3 update_pools.py     # writes pools.json next to it (needs the Anthropic key, see the handover)

The keys live on the machine (`~/.shopfinder/anthropic_key`, `groq_key`, `google_maps_key`), never
in the page, the repo, or Cloudflare. `bash deploy.sh key` puts them there from the Mac. On the
phone, `mapool` hands the key from `~/storage/downloads/Api/Claude_api.txt` to the updater in the
environment, without copying it.

## Deploy

    git push                    # the machine pulls within a minute and restarts the service
    bash deploy.sh              # the page to shopfinder.pages.dev
