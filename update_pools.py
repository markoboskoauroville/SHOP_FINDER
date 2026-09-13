#!/usr/bin/env python3
"""
update_pools.py: today's public-swim hours for the Zagreb city pools.

Reads each pool's official page on sportskiobjekti.hr, asks Claude Haiku (Marko, 13.9.2026: "you
always need to use Haiku to actually scrape the working hours") to pull out today's hours for the
public (gradjanstvo), the whole week as a compact list (Mon-Fri 06:30-20:00, Sat-Sun ...) and any
notice, computes open_now from the local time, and writes pools.json. Without an Anthropic key it
falls back to Groq, the extractor of 12.9.2026. The app (public/index.html) reads pools.json from
the same origin; when the file is missing it falls back to live Google hours on its own.

Standard library only. Runs on the Oracle machine (a timer every morning, and the app's refresh
button through serve.py), on a phone in Termux, or on a Mac.

    python3 update_pools.py

Settings, all optional:
  ANTHROPIC_API_KEY  the key; else the file anthropic_key in SHOPFINDER_DATA, else next to this script
  CLAUDE_MODEL     default claude-haiku-4-5 (Haiku, always: the cheap one, the pages are short)
  GROQ_API_KEY     the fallback; else the file groq_key in SHOPFINDER_DATA, else next to this script
  GROQ_MODEL       the model (or a comma list) to try first; default openai/gpt-oss-120b, then gpt-oss-20b, qwen3.8-27b
  SHOPFINDER_DATA  where pools.json (and groq_key) live; default: the folder of this script
  POOLS_OUT        the exact output path, wins over SHOPFINDER_DATA
  TZ               the machine runs in UTC; install.sh sets Europe/Zagreb for the service and the timer
"""

import os
import re
import sys
import json
import html
import time
import datetime
import concurrent.futures
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("SHOPFINDER_DATA") or HERE
OUT_PATH = os.environ.get("POOLS_OUT") or os.path.join(DATA_DIR, "pools.json")
# Groq retires models (llama-3.3-70b-versatile was gone by 12.9.2026): the first of these that
# answers is used; GROQ_MODEL (comma-separated allowed) puts other names first.
GROQ_MODELS = [m.strip() for m in (os.environ.get("GROQ_MODEL") or "").split(",") if m.strip()] + \
              ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile"]
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = (os.environ.get("CLAUDE_MODEL") or "claude-haiku-4-5").strip()
CLAUDE_MAX_CHARS = 12000        # a pool's own text is 3,000-6,000 characters; Haiku reads it whole
# One pool at a time: Groq's free tier allows a few thousand tokens a minute, and eight pages at once
# answered 429 (12.9.2026). A 429 waits what Groq asks and tries again, three times.
MAX_WORKERS = 1
SNIPPET_CHARS = 4000


def _key(env_name, file_name, provider=""):
    """A key from the environment, or from a file in the data folder (never inside the repo), or
    from the keyring on this machine (`keyring get <provider>`, KEYRING_TERMUX) when it is installed."""
    k = (os.environ.get(env_name) or "").strip()
    if k:
        return k
    for path in (os.path.join(DATA_DIR, file_name), os.path.join(HERE, file_name)):
        try:
            with open(path, encoding="utf-8") as f:
                k = f.read().strip()
            if k:
                return k
        except OSError:
            pass
    if provider:
        try:
            import subprocess
            p = subprocess.run(["keyring", "get", provider], capture_output=True, text=True, timeout=10)
            if p.returncode == 0 and p.stdout.strip():
                return p.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return ""


def anthropic_key():
    return _key("ANTHROPIC_API_KEY", "anthropic_key", "anthropic")


def groq_key():
    return _key("GROQ_API_KEY", "groq_key", "groq")


OFFICIAL = "https://www.sportskiobjekti.hr/"

# Fixed data: only the name and the location never change; the hours come from the site.
# The same list as POOLS in public/index.html. Links and addresses from the official pages, positions
# from OpenStreetMap, 12.9.2026 (the old Utrina, Šalata and Mladost positions were up to 1.5 km off).
# Bazen Špansko opened 9.9.2026.
POOLS = [
    {"id": "pool-spansko", "name": "Bazen Špansko", "addr": "Ul. Drage Stipca 4, Zagreb",
     "lat": 45.79740, "lng": 15.90475, "url": OFFICIAL + "bazen-spansko/2311"},
    {"id": "pool-mladost-out", "name": "Bazeni Mladost – outdoor (SP Mladost)", "addr": "Jarunska 5, Zagreb",
     "lat": 45.78243, "lng": 15.94467, "url": OFFICIAL + "sportski-park-mladost/1345"},
    {"id": "pool-mladost-in", "name": "Zimsko plivalište Mladost – indoor", "addr": "Trg Krešimira Ćosića 10, Zagreb",
     "lat": 45.80632, "lng": 15.95132, "url": OFFICIAL + "zimsko-plivaliste-mladost/1369"},
    {"id": "pool-utrine", "name": "Bazenski kompleks Utrina", "addr": "Kombolova ul. 4A, Zagreb",
     "lat": 45.77376, "lng": 15.99168, "url": OFFICIAL + "bazenski-kompleks-utrina/1368"},
    {"id": "pool-salata", "name": "ŠRC Šalata – outdoor pool", "addr": "Stube Josipa Schlossera 2, Zagreb",
     "lat": 45.81658, "lng": 15.98510, "url": OFFICIAL + "sportsko-rekreacijski-centar-salata/1346"},
    {"id": "pool-svetice", "name": "Bazenski kompleks Svetice", "addr": "Ul. Divka Budaka 21, Zagreb",
     "lat": 45.81714, "lng": 16.01589,
     "url": OFFICIAL + "sportsko-rekreacijski-centar-svetice-i-bazenski-kompleks-svetice/1358"},
    {"id": "pool-jelkovec", "name": "Bazen Jelkovec (Sesvete)", "addr": "Ul. Vladimira Stahuljaka 5, Sesvete",
     "lat": 45.81022, "lng": 16.10691, "url": OFFICIAL + "bazen-jelkovec/1370"},
    {"id": "pool-iver", "name": "Bazen Iver (Sesvetski Kraljevec)", "addr": "Ul. Mladena Halape 6, Sesvete",
     "lat": 45.81181, "lng": 16.18354, "url": OFFICIAL + "bazen-iver-1388/1388"},
]

# Croatian public holidays (the weekend/holiday schedule applies).
HOLIDAYS = {
    "2026-01-01", "2026-01-06", "2026-04-05", "2026-04-06", "2026-05-01",
    "2026-05-30", "2026-06-04", "2026-06-22", "2026-08-05", "2026-08-15",
    "2026-11-01", "2026-11-18", "2026-12-25", "2026-12-26",
    "2027-01-01", "2027-01-06", "2027-03-28", "2027-03-29", "2027-05-01",
    "2027-05-27", "2027-05-30", "2027-06-22", "2027-08-05", "2027-08-15",
    "2027-11-01", "2027-11-18", "2027-12-25", "2027-12-26",
}

DAYS_HR = ["nedjelja", "ponedjeljak", "utorak", "srijeda", "cetvrtak", "petak", "subota"]


def log(msg):
    print("[update_pools] " + msg, flush=True)


def fetch_page(url, tries=3):
    """Download a page and return its visible text (no tags). The site answers slowly at times
    (Iver timed out at 30 s on 13.9.2026 while the seven others came): three tries, then the error."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (pool-updater) Python-urllib",
        "Accept-Language": "hr,en;q=0.8",
    })
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == tries - 1 or (isinstance(e, urllib.error.HTTPError) and e.code < 500):
                raise
            log("  " + url + ": " + repr(e)[:80] + ", trying again")
            time.sleep(3)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("windows-1250", errors="ignore")
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


KEYWORDS = ("radno vrijeme", "gra\u0111an", "gradjan", "rekreativ", "plivanje za", "termin", "obavijest",
            "zatvoren", "ponedjeljak", "subota", "nedjelja", "praznik", "sati")


TEMPLATE_URL = OFFICIAL + "bazeni/1361"   # a generic page of the site: its lines are the menu, the news, the footer


def fetch_template_lines():
    """The lines every page of sportskiobjekti.hr shares (the menu of all objects, the news, the
    footer): about 19,000 of a pool page's 24,000 characters. Removed from each pool page, so Groq
    reads the pool's own text only. Empty when the fetch fails (then the keyword trim does its best)."""
    try:
        return set(l.strip() for l in fetch_page(TEMPLATE_URL).splitlines() if l.strip())
    except Exception as e:
        log("template page not fetched (" + repr(e) + "), sending the keyword windows instead")
        return set()


def own_text(text, template_lines):
    if not template_lines:
        return text
    kept = [l for l in text.splitlines() if l.strip() and l.strip() not in template_lines]
    return "\n".join(kept)


def trim_text(text, limit=SNIPPET_CHARS):
    """The part of the page that talks about hours: windows around the keywords, in page order,
    joined and capped, so a call costs a fraction of the whole page (the free tier counts tokens)."""
    low = text.lower()
    spans = []
    for kw in KEYWORDS:
        i = low.find(kw)
        while i >= 0 and len(spans) < 40:
            spans.append((max(0, i - 500), min(len(text), i + 900)))
            i = low.find(kw, i + len(kw))
    if not spans:
        return text[:limit]
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    out = " ... ".join(text[a:b] for a, b in merged)
    return out[:limit]


def prompts(page_text, pool_name, today_iso, weekday_hr, is_holiday, template_lines=frozenset(), limit=SNIPPET_CHARS):
    """The system and user text for the extractor: today's public-swim hours, the week as a compact
    list, a notice. Strict JSON back."""
    own = own_text(page_text, template_lines)
    snippet = own if len(own) <= limit else trim_text(own, limit)
    system = (
        "You read Croatian municipal swimming-pool web pages and extract the "
        "public-swim hours (termini za gradjanstvo, rekreativno plivanje) for a specific day and for "
        "the whole week. Answer with strict minified JSON only, no markdown, no comments."
    )
    user = (
        f"Pool: {pool_name}\n"
        f"Today is {today_iso}, weekday in Croatian: {weekday_hr}, "
        f"public holiday today: {'yes' if is_holiday else 'no'}.\n\n"
        "From the page text below, extract the public-swim hours for the general public "
        "(gradjanstvo), taking into account the weekday, any dated notices (obavijest), seasonal "
        "(ljetni/zimski) schedules, and holidays.\n"
        "Return JSON with exactly these keys:\n"
        '{"today_ranges": [["HH:MM","HH:MM"]], "closed_today": false, '
        '"week": [{"days": "Mon-Fri", "hours": "06:30-20:00"}, {"days": "Sat-Sun", "hours": "08:00-20:00"}], '
        '"notice": "", "confidence": "high|medium|low"}\n'
        "Rules: use 24h HH:MM. today_ranges = the ranges that apply TODAY. If closed today, "
        "today_ranges=[] and closed_today=true. If you cannot tell, today_ranges=[] and "
        "closed_today=null and confidence=low.\n"
        "week = the CURRENT schedule for the general public, one entry per group of days with the same "
        "hours, in week order, as compact as possible: English day abbreviations Mon Tue Wed Thu Fri Sat "
        "Sun, ranges like Mon-Fri, Sat-Sun, single days like Sat; several ranges in one day joined with "
        "a comma (\"06:30-09:00, 12:00-20:00\"); a day the pool is closed to the public gets hours "
        "\"closed\"; a public-holiday rule gets days \"Holidays\". Use the schedule in force now (the "
        "season that includes today); leave out lessons, clubs, schools, and anything not for the "
        "public. If the page has no weekly schedule, week=[].\n"
        "notice = one short sentence (max 160 chars) about any current/holiday/event "
        "change relevant today, else empty string.\n\n"
        "PAGE TEXT:\n" + snippet
    )
    return system, user


def call_claude(key, page_text, pool_name, today_iso, weekday_hr, is_holiday, template_lines=frozenset()):
    """Claude Haiku through the Messages API (raw HTTP: this file is standard library only, like the
    rest of the app; the machine installs no packages). One attempt after a 429 or a 5xx."""
    system, user = prompts(page_text, pool_name, today_iso, weekday_hr, is_holiday, template_lines, CLAUDE_MAX_CHARS)
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": 1024,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    last = None
    for attempt in range(3):
        req = urllib.request.Request(CLAUDE_URL, data=payload, headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "shopfinder-pools/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            last = e
            if e.code in (429, 500, 502, 503, 529) and attempt < 2:
                wait = e.headers.get("retry-after")
                secs = float(wait) if wait and wait.replace(".", "", 1).isdigit() else 8.0 * (attempt + 1)
                log("  %d from Claude (%s), waiting %.0f s" % (e.code, body[:120].replace("\n", " "), min(secs, 60)))
                time.sleep(min(secs, 60))
                continue
            log("  Claude answered %d: %s" % (e.code, body[:300].replace("\n", " ")))
            raise
    else:
        raise last or RuntimeError("Claude did not answer")
    if data.get("stop_reason") == "refusal":
        raise RuntimeError("Claude declined the page")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def call_groq(key, page_text, pool_name, today_iso, weekday_hr, is_holiday, template_lines=frozenset()):
    """The fallback extractor when there is no Anthropic key: Groq, strict JSON."""
    system, user = prompts(page_text, pool_name, today_iso, weekday_hr, is_holiday, template_lines)
    last = None
    for model in GROQ_MODELS:
        for attempt in range(4):
            try:
                return call_groq_model(key, model, system, user)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")
                last = e
                if e.code in (400, 404) and "model" in body and ("not exist" in body or "not_found" in body or "decommissioned" in body):
                    log("  model " + model + " is not available, trying the next")
                    break
                if e.code == 429 and attempt < 3:
                    wait = e.headers.get("retry-after")
                    m = re.search(r"try again in ([\d.]+)\s*(m|s)", body)
                    secs = float(wait) if wait and wait.replace(".", "", 1).isdigit() else (
                        float(m.group(1)) * (60 if m.group(2) == "m" else 1) if m else 12.0)
                    secs = min(max(secs + 1, 3), 90)
                    log("  429 from Groq (" + body[:120].replace("\n", " ") + "), waiting %.0f s" % secs)
                    time.sleep(secs)
                    continue
                raise
    raise last or RuntimeError("no Groq model answered")


def call_groq_model(key, model, system, user):
    payload = json.dumps({
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    # Groq's edge answers 403 to the bare Python-urllib agent (seen 12.9.2026): name the app instead.
    req = urllib.request.Request(GROQ_URL, data=payload, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; shopfinder-pools/1.0)",
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?|```$", "", content.strip()).strip()
    return json.loads(content)


def compute_open_now(ranges, now):
    """True/False from today's ranges against the time now; None when unknown."""
    if not ranges:
        return None
    mins = now.hour * 60 + now.minute
    for r in ranges:
        try:
            s_h, s_m = map(int, r[0].split(":"))
            e_h, e_m = map(int, r[1].split(":"))
        except Exception:
            continue
        if s_h * 60 + s_m <= mins < e_h * 60 + e_m:
            return True
    return False


def hours_text(ranges, closed_today):
    if closed_today is True:
        return "Closed"
    if not ranges:
        return "Unknown"
    return ", ".join(r[0] + "-" + r[1] for r in ranges)


def week_list(raw):
    """The weekly schedule as the page shows it: [{"days": "Mon-Fri", "hours": "06:30-20:00"}, ...],
    at most eight short entries, anything odd dropped rather than shown."""
    out = []
    for item in (raw or [])[:8]:
        if not isinstance(item, dict):
            continue
        days = str(item.get("days") or "").strip()[:24]
        hours = str(item.get("hours") or "").strip()[:60]
        if days and hours:
            out.append({"days": days, "hours": hours})
    return out


def process_pool(extract, p, now, today_iso, weekday_hr, is_holiday, template_lines=frozenset()):
    """One pool: fetch its page, extract the hours. Runs in a worker thread."""
    entry = {
        "id": p["id"], "name": p["name"], "addr": p["addr"],
        "lat": p["lat"], "lng": p["lng"], "url": p["url"],
        "open_now": None, "today_hours": "Unknown", "week": [], "notice": "",
    }
    try:
        log("fetching " + p["name"])
        text = fetch_page(p["url"])
        res = extract(text, p["name"], today_iso, weekday_hr, is_holiday, template_lines)
        ranges = res.get("today_ranges") or []
        closed = res.get("closed_today", None)
        entry["open_now"] = (False if closed is True else compute_open_now(ranges, now))
        entry["today_hours"] = hours_text(ranges, closed)
        entry["week"] = week_list(res.get("week"))
        entry["notice"] = (res.get("notice") or "").strip()[:200]
        log("  -> " + p["name"] + ": " + entry["today_hours"] +
            ("  week: " + "; ".join(w["days"] + " " + w["hours"] for w in entry["week"]) if entry["week"] else "  (no week)") +
            (" | " + entry["notice"] if entry["notice"] else ""))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        log("  HTTP error " + str(e.code) + " for " + p["name"] + (": " + body if body else ""))
    except Exception as e:
        log("  error for " + p["name"] + ": " + repr(e))
    return entry


def main():
    if anthropic_key():
        akey = anthropic_key()
        extract = lambda *a: call_claude(akey, *a)            # noqa: E731
        source = "sportskiobjekti.hr via Claude (" + CLAUDE_MODEL + ")"
        log("extractor: Claude " + CLAUDE_MODEL)
    elif groq_key():
        gkey = groq_key()
        extract = lambda *a: call_groq(gkey, *a)              # noqa: E731
        source = "sportskiobjekti.hr via Groq extraction"
        log("extractor: Groq (no Anthropic key at " + os.path.join(DATA_DIR, "anthropic_key") + ")")
    else:
        log("no key: set ANTHROPIC_API_KEY or write it to " + os.path.join(DATA_DIR, "anthropic_key") +
            " (or GROQ_API_KEY / groq_key as the fallback)")
        sys.exit(2)
    now = datetime.datetime.now()
    today_iso = now.strftime("%Y-%m-%d")
    weekday_hr = DAYS_HR[(now.weekday() + 1) % 7]
    is_holiday = today_iso in HOLIDAYS      # the weekday name already says weekend; a weekend is not a holiday

    template_lines = fetch_template_lines()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process_pool, extract, p, now, today_iso, weekday_hr, is_holiday, template_lines): i
                   for i, p in enumerate(POOLS)}
        results = [None] * len(POOLS)
        for fut in concurrent.futures.as_completed(futures):
            results[futures[fut]] = fut.result()

    payload = {
        "updated": now.astimezone().isoformat(timespec="minutes"),
        "source": source,
        "pools": results,
    }
    out_dir = os.path.dirname(OUT_PATH)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUT_PATH)
    log("wrote " + OUT_PATH)


if __name__ == "__main__":
    main()
