#!/usr/bin/env python3
"""TEST 3 - the ugly cases. No terminal, a busy port, no git clone, GitHub unreachable, an update
offered and refused, a stray key after the refusal, a restart, a pool update in the way, the
terminal going away, Ctrl-C."""
import os
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import APP, PY, Console, check, finish, free_port, http, make_clone, bump_remote, git, wait_port  # noqa: E402

# ABSENT: no terminal (pipes, like systemd or nohup): it serves, says so, and Ctrl-C stops it
bare, work, clone = make_clone(version=1)
port = free_port()
p = subprocess.Popen([PY, os.path.join(clone, "serve.py")], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     env=dict(os.environ, PORT=str(port), HOST="127.0.0.1", PYTHONUNBUFFERED="1"), start_new_session=True)
check("no tty: the port answers", wait_port(port, 10))
os.killpg(os.getpgid(p.pid), signal.SIGINT)
try:
    out = p.communicate(timeout=8)[0].decode("utf-8", "replace")
except subprocess.TimeoutExpired:
    os.killpg(os.getpgid(p.pid), signal.SIGKILL); out = p.communicate()[0].decode("utf-8", "replace")
check("no tty: it said there are no keys", "no terminal: no keys" in out, out[-300:])
check("no tty: no key row was drawn", "q quit   o open page" not in out)
check("no tty: Ctrl-C stopped it and it said so", p.returncode == 0 and "stopped" in out, (p.returncode, out[-120:]))

# TWICE: the port is busy (another copy of this app): it says so and exits 1, the first keeps serving
c1 = Console(app_dir=clone)
check("first copy serves", wait_port(c1.port, 10))
c2 = Console(app_dir=clone, port=c1.port)
check("second copy on the same port says the port is taken", c2.wait_for("is taken", 10), c2.screen()[-200:])
check("and exits 1", c2.wait_exit(5) and c2.p.returncode == 1, c2.p.returncode)
check("the first copy is untouched", http("http://127.0.0.1:%d/health" % c1.port)[0] == 200)
c1.key("q"); c1.wait_exit(); c1.kill(); c2.kill()

# ABSENT: not a git clone: u says so plainly and keeps serving
nogit = clone + "-nogit"
shutil.copytree(clone, nogit, ignore=shutil.ignore_patterns(".git"))
c = Console(app_dir=nogit)
c.wait_for("q quit", 10)
c.key("u")
check("no .git: 'could not check ... not a git checkout'", c.wait_for("not a git checkout", 10), c.screen()[-300:])
check("no .git: still serving", http("http://127.0.0.1:%d/health" % c.port)[0] == 200)
c.key("q"); c.wait_exit(); c.kill()

# NEVER ANSWERS / ABSENT: GitHub unreachable: could not reach, still serving
git(clone, "remote", "set-url", "origin", "/nonexistent/origin.git")
c = Console(app_dir=clone)
c.wait_for("q quit", 10)
c.key("u")
check("unreachable origin: 'could not check: could not reach GitHub'", c.wait_for("could not reach GitHub", 15), c.screen()[-300:])
check("unreachable origin: still serving", http("http://127.0.0.1:%d/health" % c.port)[0] == 200)
c.key("q"); c.wait_exit(); c.kill()
git(clone, "remote", "set-url", "origin", bare)

# OUT OF ORDER: an update is offered, refused with n; a stray key after that is a command again
bump_remote(work, 2, "v2")
c = Console(app_dir=clone)
c.wait_for("q quit", 10)
c.key("u")
check("v2 available: the offer names both numbers", c.wait_for("v2 available", 15) and "v1 installed" in c.screen(), c.screen()[-300:])
check("and asks for y", "press y to update" in c.screen())
c.key("n")
check("n cancels", c.wait_for("update canceled", 5), c.screen()[-200:])
check("nothing was pulled", "APP_VERSION = 1" in open(os.path.join(clone, "version.py")).read())
c.key("o")
check("the next key is a command again (o opens)", c.wait_for("browser", 5), c.screen()[-200:])
# TWICE: u pressed again while the offer is open answers the offer (not a second check)
c.key("u"); c.wait_for("press y to update", 15)
before = c.screen().count("checking for an update")
c.key("u")
time.sleep(1.0)
check("u during the offer cancels it rather than starting a second check", "update canceled" in c.screen()[-200:] and c.screen().count("checking for an update") == before, c.screen()[-200:])
c.key("q"); c.wait_exit(); c.kill()

# r: restart on the same port, same pid, still serving
c = Console(app_dir=clone)
c.wait_for("q quit", 10)
pid = c.p.pid
c.key("r")
check("r says restarting", c.wait_for("restarting", 5))
c.buf = b""
check("after r the banner comes back", c.wait_for("q quit   o open page", 15), c.screen()[-300:])
check("after r the port answers", wait_port(c.port, 10))
check("same pid (exec, not a child)", c.p.pid == pid and c.alive())
c.key("q"); check("q after a restart stops it", c.wait_exit(8)); c.kill()
check("nothing left behind after the restart", c.left_behind() == [], c.left_behind())

# a pool update running: u and r are refused (the run must not be cut in half), q still works
slow = clone + "-slow"
subprocess.run(["git", "clone", "-q", bare, slow], check=True)     # not copytree: git's read-only objects refuse copystat here
with open(os.path.join(slow, "update_pools.py"), "w") as f:
    f.write("import time, sys\ntime.sleep(20)\nsys.exit(0)\n")
c = Console(app_dir=slow)
c.wait_for("q quit", 10)
st, body = http("http://127.0.0.1:%d/update" % c.port)
check("/update starts a run", st == 200 and b'"started": true' in body, body[:100])
c.key("u")
check("u during a pool update is refused with the reason", c.wait_for("a pool update is running", 5), c.screen()[-200:])
c.key("r")
check("r during a pool update is refused too", c.screen().count("a pool update is running") >= 1 and c.wait_for("a pool update is running", 5))
check("still serving", http("http://127.0.0.1:%d/health" % c.port)[0] == 200)
c.key("q")
check("q during a pool update still quits", c.wait_exit(8))
c.kill()

# the terminal goes away (SIGHUP on the pty): the process ends, nothing left behind
c = Console(app_dir=clone)
c.wait_for("q quit", 10)
os.killpg(c.pgid, signal.SIGHUP)
check("SIGHUP ends it", c.wait_exit(8))
c.kill()
check("SIGHUP leaves nothing", c.left_behind() == [], c.left_behind())

# Ctrl-C in the console. A typed \x03 on a pty that is not the controlling terminal raises no
# SIGINT (there is no foreground group to send it to), so send the signal a real terminal would.
c = Console(app_dir=clone)
c.wait_for("q quit", 10)
os.killpg(c.pgid, signal.SIGINT)
check("Ctrl-C in the console stops it", c.wait_exit(8) and "stopped." in c.screen(), c.screen()[-200:])
c.kill()

# the terminal is restored after q: cbreak off (echo and canonical mode back)
import termios
c = Console(app_dir=clone)
c.wait_for("q quit", 10)
mid = termios.tcgetattr(c.m)
c.key("q"); c.wait_exit(8)
after = termios.tcgetattr(c.m)
ICANON = termios.ICANON
check("cbreak was on while it ran", not (mid[3] & ICANON))
check("the terminal is restored on the way out", bool(after[3] & ICANON))
c.kill()

# update_pools.py with no key at all: exit 2 and a sentence naming the file
env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "GROQ_API_KEY")}
env["SHOPFINDER_DATA"] = slow
p = subprocess.run([PY, os.path.join(APP, "update_pools.py")], capture_output=True, text=True, env=env, timeout=30)
check("no key: exit 2 naming anthropic_key", p.returncode == 2 and "anthropic_key" in p.stdout, (p.returncode, p.stdout[-200:]))

# update_pools.py with a wrong key: the pool stays 'Unknown', the run completes, pools.json is written
import tempfile
d = tempfile.mkdtemp()
real = ""
try:
    import re
    real = re.findall(r"sk-ant-[A-Za-z0-9_\-]{20,}", open("/storage/emulated/0/Download/Api/Claude_api.txt").read())[-1]
except Exception:
    pass
if real:
    bad = real[:-4] + "xxxx"        # a real key with its last four characters changed: the shape is real, the rejection is real
    env2 = dict(env, ANTHROPIC_API_KEY=bad, POOLS_OUT=os.path.join(d, "pools.json"))
    p = subprocess.run([PY, "-c", "import update_pools as u, datetime; u.POOLS[:] = u.POOLS[:1]; u.main()"],
                       capture_output=True, text=True, env=env2, timeout=120, cwd=APP)
    check("a bad key: Claude's 401 is printed, the run completes", p.returncode == 0 and "401" in p.stdout and os.path.exists(os.path.join(d, "pools.json")), p.stdout[-300:])
    import json
    if os.path.exists(os.path.join(d, "pools.json")):
        j = json.load(open(os.path.join(d, "pools.json")))
        check("a bad key: the pool is Unknown with an empty week, not invented", j["pools"][0]["today_hours"] == "Unknown" and j["pools"][0]["week"] == [], j["pools"][0])
else:
    print("  skip  no Claude key file on this phone: the bad-key case not run")

finish("test3_ugly")
