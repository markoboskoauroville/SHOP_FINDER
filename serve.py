#!/usr/bin/env python3
"""
serve.py: the Shop & Pool Finder's small server. Standard library only.

  GET {PREFIX}/            the app (public/index.html) and the files beside it
  GET {PREFIX}/pools.json  the hours update_pools.py wrote last (404 until the first run)
  GET {PREFIX}/update      starts update_pools.py in the background and answers at once
                           ({"started": true}); the page polls /health until "updated" changes.
                           A run younger than ten minutes is not repeated ({"skipped": true}):
                           the button is public behind pages.dev
  GET {PREFIX}/config.js   window.SF_CONFIG = {google, googleTiles}: whether the paid option exists here
  GET {PREFIX}/places      ?q=&lat=&lng=&radius=&n=  Google Places text search, made HERE with the key
                           (the file google_maps_key in the data folder, or env GOOGLE_MAPS_KEY); the key
                           never reaches the page. Per-IP and daily limits (the address is public).
  GET {PREFIX}/gtile/z/x/y.png  Google's map tiles through the Map Tiles API, made here too; when that API
                           is not enabled on the key, config.js says googleTiles:false and the page keeps
                           OpenStreetMap's tiles
  GET {PREFIX}/health      {"ok": true, "pools_json": true, "age_min": 12}

On the Oracle machine (install.sh): HOST=127.0.0.1 PORT=8900 PREFIX=/shopfinder, behind Caddy,
reached only through the pages.dev door. On a phone in Termux or on a Mac: python3 serve.py, then
http://localhost:8080. Nothing else to configure.

The console (Marko, 13.9.2026: "Q as a quit key, U as update key, the same as my other Termux
apps"): in a terminal, serve.py prints the banner and the key row every app on this phone has,
    q quit   o open page   u check for update   r restart
one key, no Enter (console.py, the shape of MAHA_TRANSCRIBE_TERMUX_TERMINAL's). U fetches GitHub,
shows the installed and the available version (version.py here and on origin/main), asks for y,
pulls with --ff-only and restarts itself on the same port (selfupdate.py). No terminal (systemd on
the machine, nohup, a pipe): no keys, it serves; Ctrl-C stops it as before.

The settings gear (Marko, 13.9.2026): on a phone or a Mac, the page's ⚙ shows which keys this
folder holds, takes a picked key file (the keys found by shape: AIza… is the Google key, sk-ant-…
the Anthropic key, gsk_… the Groq fallback) and tests each key for real with the probes of
KEYRING_TERMUX (probes.py, vendored). The settings addresses answer only to the machine they run
on: a request that came through Caddy or the pages.dev door (X-Forwarded-For, or PREFIX set) gets
404, so the public app can neither read nor replace the keys. Keys in the data folder can also
come from the keyring: `keyring get anthropic` is asked when no file and no environment hold one.

Settings: HOST (default 0.0.0.0), PORT (8080), PREFIX (empty), SHOPFINDER_DATA (the folder of
pools.json and the key files; default: this folder), UPDATE_MIN_AGE (minutes, default 10).
"""

import os
import re
import sys
import json
import time
import threading
import subprocess
import http.server
import socketserver
import urllib.parse
import urllib.request
import urllib.error
import collections

import console as term
import portpick
import probes
import selfupdate
import version

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(HERE, "public")
DATA_DIR = os.environ.get("SHOPFINDER_DATA") or HERE
POOLS_JSON = os.path.join(DATA_DIR, "pools.json")
UPDATER = os.path.join(HERE, "update_pools.py")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
PREFIX = os.environ.get("PREFIX", "").rstrip("/")
UPDATE_MIN_AGE = float(os.environ.get("UPDATE_MIN_AGE", "10")) * 60
# the paid calls are public behind pages.dev: so many per address per ten minutes, so many a day
LIMITS = {"places": (int(os.environ.get("PLACES_PER_10MIN", "40")), 600),
          "gtile": (int(os.environ.get("TILES_PER_10MIN", "1500")), 600)}
DAILY = {"places": int(os.environ.get("PLACES_DAILY_CAP", "600")),
         "gtile": int(os.environ.get("TILES_DAILY_CAP", "15000"))}
GOOGLE_TILE_STYLES = [
    {"elementType": "geometry", "stylers": [{"color": "#1b1f27"}]},
    {"elementType": "labels.text.fill", "stylers": [{"color": "#8b949e"}]},
    {"elementType": "labels.text.stroke", "stylers": [{"color": "#0d1117"}]},
    {"featureType": "road", "elementType": "geometry", "stylers": [{"color": "#2a2f3a"}]},
    {"featureType": "water", "elementType": "geometry", "stylers": [{"color": "#0d1117"}]},
    {"featureType": "poi", "stylers": [{"visibility": "off"}]},
]

update_lock = threading.Lock()
limit_lock = threading.Lock()
hits = collections.defaultdict(collections.deque)     # (kind, ip) -> times
daily = {"day": "", "places": 0, "gtile": 0}
tiles_session = {"session": None, "expiry": 0, "checked": 0, "ok": False}


KEY_FILES = {"google": "google_maps_key", "anthropic": "anthropic_key", "groq": "groq_key"}
KEY_ENV = {"google": "GOOGLE_MAPS_KEY", "anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY"}
KEY_SHAPES = {"google": re.compile(r"AIza[A-Za-z0-9_\-]{35}"), "anthropic": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "groq": re.compile(r"gsk_[A-Za-z0-9]{20,}")}
_keyring_cache = {}


def read_key(provider):
    """The environment, then the file in the data folder, then the keyring on this machine."""
    key = (os.environ.get(KEY_ENV[provider]) or "").strip()
    if key:
        return key
    try:
        with open(os.path.join(DATA_DIR, KEY_FILES[provider]), encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    except OSError:
        pass
    if provider not in _keyring_cache:
        _keyring_cache[provider] = ""
        try:
            p = subprocess.run(["keyring", "get", provider], capture_output=True, text=True, timeout=10)
            _keyring_cache[provider] = p.stdout.strip() if p.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            pass
    return _keyring_cache[provider]


def google_key():
    return read_key("google")


def write_key(provider, value):
    """0600, written beside its name and renamed over it."""
    path = os.path.join(DATA_DIR, KEY_FILES[provider])
    fd = os.open(path + ".new", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value.strip() + "\n")
    os.replace(path + ".new", path)
    _keyring_cache.pop(provider, None)


def key_state():
    """What the gear shows: per provider, whether a key is here and where from, never the key."""
    out = {}
    for prov in KEY_FILES:
        src = ""
        if (os.environ.get(KEY_ENV[prov]) or "").strip():
            src = "environment"
        elif os.path.exists(os.path.join(DATA_DIR, KEY_FILES[prov])) and os.path.getsize(os.path.join(DATA_DIR, KEY_FILES[prov])) > 1:
            src = "file " + KEY_FILES[prov]
        elif read_key(prov):
            src = "the keyring"
        out[prov] = {"present": bool(src), "source": src, "state": settings_state.get(prov, {}).get("state", "untested"), "detail": settings_state.get(prov, {}).get("detail", ""), "at": settings_state.get(prov, {}).get("at", "")}
    return out


settings_state = {}


def local_only(handler):
    """True for a request made on this machine, straight to this server: not through Caddy (which
    adds X-Forwarded-For), not through the pages.dev door, not with PREFIX (the machine's shape)."""
    if PREFIX:
        return False
    h = handler.headers
    if h.get("X-Forwarded-For") or h.get("X-Client-IP") or h.get("CF-Connecting-IP"):
        return False
    return handler.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def allowed(kind, ip):
    """One call more for this address and this day, or not."""
    now = time.time()
    per, window = LIMITS[kind]
    with limit_lock:
        today = time.strftime("%Y-%m-%d")
        if daily["day"] != today:
            daily.update(day=today, places=0, gtile=0)
        if daily[kind] >= DAILY[kind]:
            return False, "today's %s allowance on the machine is used up" % kind
        q = hits[(kind, ip)]
        while q and q[0] < now - window:
            q.popleft()
        if len(q) >= per:
            return False, "too many %s calls from this address, wait a few minutes" % kind
        q.append(now)
        daily[kind] += 1
        return True, ""


def google_places(q, lat, lng, radius, n):
    """Places API (New) text search, the compact shape the page needs."""
    payload = json.dumps({
        "textQuery": q, "languageCode": "en",
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius}},
        "maxResultCount": n, "rankPreference": "DISTANCE",
    }).encode("utf-8")
    req = urllib.request.Request("https://places.googleapis.com/v1/places:searchText", data=payload, headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": google_key(),
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,"
                            "places.currentOpeningHours.openNow,places.currentOpeningHours.weekdayDescriptions,places.googleMapsUri",
        "User-Agent": "shopfinder/1.0",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = []
    for p in data.get("places", []):
        oh = p.get("currentOpeningHours") or {}
        loc = p.get("location") or {}
        out.append({
            "id": p.get("id"), "name": (p.get("displayName") or {}).get("text"),
            "addr": p.get("formattedAddress", ""), "lat": loc.get("latitude"), "lng": loc.get("longitude"),
            "openNow": oh.get("openNow"), "weekday": oh.get("weekdayDescriptions") or [],
            "mapsUri": p.get("googleMapsUri"),
        })
    return out


def google_tiles_session():
    """A Map Tiles API session for the dark roadmap, kept until it expires; False when the API is
    not enabled on the key (checked again after an hour)."""
    now = time.time()
    with limit_lock:
        if tiles_session["session"] and tiles_session["expiry"] > now + 60:
            return tiles_session["session"]
        if not tiles_session["ok"] and now - tiles_session["checked"] < 3600:
            return None
        tiles_session["checked"] = now
    key = google_key()
    if not key:
        return None
    try:
        payload = json.dumps({"mapType": "roadmap", "language": "en-GB", "region": "HR",
                              "styles": GOOGLE_TILE_STYLES}).encode("utf-8")
        req = urllib.request.Request("https://tile.googleapis.com/v1/createSession?key=" + key, data=payload,
                                     headers={"Content-Type": "application/json", "User-Agent": "shopfinder/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        with limit_lock:
            tiles_session.update(session=data["session"], expiry=float(data.get("expiry", now + 3600)), ok=True)
        return data["session"]
    except Exception as e:
        sys.stderr.write("map tiles session not created (the Map Tiles API off on the key?): %s\n" % repr(e)[:200])
        with limit_lock:
            tiles_session.update(session=None, ok=False)
        return None

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
        if path == "/places":
            return self.serve_places()
        if path.startswith("/gtile/"):
            return self.serve_tile(path)
        if path == "/health":
            return send_json(self, 200, health())
        if path == "/settings/state":
            if not local_only(self):
                return self.send_error(404, "not here")
            return send_json(self, 200, {"ok": True, "version": version.APP_VERSION, "keys": key_state(), "data_dir": DATA_DIR})
        if path.startswith("/settings/test"):
            if not local_only(self):
                return self.send_error(404, "not here")
            return self.settings_test()
        # the static files: SimpleHTTPRequestHandler reads self.path
        self.path = path
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.unquote(self.path.split("?")[0])
        if path == "/settings/import":
            if not local_only(self):
                return self.send_error(404, "not here")
            return self.settings_import()
        return self.send_error(404, "Not found")

    def settings_import(self):
        """The picked key file, as the request body (text): keys found by shape, written to the data
        folder, the answer says what was found and never a value."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 4 * 1024 * 1024:
            return send_json(self, 400, {"ok": False, "error": "no file, or a file larger than 4 MB, which is not a key file"})
        raw = self.rfile.read(n)
        if b"\x00" in raw[:4096]:
            return send_json(self, 400, {"ok": False, "error": "not a text file"})
        text = raw.decode("utf-8", "replace")
        found = {}
        for prov, rx in KEY_SHAPES.items():
            m = rx.findall(text)
            if m:
                found[prov] = m[-1]
        if not found:
            return send_json(self, 200, {"ok": True, "written": [], "note": "no key of a shape this app uses (AIza…, sk-ant-…, gsk_…) in that file"})
        written = []
        for prov, val in found.items():
            write_key(prov, val)
            settings_state.pop(prov, None)
            written.append(prov)
        return send_json(self, 200, {"ok": True, "written": written, "keys": key_state()})

    def settings_test(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        prov = (qs.get("provider") or [""])[0]
        if prov not in KEY_FILES:
            return send_json(self, 400, {"ok": False, "error": "provider?"})
        key = read_key(prov)
        if not key:
            return send_json(self, 200, {"ok": True, "state": "absent", "detail": "no %s key here" % prov})
        v = probes.test_key(prov, key)
        settings_state[prov] = {"state": v["state"], "detail": v["detail"][:200], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        return send_json(self, 200, {"ok": True, "state": v["state"], "detail": v["detail"][:200], "status": v.get("status"), "apis": v.get("apis")})

    def client_ip(self):
        h = self.headers
        return (h.get("X-Client-IP") or (h.get("X-Forwarded-For") or "").split(",")[0].strip() or self.client_address[0])

    def serve_config(self):
        """Whether the paid option exists on this machine. Never the key."""
        has_key = bool(google_key())
        body = ("window.SF_CONFIG = " + json.dumps({
            "google": has_key, "googleTiles": bool(has_key and google_tiles_session())}) + ";").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_places(self):
        if not google_key():
            return send_json(self, 503, {"ok": False, "error": "no Google key on the machine"})
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        try:
            q = qs.get("q", [""])[0].strip()[:120]
            lat = float(qs.get("lat", ["45.8131"])[0]); lng = float(qs.get("lng", ["15.9775"])[0])
            radius = min(max(float(qs.get("radius", ["3000"])[0]), 50.0), 50000.0)
            n = min(max(int(qs.get("n", ["20"])[0]), 1), 20)
        except ValueError:
            return send_json(self, 400, {"ok": False, "error": "bad query"})
        if not q:
            return send_json(self, 400, {"ok": False, "error": "q missing"})
        ok, why = allowed("places", self.client_ip())
        if not ok:
            return send_json(self, 429, {"ok": False, "error": why})
        try:
            return send_json(self, 200, {"ok": True, "places": google_places(q, lat, lng, radius, n)})
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:300]
            sys.stderr.write("places %s: %s\n" % (e.code, body))
            return send_json(self, 502, {"ok": False, "error": "Google answered %d (the key's restrictions?)" % e.code})
        except Exception as e:
            return send_json(self, 502, {"ok": False, "error": "Google not reached: " + repr(e)[:120]})

    def serve_tile(self, path):
        m = re.match(r"^/gtile/(\d{1,2})/(\d+)/(\d+)\.png$", path)
        if not m:
            return self.send_error(404, "tile?")
        session = google_tiles_session()
        if not session:
            return self.send_error(503, "no Google tiles on this machine")
        ok, why = allowed("gtile", self.client_ip())
        if not ok:
            return self.send_error(429, why)
        z, x, y = m.groups()
        url = "https://tile.googleapis.com/v1/2dtiles/%s/%s/%s?session=%s&key=%s" % (z, x, y, session, google_key())
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "shopfinder/1.0"}), timeout=20) as resp:
                data = resp.read()
                ctype = resp.headers.get("Content-Type", "image/png")
        except urllib.error.HTTPError as e:
            return self.send_error(502, "Google tile %d" % e.code)
        except Exception:
            return self.send_error(502, "Google tile not reached")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=1800")
        self.end_headers()
        self.wfile.write(data)

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


def console_snapshot():
    return {"version": version.APP_VERSION, "pools_updated": pools_updated(), "google": bool(google_key())}


def console_busy():
    """An update or a restart while update_pools.py runs would cut it in half."""
    if update_state["running"]:
        return "a pool update is running, press u again when the page says it is done"
    return ""


if __name__ == "__main__":
    if not os.path.isdir(PUBLIC):
        print("no public/ folder beside serve.py: " + PUBLIC)
        sys.exit(1)
    note = None
    if not PREFIX:
        # on a phone or a Mac: the app never fails to start because a port is taken (portpick.py,
        # the ecosystem rule of 13.9.2026); on the machine (PREFIX set) Caddy routes to ONE port,
        # so a taken port there is an error systemd retries, not a move
        PORT, note = portpick.pick(HOST if HOST != "0.0.0.0" else "0.0.0.0", PORT)
    try:
        httpd = Server((HOST, PORT), Handler)
    except OSError as e:
        print("port %d is taken (%s): another copy of this app?" % (PORT, e.strerror))
        sys.exit(1)
    url = "http://%s:%d%s/" % ("localhost" if HOST in ("0.0.0.0", "127.0.0.1") else HOST, PORT, PREFIX)
    with httpd:
        action = term.run(httpd, url, snapshot=console_snapshot, note=note,
                          on_check_update=selfupdate.check_remote, on_perform_update=selfupdate.perform_update,
                          busy=console_busy)
    if action == "restart":
        # on the main thread: the listening socket is closed, the terminal restored; same pid, same port
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
