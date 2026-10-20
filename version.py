"""
version.py  --  the single number everything else reads.

One whole number per modules/versioning.md: v1, v2, v3, never a dot. Every change, however small,
is a new number. Bumped by hand on every commit that touches this app (serve.py, console.py,
selfupdate.py, update_pools.py, public/index.html).

Kept in its own file so selfupdate.py can read it off origin/main with `git show` and compare it
with the one installed, without importing serve.py.

v1 is the first numbered version (13.9.2026): everything before it was the unnumbered 12.9.2026 app.
v2 (13.9.2026): the settings gear, the keys tested with the keyring's probes, the port picked when taken.
v3 (13.9.2026): the live port registry (portpick.announce, ports.md §3); the page opens in Chrome, bounded.
v4 (20.10.2026): the Bank pill: the nearest banks open at this hour (page v18).
v5 (20.10.2026): the free search no longer hangs: maps.mail.ru as a third Overpass server (asked twice), 30 s per server;
    Google's bank results leave out the ATMs (primaryType from serve.py).
"""

APP_VERSION = 5
