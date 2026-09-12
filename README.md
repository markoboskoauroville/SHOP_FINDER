# SHOP_FINDER, the Store & Pool Finder

One page that finds the nearest Spar, dm, bio&bio, Mlinar or mall around you, and shows the eight
Zagreb city pools with today's public-swim hours. It lives at **https://shopfinder.pages.dev**
(Cloudflare Pages, free) and on the free Oracle machine, where a small Python server reads the
official pool pages every morning.

**Two map options, always** (Marko, 12.9.2026): the toggle next to *Today*.

| | free: **OSM** (default) | paid: **Google** |
|---|---|---|
| map | OpenStreetMap tiles, Leaflet | Maps JavaScript API |
| the shops and their hours | Overpass API, the `opening_hours` tag | Places API text search |
| pool hours without pools.json | not loaded, the official link | Places API |
| walking route | OSRM on OpenStreetMap | OSRM on OpenStreetMap |
| bill | nothing | every call against the key (config.js, from a Pages secret) |

**The pools** (Upravljanje sportskim objektima, links checked 12.9.2026): Bazen Špansko (opened
9.9.2026, west), Bazeni Mladost outdoor, Zimsko plivalište Mladost, Utrina, Šalata, Svetice, Jelkovec,
Iver. The list is in `public/index.html` and again in `update_pools.py`; change both.

## The files

    public/index.html        the app, one file, no build
    public/_headers          no-store for pools.json and /update on Pages
    (config.js)              not a file: the Pages Function or serve.py answers it with the Google key
    functions/_middleware.js the Pages Function: relays /pools.json and /update to the machine with the door key
    serve.py                 the server: the page, pools.json, /update, /health; standard library
    update_pools.py          the official pages through Groq -> pools.json (key: SHOPFINDER_DATA/groq_key)
    install.sh               ON the machine: shopfinder.service (:8900, /shopfinder), the GitHub updater
                             every minute, the pool timer at 06:15 Zagreb
    deploy.sh                from the Mac: the Pages project and its secrets, the Groq key to the machine
    shopfinder-v1.sh         the Termux menu for a phone (start, stop, log, boot)
    HANDOVER.md              the whole story: where it runs, the secrets, what is paid, what was decided

## Run it anywhere

    python3 serve.py            # http://localhost:8080
    python3 update_pools.py     # writes pools.json next to it (needs a Groq key, see the handover)

## Deploy

    git push                    # the machine pulls within a minute and restarts the service
    bash deploy.sh              # the page to shopfinder.pages.dev
