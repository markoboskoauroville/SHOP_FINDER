"""
version.py  --  the single number everything else reads.

One whole number per modules/versioning.md: v1, v2, v3, never a dot. Every change, however small,
is a new number. Bumped by hand on every commit that touches this app (serve.py, console.py,
selfupdate.py, update_pools.py, public/index.html).

Kept in its own file so selfupdate.py can read it off origin/main with `git show` and compare it
with the one installed, without importing serve.py.

v1 is the first numbered version (13.9.2026): everything before it was the unnumbered 12.9.2026 app.
"""

APP_VERSION = 1
