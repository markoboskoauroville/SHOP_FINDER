#!/usr/bin/env python3
"""TEST 2 - inside the running app, driven the way a person drives it: keys on a real pty, the
real serve.py, the real port, a real origin (a bare repo with the same version), a stand-in
termux-open-url that records what it was asked to open."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Console, check, finish, http, make_clone, stub_bin, wait_port  # noqa: E402

bare, work, clone = make_clone(version=1)
stub, rec = stub_bin()
c = Console(app_dir=clone, env={"PATH": stub + os.pathsep + os.environ["PATH"]})
try:
    check("the banner names the app and the address", c.wait_for("Shop & Pool Finder", 10) and ("http://localhost:%d/" % c.port) in c.screen(), c.screen()[-300:])
    check("the banner says the version", "version 1" in c.read(0.5))
    check("the key row is the one every app here has", "q quit   o open page   u check for update   r restart" in c.screen(), c.screen()[-200:])
    check("the port answers while the console waits for keys", wait_port(c.port, 10))
    st, body = http("http://127.0.0.1:%d/" % c.port)
    check("the page is served", st == 200 and b"Store & Pool Finder" in body, st)
    st, body = http("http://127.0.0.1:%d/health" % c.port)
    check("/health answers", st == 200 and b'"ok": true' in body, body[:80])

    c.key("o")
    check("o says it opens the browser", c.wait_for("opening the browser", 5), c.screen()[-200:])
    import time
    time.sleep(0.8)
    opened = open(rec).read().strip() if os.path.exists(rec) else ""
    check("the stand-in opener was handed the served address", opened == "http://localhost:%d/" % c.port, opened)

    c.key("u")
    check("u checks and reports the latest version", c.wait_for("v1 is already the latest version", 20), c.screen()[-300:])
    check("the server kept serving through the check", http("http://127.0.0.1:%d/health" % c.port)[0] == 200)

    c.key("x")
    check("an unknown key changes nothing", c.alive() and http("http://127.0.0.1:%d/health" % c.port)[0] == 200)

    c.key("q")
    check("q stops it", c.wait_exit(8), c.screen()[-200:])
    check("it says stopped", "stopped." in c.screen())
    check("the port is free again", http("http://127.0.0.1:%d/health" % c.port, 2)[0] is None)
    check("nothing left behind", c.left_behind() == [], c.left_behind())
finally:
    c.kill()

# the same, through the mapool command (the launcher gives the console its terminal)
c = Console(app_dir=clone, env={"PATH": stub + os.pathsep + os.environ["PATH"]})
c.kill()
import subprocess
import pty
import fcntl
import struct
import termios
m, s = pty.openpty()
fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 100, 0, 0))
port = c.port
p = subprocess.Popen(["bash", os.path.join(clone, "mapool")], stdin=s, stdout=s, stderr=s, close_fds=True,
                     env=dict(os.environ, PORT=str(port), HOST="127.0.0.1", TERM="xterm-256color", PATH=stub + os.pathsep + os.environ["PATH"]), start_new_session=True)
os.close(s)
c2 = Console.__new__(Console); c2.m = m; c2.p = p; c2.port = port; c2.buf = b""; c2.pgid = os.getpgid(p.pid)
try:
    check("mapool starts the console", c2.wait_for("q quit   o open page", 10), c2.screen()[-200:])
    check("mapool serves the port", wait_port(port, 10))
    c2.key("q")
    check("q through mapool stops it", c2.wait_exit(8))
    check("nothing left behind after mapool", c2.left_behind() == [], c2.left_behind())
finally:
    c2.kill()

p = subprocess.run(["bash", os.path.join(clone, "mapool"), "where"], capture_output=True, text=True, timeout=20)
check("mapool where prints the folder and v1", clone in p.stdout and "v1" in p.stdout, p.stdout)
p = subprocess.run(["bash", os.path.join(clone, "mapool"), "update"], capture_output=True, text=True, timeout=60)
check("mapool update with nothing new says so", "already the latest" in p.stdout, p.stdout + p.stderr)

finish("test2_ui")
