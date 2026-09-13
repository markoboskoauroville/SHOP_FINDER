#!/usr/bin/env python3
"""TEST 1 - the mechanism, alone. selfupdate against a throwaway 'GitHub' (a bare repo), the week
list and today's open/closed arithmetic of update_pools.py, and the page's own arithmetic (the B/N
distances, the pool order, the report grouping) run in node with a stub localStorage. No server."""
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import APP, check, finish, make_clone, bump_remote, git  # noqa: E402

# --- selfupdate: the check, the confirm, the pull -------------------------------------------------
bare, work, clone = make_clone(version=1)
sys.path.insert(0, clone)
import selfupdate  # noqa: E402  (the copy in the clone: HERE is the clone)

info = selfupdate.check_remote()
check("v1 clone, v1 on origin: up to date", info["up_to_date"] and info["installed"] == 1 and info["latest"] == 1, info)
check("perform_update with nothing to pull says so", "latest" in selfupdate.perform_update() or "up to date" in selfupdate.perform_update().lower())

bump_remote(work, 2, "v2")
info = selfupdate.check_remote()
check("v2 on origin: not up to date, 1 -> 2", (not info["up_to_date"]) and info["installed"] == 1 and info["latest"] == 2 and info["behind"] == 1, info)
check("the check did not touch the working tree", "APP_VERSION = 1" in open(os.path.join(clone, "version.py")).read())
msg = selfupdate.perform_update()
check("perform_update pulled v2", "APP_VERSION = 2" in open(os.path.join(clone, "version.py")).read(), msg)
check("its message is one line", "\n" not in msg and msg, msg)

# a commit on origin without a version bump: behind, and therefore not up to date (both facts count)
with open(os.path.join(work, "README.tmp"), "w") as f:
    f.write("x")
git(work, "add", "-A"); git(work, "commit", "-q", "-m", "no bump"); git(work, "push", "-q", "origin", "main")
info = selfupdate.check_remote()
check("same number, one commit behind: not up to date", (not info["up_to_date"]) and info["behind"] == 1, info)

# a local change that blocks a fast-forward: the pull refuses and says so, nothing half-changed
selfupdate.perform_update()
with open(os.path.join(clone, "version.py"), "a") as f:
    f.write("# local edit\n")
git(clone, "commit", "-q", "-am", "local")
bump_remote(work, 3, "v3")
try:
    selfupdate.perform_update()
    check("diverged clone: pull refused", False, "no error raised")
except selfupdate.UpdateError as e:
    check("diverged clone: pull refused with a plain message", "git pull failed" in str(e), e)
check("the local commit survived", "# local edit" in open(os.path.join(clone, "version.py")).read())

# unreachable origin
git(clone, "remote", "set-url", "origin", "/nonexistent/origin.git")
try:
    selfupdate.check_remote()
    check("unreachable origin: error", False, "no error raised")
except selfupdate.UpdateError as e:
    check("unreachable origin: 'could not reach GitHub'", "could not reach" in str(e), e)

# not a checkout
import shutil
shutil.rmtree(os.path.join(clone, ".git"))
try:
    selfupdate.check_remote()
    check("no .git: error", False, "no error raised")
except selfupdate.UpdateError as e:
    check("no .git: says it is not a checkout", "not a git checkout" in str(e), e)

# --- update_pools: the week list and today's arithmetic -------------------------------------------
sys.path.insert(0, APP)
import importlib.util
spec = importlib.util.spec_from_file_location("update_pools", os.path.join(APP, "update_pools.py"))
up = importlib.util.module_from_spec(spec); spec.loader.exec_module(up)
w = up.week_list([{"days": "Mon-Fri", "hours": "06:30-20:00"}, {"days": "", "hours": "x"}, "junk", None,
                  {"days": "Sat-Sun", "hours": "08:00-20:00"}, {"days": "D" * 50, "hours": "H" * 90}])
check("week_list keeps well-formed entries, drops junk", [x["days"] for x in w][:2] == ["Mon-Fri", "Sat-Sun"], w)
check("week_list caps lengths", len(w[2]["days"]) == 24 and len(w[2]["hours"]) == 60)
check("week_list of None is []", up.week_list(None) == [])
check("week_list keeps at most 8", len(up.week_list([{"days": "d", "hours": "h"}] * 12)) == 8)
t = lambda h, m: datetime.datetime(2026, 9, 13, h, m)  # noqa: E731
check("open at the start minute", up.compute_open_now([["06:30", "20:00"]], t(6, 30)) is True)
check("closed at the end minute", up.compute_open_now([["06:30", "20:00"]], t(20, 0)) is False)
check("closed the minute before opening", up.compute_open_now([["06:30", "20:00"]], t(6, 29)) is False)
check("no ranges: unknown", up.compute_open_now([], t(12, 0)) is None)
check("a broken range is skipped", up.compute_open_now([["x", "y"], ["12:00", "13:00"]], t(12, 30)) is True)
check("hours_text: closed", up.hours_text([], True) == "Closed")
check("hours_text: two ranges", up.hours_text([["06:00", "14:00"], ["15:00", "20:00"]], False) == "06:00-14:00, 15:00-20:00")
sysm, user = up.prompts("Radno vrijeme za gradjanstvo ...", "Bazen X", "2026-09-13", "nedjelja", False)
check("the prompt asks for the week and today's ranges", '"week"' in user and "today_ranges" in user and "Mon-Fri" in user)
check("the model is Haiku by default", up.CLAUDE_MODEL.startswith("claude-haiku"), up.CLAUDE_MODEL)

# --- the page's arithmetic, in node ---------------------------------------------------------------
html = open(os.path.join(APP, "public", "index.html"), encoding="utf-8").read()
js = html[html.index("<script>") + 8:html.rindex("</script>")]
def fn(name):
    m = re.search(r"\n(function %s\([^)]*\) \{.*?\n\})\n" % re.escape(name), js, re.S)
    assert m, name
    return m.group(1)
consts = "\n".join(re.search(r"\n(const %s = .*?;)\n" % c, js, re.S).group(1) for c in ("LANDMARKS", "PRIORITY_POOL", "VISITS_KEY"))
pools = re.search(r"\nconst POOLS = \[.*?\n\];", js, re.S).group(0).replace("OFFICIAL + ", "'' + ")
snippet = """
const store = {}; const localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
const openStats = new Set(); function setStatus(){}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmtUpdated(d){return d.toISOString();}
%s
%s
%s
%s
%s
%s
%s
%s
%s
%s
%s
%s
%s
const out = {};
// 1. a shop on Britanski trg itself: B 0.0; Nova TV from there is 6.75 km
out.tailAtB = shopTitleTail({ name: "Spar", street: "Britanski trg 1", lat: 45.81314, lng: 15.96501 });
out.tailNoStreet = shopTitleTail({ name: "Spar", street: "", lat: 45.75517, lng: 15.99101 });
out.kmBN = distMeters(LANDMARKS[0], LANDMARKS[1]);
// 2. the pool order: no visits -> Spansko first, then by distance
const pools = ["pool-iver", "pool-utrine", "pool-spansko"].map((id, i) => ({ id, isPool: true, dist: 1000 - i * 100 }));
out.orderNoVisits = pools.slice().sort(poolOrder()).map(p => p.id);
addVisit("pool-iver"); addVisit("pool-iver"); addVisit("pool-utrine");
out.orderVisits = pools.slice().sort(poolOrder()).map(p => p.id);
out.counts = visitCounts();
// 3. the numbers and the report grouping
const v = loadVisits(); v[0].at = "2026-08-02T10:00:00.000Z"; v[0].h = 1.5; v[0].km = 2; v[0].laps = 40; v[0].eur = 5;
v[1].at = "2026-08-20T10:00:00.000Z"; v[1].h = 1; v[1].km = 1; v[1].laps = 20; v[1].eur = 4.5;
v[2].at = "2025-12-31T10:00:00.000Z"; v[2].h = 2; v[2].km = 3; v[2].laps = 60; v[2].eur = 6; saveVisits(v);
out.sum = sumVisits(loadVisits());
out.byMonth = reportTable(loadVisits(), "month", false);
out.byYear = reportTable(loadVisits(), "year", true);
updateVisit(v[2].id, "eur", "-4"); out.negativeClamped = loadVisits()[2].eur;
updateVisit(v[2].id, "km", "abc"); out.junkIsZero = loadVisits()[2].km;
deleteVisit(v[2].id); out.afterDelete = loadVisits().length;
out.emptyReport = reportTable([], "month", false);
console.log(JSON.stringify(out));
""" % (consts, pools, fn("distMeters"), fn("kmPlain"), fn("shopTitleTail"), fn("loadVisits"), fn("saveVisits"), fn("num"),
       fn("visitCounts"), fn("poolName"), fn("addVisit"), fn("updateVisit"), fn("deleteVisit"))
snippet += "\n".join(fn(n) for n in ("poolOrder", "sumVisits", "fmtN", "periodKey", "periodLabel", "totalsRow", "reportTable")) 
# the functions above are appended after use in the template: hoist them by putting them first
snippet = "\n".join(fn(n) for n in ("poolOrder", "sumVisits", "fmtN", "periodKey", "periodLabel", "totalsRow", "reportTable")) + snippet
p = subprocess.run(["node", "-e", snippet], capture_output=True, text=True, timeout=30)
if p.returncode != 0:
    check("the page's functions run in node", False, p.stderr[-400:])
else:
    o = json.loads(p.stdout.strip().splitlines()[-1])
    check("B/N: a shop on British Square reads (B 0.0 · N 6.8)", "(B 0.0 · N 6.8)" in o["tailAtB"] and "Britanski trg 1" in o["tailAtB"], o["tailAtB"])
    check("B/N: a shop at Nova TV reads N 0.0", "N 0.0)" in o["tailNoStreet"] and "street" not in o["tailNoStreet"], o["tailNoStreet"])
    check("B to N is 6.75 km (measured on the map, 13.9.2026)", 6700 < o["kmBN"] < 6800, o["kmBN"])
    check("no visits: Špansko first, then the nearest", o["orderNoVisits"] == ["pool-spansko", "pool-utrine", "pool-iver"], o["orderNoVisits"])
    check("visits decide: 2 visits before 1 before Špansko", o["orderVisits"] == ["pool-iver", "pool-utrine", "pool-spansko"], o["orderVisits"])
    check("sum of three visits", o["sum"] == {"n": 3, "h": 4.5, "km": 6, "laps": 120, "eur": 15.5}, o["sum"])
    check("by month: Aug 2026 has 2 visits, Dec 2025 has 1, newest first", o["byMonth"].index("Aug 2026") < o["byMonth"].index("Dec 2025") and "<td>Aug 2026</td><td>2</td>" in o["byMonth"], o["byMonth"])
    check("by year with the per-pool split", "<td>2026</td><td>2</td>" in o["byYear"] and "Bazen Iver" in o["byYear"], o["byYear"])
    check("a negative euro entry is clamped to 0", o["negativeClamped"] == 0)
    check("a non-number entry is 0", o["junkIsZero"] == 0)
    check("delete removes one", o["afterDelete"] == 2)
    check("an empty log says 'no visits yet'", "no visits yet" in o["emptyReport"])

finish("test1_mechanism")
