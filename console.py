"""
console.py  --  the terminal side of the Shop & Pool Finder.

The same console every Termux app on this phone has (MAHA_TRANSCRIBE_TERMUX_TERMINAL/console.py,
GOOGLE_TTS_STT's serve(), MAHA_COMMUTE's main()), so a person moving between them sees one thing:
a few plain lines printed once, the terminal scrolling and wrapping the way it knows how, and a key
press answered by printing a NEW line rather than repainting an old one. No box: a panel built to a
fixed inner width truncates whatever does not fit, and on a forty column phone screen that means
most of the key row disappears while still being bound.

    q            quit
    o            open the page again
    u            check for an update, confirm with y, then update and restart
    r            restart

DEGRADES HONESTLY. With no terminal (systemd on the Oracle machine, nohup, a pipe) there is no key
to press, so it prints the address and serves; Ctrl-C stops it, as before.
"""

import os
import shutil
import subprocess
import sys
import threading
import time

# the same amber the other consoles use
AMBER = "\033[38;5;214m"
SAND = "\033[38;5;223m"
SLATE = "\033[38;5;245m"
RED = "\033[38;5;203m"
OFF = "\033[0m"

LOGO = [
    "███████╗██╗  ██╗ ██████╗ ██████╗ ",
    "██╔════╝██║  ██║██╔═══██╗██╔══██╗",
    "███████╗███████║██║   ██║██████╔╝",
    "╚════██║██╔══██║██║   ██║██╔═══╝ ",
    "███████║██║  ██║╚██████╔╝██║     ",
    "╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝     ",
]


def w(s, colour, enabled=True):
    return "%s%s%s" % (colour, s, OFF) if enabled else s


def say(line=""):
    print(line, flush=True)


def open_page(url):
    """termux-open-url on the phone, open on a Mac, xdg-open on Linux. False when none exists."""
    for cmd in (["termux-open-url", url], ["open", url], ["xdg-open", url]):
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                pass
    return False


def is_interactive():
    """A terminal on both sides, and this process not a background job of it. A background job
    (`mapool &`) that reads its controlling terminal is stopped by SIGTTIN, so it gets no keys; under
    systemd, nohup or a pipe there is no terminal at all. A pty that is NOT this process's
    controlling terminal (a test harness, a launcher that started it in a new session) cannot stop
    it, so it is interactive: tcgetpgrp raising ENOTTY means "no controlling terminal", not "no
    terminal" (found 13.9.2026: the first version read it as the latter and printed
    'no terminal: no keys' on a perfectly good pty)."""
    try:
        fd = sys.stdin.fileno()
        if not (sys.stdout.isatty() and os.isatty(fd)):
            return False
    except (OSError, ValueError, AttributeError):
        return False
    try:
        return os.tcgetpgrp(fd) == os.getpgrp()
    except OSError:
        return True


def _print_banner(url, colour, snap):
    for row in LOGO:
        say(w(row, AMBER, colour))
    say()
    say("  " + w("Shop & Pool Finder", SAND, colour) + "   ·   " + w(url, SLATE, colour))
    s = snap() if snap else {}
    pools = ("pool hours from %s" % s["pools_updated"]) if s.get("pools_updated") else "no pool hours yet (the page's refresh button, or update_pools.py)"
    paid = "Google option on" if s.get("google") else "free map only (no Google key here)"
    say("  version " + str(s.get("version", "?")) + "   ·   " + w(pools, SLATE, colour) + "   ·   " + w(paid, SLATE, colour))
    say()


def _print_keys(colour):
    say("  " + w("q", AMBER, colour) + " quit   " +
        w("o", AMBER, colour) + " open page   " +
        w("u", AMBER, colour) + " check for update   " +
        w("r", AMBER, colour) + " restart")
    try:
        cols = shutil.get_terminal_size((40, 20)).columns
    except Exception:
        cols = 40
    say(w("ॐ" + "─" * max(cols - 3, 0), AMBER, colour))


def run(httpd, url, snapshot=None, note=None, on_check_update=None, on_perform_update=None, busy=None):
    """Serve httpd (an http.server), printing plain lines rather than drawing a box.

    Returns "quit" or "restart". on_check_update() -> dict, on_perform_update() -> str; both may
    raise, and a failure is printed as one more plain line rather than crashing the console.
    busy() -> str or "": when it says something, an update is refused with that reason (a pool
    update running in the background must not be cut in half by a restart).
    """
    colour = is_interactive()

    if note:
        say(note)
    _print_banner(url, colour, snapshot)

    if not is_interactive():
        say("Shop & Pool Finder — " + url + "   (no terminal: no keys; Ctrl-C stops)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            say("\nstopped")
        return "quit"

    _print_keys(colour)

    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    # set while an update is offered; the very next keypress answers that question instead of
    # being read as a command, so a stray key afterwards cannot start (or skip) an update by accident
    awaiting_confirm = [False]
    pending_check = [None]

    def handle_update_check():
        say()
        reason = busy() if busy else ""
        if reason:
            say("  " + w(reason, SAND, colour))
            return
        say("  checking for an update…")
        try:
            info = on_check_update()
        except Exception as e:                                   # noqa: BLE001
            say("  " + w("could not check: " + str(e), RED, colour))
            return
        if info["up_to_date"]:
            say("  " + w("v%s is already the latest version" % info["installed"], SLATE, colour))
            return
        say("  " + w("v%s installed" % info["installed"], SAND, colour) +
            "   →   " + w("v%s available" % info["latest"], AMBER, colour))
        say("  press " + w("y", AMBER, colour) + " to update, any other key cancels")
        pending_check[0] = info
        awaiting_confirm[0] = True

    def handle_update_confirm(ch):
        info = pending_check[0]
        awaiting_confirm[0] = False
        if ch != "y":
            say("  update canceled")
            return None
        say("  updating v%s → v%s…" % (info["installed"], info["latest"]))
        say("  pulling…")
        try:
            msg = on_perform_update()
        except Exception as e:                                   # noqa: BLE001
            say("  " + w("update failed: " + str(e), RED, colour))
            return None
        say("  " + w(msg, SLATE, colour))
        say("  " + w("updated to v%s, restarting…" % info["latest"], AMBER, colour))
        time.sleep(1.0)
        return "restart"

    action = "quit"
    try:
        tty.setcbreak(fd)
        while True:
            r, _, _ = select.select([fd], [], [], 0.5)
            if not r:
                continue
            raw = os.read(fd, 1)
            if not raw:                                          # the terminal went away
                break
            ch = raw.decode(errors="ignore").lower()

            if awaiting_confirm[0]:
                result = handle_update_confirm(ch)
                if result:
                    action = result
                    break
                continue

            if ch in ("q", "\x03", "\x04"):
                action = "quit"
                break
            if ch == "r":
                reason = busy() if busy else ""
                if reason:
                    say("  " + w(reason, SAND, colour))
                    continue
                say("  restarting…")
                action = "restart"
                break
            if ch == "o":
                ok = open_page(url)
                say("  " + ("opening the browser" if ok else
                            w("no way to open a browser from here, go to " + url + " yourself", RED, colour)))
            elif ch == "u" and on_check_update:
                handle_update_check()
    except KeyboardInterrupt:
        action = "quit"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    httpd.shutdown()
    if action == "quit":
        say(w("  stopped.", SLATE, colour))
    return action
