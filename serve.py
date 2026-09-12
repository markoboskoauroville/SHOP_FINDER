#!/usr/bin/env python3
"""
serve.py: the Shop & Pool Finder's small server. Standard library only.

  GET {PREFIX}/            the app (public/index.html) and the files beside it
  GET {PREFIX}/pools.json  the hours update_pools.py wrote last (404 until the first run)
  GET {PREFIX}/update      starts update_pools.py in the background and answers at once
                           ({"started": true}); the page polls /health until "updated" changes.
                           A run younger than ten minutes is not repeated ({"skipped": true}):
                           the button is public behind pages.dev
  GET {PREFIX}/config.js   window.SF_CONFIG = {googleMapsKey} (env GOOGLE_MAPS_KEY or the file google_maps_key)
  GET {PREFIX}/health      {"ok": true, "pools_json": true, "age_min": 12}

On the Oracle machine (install.sh): HOST=127.0.0.1 PORT=8900 PREFIX=/shopfinder, behind Caddy,
reached only through the pages.dev door. On a phone in Termux or on a Mac: python3 serve.py, then
http://localhost:8080. Nothing else to configure.

Settings: HOST (default 0.0.0.0), PORT (8080), PREFIX (empty), SHOPFINDER_DATA (the folder of
pools.json and groq_key; default: this folder), UPDATE_MIN_AGE (minutes, default 10).
"""

import os
import sys
import json
import time
import threading
import subprocess
import http.server
import socketserver
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(HERE, "public")
DATA_DIR = os.environ.get("SHOPFINDER_DATA") or HERE
POOLS_JSON = os.path.join(DATA_DIR, "pools.json")
UPDATER = os.path.join(HERE, "update_pools.py")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
PREFIX = os.environ.get("PREFIX", "").rstrip("/")
UPDATE_MIN_AGE = float(os.environ.get("UPDATE_MIN_AGE", "10")) * 60

update_lock = threading.Lock()


def pools_age():
    """Seconds since pools.json was written, or None."""
    try:
        return time.time() - os.path.getmtime(POOLS_JSON)
    except OSError:
        return None


def pools_updated():
    """The moment pools.json was written, ISO, or None."""
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(POOLS_JSON)))
    except OSError:
        return None


update_state = {"running": False, "started": None, "last_ok": None, "last_error": "", "last_log": ""}


def health():
    age = pools_age()
    return {"ok": True, "pools_json": age is not None, "age_min": None if age is None else round(age / 60),
            "updated": pools_updated(), "running": update_state["running"],
            "last_ok": update_state["last_ok"], "last_error": update_state["last_error"]}


def run_updater():
    """update_pools.py in the background (a run is one to three minutes on Groq's free tier)."""
    try:
        env = dict(os.environ, SHOPFINDER_DATA=DATA_DIR)
        proc = subprocess.run([sys.executable, UPDATER], cwd=HERE, env=env,
                              capture_output=True, text=True, timeout=600)
        ok = proc.returncode == 0
        update_state["last_ok"] = ok
        update_state["last_log"] = (proc.stdout + proc.stderr)[-4000:]
        update_state["last_error"] = "" if ok else ("no Groq key on this machine" if proc.returncode == 2 else "update_pools.py failed")
        sys.stderr.write(update_state["last_log"] + "\n")
    except Exception as e:
        update_state["last_ok"] = False
        update_state["last_error"] = repr(e)
    finally:
        update_state["running"] = False
        update_lock.release()


def send_json(handler, code, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        path = urllib.parse.unquote(self.path.split("?")[0])
        if PREFIX:
            if path == PREFIX:
                self.send_response(302)
                self.send_header("Location", PREFIX + "/")
                self.end_headers()
                return
            if not path.startswith(PREFIX + "/"):
                return self.send_error(404, "Not under " + PREFIX)
            path = path[len(PREFIX):]
        if path == "/pools.json":
            return self.serve_pools()
        if path == "/update":
            return self.handle_update()
        if path == "/config.js":
            return self.serve_config()
        if path == "/health":
            return send_json(self, 200, health())
        # the static files: SimpleHTTPRequestHandler reads self.path
        self.path = path
        return super().do_GET()

    def serve_config(self):
        """The paid option's Google key: env GOOGLE_MAPS_KEY, or the file google_maps_key in the data folder."""
        key = (os.environ.get("GOOGLE_MAPS_KEY") or "").strip()
        if not key:
            try:
                with open(os.path.join(DATA_DIR, "google_maps_key"), encoding="utf-8") as f:
                    key = f.read().strip()
            except OSError:
                key = ""
        body = ("window.SF_CONFIG = " + json.dumps({"googleMapsKey": key}) + ";").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_pools(self):
        try:
            with open(POOLS_JSON, "rb") as f:
                body = f.read()
        except OSError:
            return send_json(self, 404, {"ok": False, "error": "pools.json not written yet"})
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_update(self):
        """Start a run and answer at once; the page polls /health until "updated" changes."""
        age = pools_age()
        if age is not None and age < UPDATE_MIN_AGE and not update_state["running"]:
            return send_json(self, 200, {"ok": True, "skipped": True, "age_min": round(age / 60), "updated": pools_updated()})
        if not update_lock.acquire(blocking=False):
            return send_json(self, 200, {"ok": True, "started": True, "running": True, "updated": pools_updated()})
        update_state["running"] = True
        update_state["started"] = time.time()
        threading.Thread(target=run_updater, daemon=True).start()
        return send_json(self, 200, {"ok": True, "started": True, "running": True, "updated": pools_updated()})


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    if not os.path.isdir(PUBLIC):
        print("no public/ folder beside serve.py: " + PUBLIC)
        sys.exit(1)
    with Server((HOST, PORT), Handler) as httpd:
        print("serving %s at http://%s:%d%s/" % (PUBLIC, "localhost" if HOST in ("0.0.0.0", "127.0.0.1") else HOST, PORT, PREFIX), flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
