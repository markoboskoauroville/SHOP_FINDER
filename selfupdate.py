"""
selfupdate.py  --  check what is installed against what GitHub has, and update in place on
confirmation. The shape of MAHA_TRANSCRIBE_TERMUX_TERMINAL/selfupdate.py, without the pip step
(this app is standard library only).

This is the U key in the console: check, print the installed version and the available one, wait
for a yes, then pull and restart. It never updates without that yes, and it never guesses at a
version number: both numbers come from reading version.py, the local file and the one on
origin/main, never from a changelog or a commit count.

The functions are deliberately separate rather than one big "do the update" call, so the console
can show the check result BEFORE asking for confirmation: check, print, then confirm.
"""

import os
import re
import subprocess

import version as local_version

HERE = os.path.dirname(os.path.abspath(__file__))
REMOTE = "origin"
BRANCH = "main"
GIT_TIMEOUT = 20

_VERSION_RE = re.compile(r"APP_VERSION\s*=\s*(\d+)")


class UpdateError(Exception):
    """Raised with a message safe to show directly to the person."""


def is_git_checkout():
    return os.path.isdir(os.path.join(HERE, ".git"))


def installed_version():
    return local_version.APP_VERSION


def _run(args, timeout):
    try:
        return subprocess.run(args, cwd=HERE, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise UpdateError("%s did not answer in %ds, check the network and try again" % (" ".join(args[:2]), timeout))
    except FileNotFoundError:
        raise UpdateError("'%s' is not installed" % args[0])


def check_remote():
    """Fetch, then read version.py off origin/main without touching the working tree.
    Returns {installed, latest, up_to_date, behind}.

    behind is the commit count between HEAD and origin/main: a version number can be unchanged
    while there is nothing to pull, which is a different fact from "there is a newer number".
    """
    if not is_git_checkout():
        raise UpdateError("%s is not a git checkout, cannot self-update; clone it from GitHub instead" % HERE)

    fetch = _run(["git", "fetch", "--quiet", REMOTE, BRANCH], GIT_TIMEOUT)
    if fetch.returncode != 0:
        raise UpdateError("could not reach GitHub: " + (fetch.stderr or "unknown git error").strip().splitlines()[-1])

    show = _run(["git", "show", "%s/%s:version.py" % (REMOTE, BRANCH)], GIT_TIMEOUT)
    if show.returncode != 0:
        raise UpdateError("could not read version.py from %s/%s" % (REMOTE, BRANCH))
    m = _VERSION_RE.search(show.stdout)
    if not m:
        raise UpdateError("origin's version.py does not have a readable APP_VERSION")
    latest = int(m.group(1))

    behind = _run(["git", "rev-list", "--count", "HEAD..%s/%s" % (REMOTE, BRANCH)], GIT_TIMEOUT)
    out = behind.stdout.strip()
    behind_n = int(out) if behind.returncode == 0 and out.isdigit() else None

    installed = installed_version()
    return {
        "installed": installed,
        "latest": latest,
        "up_to_date": latest <= installed and (behind_n == 0 if behind_n is not None else True),
        "behind": behind_n,
    }


def perform_update():
    """git pull --ff-only: it either lands cleanly or does not move at all. Returns one line for
    the console (never the raw multi-line git output)."""
    pull = _run(["git", "pull", "--ff-only", REMOTE, BRANCH], 120)
    if pull.returncode != 0:
        raise UpdateError("git pull failed: " + (pull.stderr or pull.stdout or "unknown error").strip().splitlines()[-1])
    summary = (pull.stdout or "").strip().splitlines()
    return summary[0] if summary else "already at the latest commit"
