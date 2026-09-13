"""What the four tests share: a pty around serve.py, driven the way a person drives it (keys, no
Enter), with every check made on what appeared on the screen or what the port answered. The shape of
termux-tools/tests/run_tty.py. Absolute paths everywhere; never cd (modules/termux-proot-working.md)."""
import fcntl
import os
import pty
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
PY = sys.executable

fails, count = [], 0


def check(label, ok, detail=""):
    global count
    count += 1
    print("  %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  " + str(detail)) if detail and not ok else ""), flush=True)
    if not ok:
        fails.append("%s %s" % (label, detail))


def finish(name):
    print()
    print("%s: %d checks, %d failed" % (name, count, len(fails)))
    for f in fails:
        print("  - " + f)
    sys.exit(1 if fails else 0)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def strip_ansi(b):
    return re.sub(rb"\x1b\[[0-9;?]*[a-zA-Z]", b"", b).decode("utf-8", "replace")


def http(url, timeout=5):
    """(status, body) or (None, error)"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return None, repr(e)


def wait_port(port, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        st, _ = http("http://127.0.0.1:%d/health" % port, 2)
        if st == 200:
            return True
        time.sleep(0.2)
    return False


def stub_bin():
    """A folder on the PATH with a fake termux-open-url that records the URL it was given, so the
    o key can be checked without a browser (modules/termux-app.md §12: a stand-in proves the wiring)."""
    d = tempfile.mkdtemp(prefix="mapool-stub-")
    rec = os.path.join(d, "opened.txt")
    with open(os.path.join(d, "termux-open-url"), "w") as f:
        f.write("#!/bin/sh\necho \"$1\" >> '%s'\n" % rec)
    os.chmod(os.path.join(d, "termux-open-url"), 0o755)
    return d, rec


class Console:
    """serve.py on a real pty."""

    def __init__(self, app_dir=APP, port=None, env=None, rows=40, cols=100, data_dir=None):
        self.port = port or free_port()
        self.m, s = pty.openpty()
        fcntl.ioctl(s, termios_winsz(), struct.pack("HHHH", rows, cols, 0, 0))
        e = dict(os.environ, TERM="xterm-256color", PYTHONUNBUFFERED="1", PORT=str(self.port), HOST="127.0.0.1")
        if data_dir:
            e["SHOPFINDER_DATA"] = data_dir
        if env:
            e.update(env)
        self.p = subprocess.Popen([PY, os.path.join(app_dir, "serve.py")], stdin=s, stdout=s, stderr=s,
                                  env=e, close_fds=True, start_new_session=True)
        os.close(s)
        self.pgid = os.getpgid(self.p.pid)
        self.buf = b""

    def read(self, seconds=0.5):
        end = time.time() + seconds
        while time.time() < end:
            try:
                r, _, _ = select.select([self.m], [], [], 0.1)
            except (OSError, ValueError):
                break
            if r:
                try:
                    chunk = os.read(self.m, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                self.buf += chunk
        return strip_ansi(self.buf)

    def wait_for(self, text, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            if text in self.read(0.3):
                return True
        return False

    def key(self, ch):
        os.write(self.m, ch.encode() if isinstance(ch, str) else ch)

    def screen(self):
        return strip_ansi(self.buf)

    def alive(self):
        return self.p.poll() is None

    def wait_exit(self, seconds=8):
        end = time.time() + seconds
        while time.time() < end and self.p.poll() is None:
            self.read(0.2)
        return self.p.poll() is not None

    def kill(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if self.p.poll() is None:
                try:
                    os.killpg(self.pgid, sig)
                except OSError:
                    pass
                time.sleep(0.5)
        self.p.poll()
        try:
            os.close(self.m)
        except OSError:
            pass

    def left_behind(self):
        """Processes still in the group. ps -g is the SESSION on procps-ng: read /proc/*/stat field 5."""
        left = []
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open("/proc/%s/stat" % pid) as f:
                    st = f.read()
                pgrp = int(st[st.rindex(")") + 2:].split()[2])
            except (OSError, ValueError, IndexError):
                continue
            if pgrp == self.pgid and int(pid) != os.getpid():
                left.append(int(pid))
        return left


def termios_winsz():
    import termios
    return termios.TIOCSWINSZ


def git(repo, *args, check=True):
    p = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True, timeout=60)
    if check and p.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), p.stderr.strip()))
    return p.stdout.strip()


def make_clone(version=1, tag="v1"):
    """A bare 'GitHub' with the app at APP_VERSION=version, and a clone of it: (bare, clone).
    The clone is the app under test: the real files of this folder, committed at that number."""
    root = tempfile.mkdtemp(prefix="mapool-git-")
    bare = os.path.join(root, "origin.git")
    work = os.path.join(root, "work")
    clone = os.path.join(root, "clone")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", work], check=True)
    git(work, "config", "user.email", "test@example.invalid")
    git(work, "config", "user.name", "test")
    copy_app(work, version)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", tag)
    git(work, "remote", "add", "origin", bare)
    git(work, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", bare, clone], check=True)
    git(clone, "config", "user.email", "test@example.invalid")
    git(clone, "config", "user.name", "test")
    return bare, work, clone


def copy_app(dst, version):
    import shutil
    for name in ("serve.py", "console.py", "selfupdate.py", "update_pools.py", "mapool"):
        shutil.copy(os.path.join(APP, name), os.path.join(dst, name))
    if not os.path.isdir(os.path.join(dst, "public")):
        shutil.copytree(os.path.join(APP, "public"), os.path.join(dst, "public"))
    with open(os.path.join(dst, "version.py"), "w") as f:
        f.write('"""test copy"""\n\nAPP_VERSION = %d\n' % version)


def bump_remote(work, version, tag):
    """A new version lands on 'GitHub'."""
    with open(os.path.join(work, "version.py"), "w") as f:
        f.write('"""test copy"""\n\nAPP_VERSION = %d\n' % version)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", tag)
    git(work, "push", "-q", "origin", "main")
