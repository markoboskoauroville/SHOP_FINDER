#!/usr/bin/env python3
"""TEST 4 - the upgrade, from the version before, over a running copy with its data.
v1 runs (the real launcher path: python3 serve.py in the clone, on a pty), has a pools.json in
its data folder and a visit log is not on the server (it lives in the browser: nothing to check
there). v2 lands on 'GitHub'. Press u, read the offer, press y: v2 must be serving on the same
port, in the same process, with the same pools.json, and a second u must say v2 is the latest."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Console, check, finish, http, make_clone, bump_remote, wait_port  # noqa: E402

bare, work, clone = make_clone(version=1)
data = tempfile.mkdtemp(prefix="mapool-data-")
pools = {"updated": "2026-09-13T09:05+02:00", "source": "test", "pools": [
    {"id": "pool-spansko", "name": "Bazen Špansko", "addr": "x", "lat": 45.7974, "lng": 15.90475, "url": "u",
     "open_now": True, "today_hours": "08:00-20:00", "week": [{"days": "Mon-Fri", "hours": "06:30-21:30"}], "notice": ""}]}
with open(os.path.join(data, "pools.json"), "w") as f:
    json.dump(pools, f)

c = Console(app_dir=clone, data_dir=data)
check("v1 runs and says version 1", c.wait_for("version 1", 10), c.screen()[-300:])
check("v1 has no idea of v2 yet (assert the old is old)", "APP_VERSION = 1" in open(os.path.join(clone, "version.py")).read())
check("v1 serves the data", wait_port(c.port, 10) and b"Mon-Fri" in http("http://127.0.0.1:%d/pools.json" % c.port)[1])
pid = c.p.pid

bump_remote(work, 2, "v2")

c.key("u")
check("u offers v1 -> v2", c.wait_for("v2 available", 20) and "v1 installed" in c.screen(), c.screen()[-300:])
c.key("y")
check("y pulls and announces the restart", c.wait_for("updated to v2, restarting", 30), c.screen()[-300:])
c.buf = b""
check("the new banner says version 2", c.wait_for("version 2", 20), c.screen()[-300:])
check("the key row is back", c.wait_for("q quit   o open page", 5))
check("the same port answers", wait_port(c.port, 10))
check("the same process (exec), not a child beside the old one", c.p.pid == pid and c.alive())
check("the working tree is v2", "APP_VERSION = 2" in open(os.path.join(clone, "version.py")).read())
st, body = http("http://127.0.0.1:%d/pools.json" % c.port)
check("the old pools.json is still served by the new code", st == 200 and json.loads(body)["pools"][0]["week"][0]["days"] == "Mon-Fri")
check("the data folder is untouched", sorted(os.listdir(data)) == ["pools.json"], os.listdir(data))

c.key("u")
check("a second u says v2 is the latest", c.wait_for("v2 is already the latest version", 20), c.screen()[-200:])
c.key("q")
check("q stops v2", c.wait_exit(8))
check("nothing left behind", c.left_behind() == [], c.left_behind())
c.kill()

# doing it again changes nothing: v2 clone, v2 on origin
c = Console(app_dir=clone, data_dir=data)
c.wait_for("q quit", 10)
c.key("u")
check("idempotent: up to date, no restart", c.wait_for("already the latest", 20) and c.alive())
c.key("q"); c.wait_exit(8); c.kill()

finish("test4_upgrade")
