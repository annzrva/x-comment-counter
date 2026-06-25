#!/usr/bin/env python3
"""
X Comment Counter — Duolingo-style tracker for daily X activity.

Multi-handle: anyone can type a handle and see that account's replies
(comments), posts, streak and a contribution graph, computed via twitterapi.io.

Cost controls (public-safe):
  • per-handle cache (cache_ttl_minutes) — repeat views & shared links are free
  • short backfill for a fresh handle (new_handle_backfill_days)
  • hard daily call cap (daily_call_cap) — worst case is bounded, not unbounded

Run:
    python3 app.py                 # server + open browser
    python3 app.py --port 8765
    python3 app.py --refresh [h]   # print today's numbers for handle h (no server)
    python3 app.py --backfill 90 [h]  # fetch ~90 days of history for the graph

Goals & limits live in config.json. Per-handle history lives in data/<handle>.json.
"""

import argparse
import json
import os
import re
import sys
import time
import threading
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# this module lives in api/ — config.json / data/ live one level up (repo root)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HERE, "data")
CONFIG_PATH = os.path.join(HERE, "config.json")
USAGE_PATH = os.path.join(HERE, "usage.json")

BASE = "https://api.twitterapi.io"
MIN_INTERVAL = 0.34  # ~3 QPS, polite
_last_call = [0.0]

IMG_HOSTS = {"pbs.twimg.com", "abs.twimg.com"}

DEFAULT_CONFIG = {
    "handle": "burninganna",      # owner handle (CLI default + "made by" credit)
    "comments_goal": 10,          # streak floor: hit this (+post) to keep the streak alive
    "comments_stretch": 20,       # stretch goal: hit this for the brightest graph tile
    "posts_goal": 1,
    "lookback_days": 4,           # days re-fetched on each quick refresh
    "graph_days": 90,             # contribution graph window (90 = quarter, 365 = year)
    "exceed_multiplier": 1.5,     # comments >= goal*this => "exceeded" (brightest green)
    "timezone_name": "America/Los_Angeles",  # IANA tz for the day boundary (DST-aware); owner's tz
    "timezone_offset_hours": None,           # fixed-offset fallback if timezone_name is unset/unavailable
    "author": "burninganna",      # creator handle for the "made by" credit / follow link
    "site_url": "",               # no extra branding — credit is just the @author link
    "share_cta": "Can you beat my streak?",
    # ── public cost controls ──
    "cache_ttl_minutes": 360,        # a handle's data is "fresh" for this long → no API call
    "new_handle_backfill_days": 14,  # history depth fetched the first time a handle is seen (matches the 14-day heatmap)
    "daily_call_cap": 1500,          # hard ceiling on twitterapi.io calls per day
    "rate_per_ip_per_min": 8,        # new lookups per IP per minute
}


# ── errors ────────────────────────────────────────────────────────────────

class BudgetExceeded(Exception):
    """Daily API budget cap reached."""


class InvalidHandle(Exception):
    """Handle is empty or no such X account."""


# ── config / storage ──────────────────────────────────────────────────────

_DAILY_CAP = [DEFAULT_CONFIG["daily_call_cap"]]


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    merged = dict(DEFAULT_CONFIG); merged.update(cfg)
    if merged != cfg or not os.path.exists(CONFIG_PATH):
        cfg = merged
    try:  # read-only filesystem (e.g. Vercel) → just skip persisting
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
    _DAILY_CAP[0] = cfg.get("daily_call_cap", DEFAULT_CONFIG["daily_call_cap"])
    return cfg


def sanitize_handle(h):
    """Accept '@name', 'name', or an x.com/twitter.com URL → bare lowercase handle."""
    h = (h or "").strip()
    if "x.com/" in h or "twitter.com/" in h:
        h = h.rstrip("/").split("/")[-1]
    h = h.lstrip("@").strip()
    h = re.sub(r"[^A-Za-z0-9_]", "", h)
    return h.lower()[:15]


def data_path(handle):
    return os.path.join(DATA_DIR, f"{sanitize_handle(handle)}.json")


# ── storage backend: Redis (Upstash / Vercel KV) in prod, local files in dev ──
# Auto-detected from env. On Vercel the filesystem is read-only, so per-handle
# cache + the daily budget counter must live in an external key-value store.

def _kv_creds():
    url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    tok = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    return (url, tok) if url and tok else (None, None)


def _use_kv():
    return _kv_creds()[0] is not None


def kv_cmd(*args):
    """Run one Redis command via the Upstash REST API. Returns the `result`."""
    url, tok = _kv_creds()
    body = json.dumps([str(a) for a in args]).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode()).get("result")


_EMPTY = {"days": {}, "last_refresh": None}


def load_data(handle):
    handle = sanitize_handle(handle)
    if _use_kv():
        try:
            raw = kv_cmd("GET", "cc:data:" + handle)
            return json.loads(raw) if raw else dict(_EMPTY)
        except Exception:
            return dict(_EMPTY)
    p = data_path(handle)
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return dict(_EMPTY)


def save_data(handle, data):
    handle = sanitize_handle(handle)
    if _use_kv():
        kv_cmd("SET", "cc:data:" + handle, json.dumps(data, ensure_ascii=False))
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(data_path(handle), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_key():
    key = os.environ.get("TWITTERAPI_KEY")
    if not key:
        env_path = os.path.join(HERE, ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("TWITTERAPI_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    if not key:
        sys.exit("❌ No API key. Put TWITTERAPI_KEY=... in .env")
    return key


# ── daily budget guard ────────────────────────────────────────────────────

_usage_lock = threading.Lock()


def _record_call():
    """Count one API call against today's cap; raise BudgetExceeded if over."""
    day = datetime.now().strftime("%Y-%m-%d")
    if _use_kv():
        key = "cc:usage:" + day
        n = kv_cmd("INCR", key)
        try:
            n = int(n)
        except (TypeError, ValueError):
            return
        if n == 1:
            kv_cmd("EXPIRE", key, 172800)  # auto-clean after 2 days
        if n > _DAILY_CAP[0]:
            raise BudgetExceeded("Daily API budget reached — try again tomorrow.")
        return
    with _usage_lock:
        try:
            with open(USAGE_PATH) as f:
                u = json.load(f)
        except Exception:
            u = {}
        n = u.get(day, 0)
        if n >= _DAILY_CAP[0]:
            raise BudgetExceeded("Daily API budget reached — try again tomorrow.")
        u[day] = n + 1
        cutoff = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        u = {k: v for k, v in u.items() if k >= cutoff}
        with open(USAGE_PATH, "w") as f:
            json.dump(u, f)


def calls_today():
    day = datetime.now().strftime("%Y-%m-%d")
    if _use_kv():
        try:
            return int(kv_cmd("GET", "cc:usage:" + day) or 0)
        except Exception:
            return 0
    try:
        with open(USAGE_PATH) as f:
            return json.load(f).get(day, 0)
    except Exception:
        return 0


# ── twitterapi.io ─────────────────────────────────────────────────────────

def _throttle():
    wait = MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def call(path, params, _retries=5):
    _record_call()
    url = f"{BASE}{path}?" + urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"X-API-Key": load_key()})
    _throttle()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429 and _retries > 0:
            time.sleep(2 ** (6 - _retries))
            return call(path, params, _retries - 1)
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network: {e.reason}")
    if isinstance(data, dict) and data.get("status") == "error":
        raise RuntimeError(f"API: {data.get('msg', 'unknown error')}")
    return data


def search(query, cursor=""):
    return call("/twitter/tweet/advanced_search",
                {"query": query, "queryType": "Latest", "cursor": cursor})


def user_info(handle):
    return call("/twitter/user/info", {"userName": handle})


# ── date helpers ──────────────────────────────────────────────────────────

def local_tz(cfg):
    """Resolve the tz used to bucket tweets into days and to define "today".

    Priority: IANA name (DST-aware) → fixed UTC offset → server local tz.
    The server-tz fallback is UTC on Vercel, which rolls "today" over at the
    wrong moment for the owner — so pin timezone_name in config.json.
    """
    name = cfg.get("timezone_name")
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception:
            pass
    off = cfg.get("timezone_offset_hours")
    if off is not None:
        return timezone(timedelta(hours=off))
    return datetime.now().astimezone().tzinfo


def parse_created(created_at):
    return datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")


def day_key(dt, tz):
    return dt.astimezone(tz).strftime("%Y-%m-%d")


# ── core: fetch & count ───────────────────────────────────────────────────

def fetch_counts(handle, since_dt, tz, max_pages, want_posts=True):
    """Return {date_str: {comments, posts}} for [since_dt, now]."""
    counts = {}
    q_since = since_dt.strftime("%Y-%m-%d")

    def collect(query, field):
        cursor, pages = "", 0
        while pages < max_pages:
            data = search(query, cursor)
            batch = data.get("tweets") or []
            if not batch:
                break
            stop = False
            for t in batch:
                try:
                    dt = parse_created(t["createdAt"])
                except Exception:
                    continue
                if dt < since_dt:
                    stop = True
                    break
                k = day_key(dt, tz)
                counts.setdefault(k, {"comments": 0, "posts": 0})
                counts[k][field] += 1
            if stop or not data.get("has_next_page"):
                break
            cursor = data.get("next_cursor", "")
            if not cursor:
                break
            pages += 1

    collect(f"from:{handle} filter:replies since:{q_since}", "comments")
    if want_posts:
        collect(f"from:{handle} -filter:replies since:{q_since}", "posts")
    return counts


def fetch_profile(handle):
    try:
        raw = user_info(handle)
    except Exception:
        return None
    u = raw.get("data", raw) if isinstance(raw, dict) else {}
    if not u:
        return None
    cover = u.get("coverPicture") or ""
    if cover and "/profile_banners/" in cover and not cover.rstrip("/").split("/")[-1].count("x"):
        cover = cover.rstrip("/") + "/1500x500"
    return {
        "name": u.get("name", ""),
        "bio": u.get("description") or "",
        "avatar": (u.get("profilePicture") or "").replace("_normal", "_400x400"),
        "cover": cover,
        "verified": bool(u.get("isBlueVerified") or u.get("isVerified")),
        "followers": u.get("followers"),
        "following": u.get("following"),
    }


def _midnight_since(tz, days):
    return (datetime.now(tz) - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0)


def first_fetch(cfg, handle, data):
    """First time a handle is seen: validate it, pull profile + N days of history."""
    handle = sanitize_handle(handle)
    prof = fetch_profile(handle)
    if not prof:
        raise InvalidHandle(f"@{handle} — no such X account")
    tz = local_tz(cfg)
    since = _midnight_since(tz, cfg.get("new_handle_backfill_days", 30))
    fresh = fetch_counts(handle, since, tz, max_pages=200)
    data.setdefault("days", {})
    for k, v in fresh.items():
        data["days"][k] = v
    today = datetime.now(tz).strftime("%Y-%m-%d")
    data["days"].setdefault(today, {"comments": 0, "posts": 0})
    data["profile"] = prof
    data["last_refresh"] = datetime.now(tz).isoformat(timespec="seconds")
    save_data(handle, data)
    return data


def refresh(cfg, handle, data):
    """Quick top-up of the last few days for a handle we already track."""
    handle = sanitize_handle(handle)
    tz = local_tz(cfg)
    since = _midnight_since(tz, cfg["lookback_days"])
    fresh = fetch_counts(handle, since, tz, 40)
    data.setdefault("days", {})
    for k, v in fresh.items():
        data["days"][k] = v
    today = datetime.now(tz).strftime("%Y-%m-%d")
    data["days"].setdefault(today, {"comments": 0, "posts": 0})
    prof = fetch_profile(handle)
    if prof:
        data["profile"] = prof
    data["last_refresh"] = datetime.now(tz).isoformat(timespec="seconds")
    save_data(handle, data)
    return data


def backfill(cfg, handle, data, days):
    """Deep history fetch for the contribution graph (CLI / owner)."""
    handle = sanitize_handle(handle)
    tz = local_tz(cfg)
    since = _midnight_since(tz, days)
    fresh = fetch_counts(handle, since, tz, max_pages=600)
    data.setdefault("days", {})
    for k, v in fresh.items():
        data["days"][k] = v
    prof = fetch_profile(handle)
    if prof:
        data["profile"] = prof
    data["last_refresh"] = datetime.now(tz).isoformat(timespec="seconds")
    save_data(handle, data)
    return data


# ── gamification: streak + graph ──────────────────────────────────────────

def day_met_goal(day, cfg):
    return (day.get("comments", 0) >= cfg["comments_goal"]
            and day.get("posts", 0) >= cfg["posts_goal"])


def day_level(day, cfg):
    """0 none · 1 partial (below floor) · 2 met floor · 3 hit stretch."""
    c, p = day.get("comments", 0), day.get("posts", 0)
    if c == 0 and p == 0:
        return 0
    if not day_met_goal(day, cfg):
        return 1
    if c >= cfg.get("comments_stretch", cfg["comments_goal"] * 2):
        return 3
    return 2


def compute_streak(data, cfg):
    tz = local_tz(cfg)
    today = datetime.now(tz).date()
    days = data["days"]
    if day_met_goal(days.get(today.strftime("%Y-%m-%d"), {}), cfg):
        anchor = today
    else:
        anchor = today - timedelta(days=1)
    streak, d = 0, anchor
    while day_met_goal(days.get(d.strftime("%Y-%m-%d"), {}), cfg):
        streak += 1
        d -= timedelta(days=1)
    best, run, prev = 0, 0, None
    for ds in sorted(days.keys()):
        cur = datetime.strptime(ds, "%Y-%m-%d").date()
        if not day_met_goal(days[ds], cfg):
            run, prev = 0, cur
            continue
        run = run + 1 if (prev and (cur - prev).days == 1 and run > 0) else 1
        best = max(best, run)
        prev = cur
    return streak, best


def build_state(cfg, handle, data):
    handle = sanitize_handle(handle)
    tz = local_tz(cfg)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    today_d = data["days"].get(today, {"comments": 0, "posts": 0})
    streak, best = compute_streak(data, cfg)

    base = datetime.now(tz).date()
    graph, total_met = [], 0
    for i in range(cfg["graph_days"] - 1, -1, -1):
        ds = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        d = data["days"].get(ds, {"comments": 0, "posts": 0})
        lvl = day_level(d, cfg)
        if lvl >= 2:
            total_met += 1
        graph.append({"date": ds, "comments": d.get("comments", 0),
                      "posts": d.get("posts", 0), "level": lvl})

    return {
        "handle": handle,
        "profile": data.get("profile", {}),
        "comments_goal": cfg["comments_goal"],
        "comments_stretch": cfg.get("comments_stretch", cfg["comments_goal"] * 2),
        "posts_goal": cfg["posts_goal"],
        "graph_days": cfg["graph_days"],
        "author": cfg.get("author", cfg["handle"]),
        "site_url": cfg.get("site_url", ""),
        "share_cta": cfg.get("share_cta", ""),
        "today": {
            "date": today,
            "comments": today_d.get("comments", 0),
            "posts": today_d.get("posts", 0),
            "met": day_met_goal(today_d, cfg),
        },
        "streak": streak,
        "best_streak": best,
        "days_tracked": len(data["days"]),
        "total_goal_days": total_met,
        "graph": graph,
        "last_refresh": data.get("last_refresh"),
    }


# ── orchestrator: cached, budget-aware lookup ─────────────────────────────

def is_fresh(data, cfg):
    lr = data.get("last_refresh")
    if not lr:
        return False
    try:
        t = datetime.fromisoformat(lr)
    except Exception:
        return False
    now = datetime.now(t.tzinfo) if t.tzinfo else datetime.now()
    return (now - t).total_seconds() < cfg.get("cache_ttl_minutes", 360) * 60


def lookup(cfg, handle, force=False):
    """Return state for a handle, hitting the API only when cache is stale/empty."""
    handle = sanitize_handle(handle)
    if not handle:
        raise InvalidHandle("Enter an X handle.")
    data = load_data(handle)
    has_cache = bool(data.get("days"))
    note = None
    served_cached = True
    if force or not is_fresh(data, cfg):
        try:
            data = refresh(cfg, handle, data) if has_cache else first_fetch(cfg, handle, data)
            served_cached = False
        except BudgetExceeded:
            if not has_cache:
                raise
            note = "budget"  # serve stale cache instead of failing
    st = build_state(cfg, handle, data)
    st["cached"] = served_cached
    st["fresh"] = is_fresh(data, cfg)
    if note:
        st["note"] = note
    return st


# ── HTTP server ───────────────────────────────────────────────────────────

def _with_graph(cfg, qs):
    gd = qs.get("graph_days")
    if not gd:
        return cfg
    c = dict(cfg)
    try:
        c["graph_days"] = max(1, min(366, int(gd[0])))
    except ValueError:
        pass
    return c


# very small in-memory per-IP rate limiter for fresh lookups
_rate_lock = threading.Lock()
_rate_hits = {}


def _rate_ok(ip, cfg):
    limit = cfg.get("rate_per_ip_per_min", 8)
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(ip, []) if now - t < 60]
        if len(hits) >= limit:
            _rate_hits[ip] = hits
            return False
        hits.append(now)
        _rate_hits[ip] = hits
        return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)
        cfg = load_config()
        try:
            if path == "/" or path.startswith("/index"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif path == "/api/lookup":
                self._lookup(cfg, qs)
            elif path == "/api/backfill":
                handle = qs.get("handle", [cfg["handle"]])[0]
                days = int(qs.get("days", [cfg["graph_days"]])[0])
                c = _with_graph(cfg, qs); c["graph_days"] = max(c["graph_days"], days)
                st = build_state(c, handle, backfill(cfg, handle, load_data(handle), days))
                self._send(200, json.dumps(st))
            elif path == "/img":
                self._proxy_img(qs.get("u", [""])[0])
            else:
                self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}))

    def _lookup(self, cfg, qs):
        handle = sanitize_handle(qs.get("handle", [cfg["handle"]])[0])
        force = qs.get("force", ["0"])[0] in ("1", "true", "yes")
        c = _with_graph(cfg, qs)
        # rate-limit only calls that may hit the API (no cache yet, or forced)
        will_fetch = force or not is_fresh(load_data(handle), cfg)
        if will_fetch:
            ip = self.client_address[0]
            if not _rate_ok(ip, cfg):
                self._send(429, json.dumps({"error": "Slow down a sec — too many lookups."}))
                return
        try:
            self._send(200, json.dumps(lookup(c, handle, force=force)))
        except InvalidHandle as e:
            self._send(200, json.dumps({"error": str(e), "invalid_handle": True}))
        except BudgetExceeded as e:
            self._send(200, json.dumps({"error": str(e), "budget": True}))

    def _proxy_img(self, u):
        if not u:
            self._send(400, b"no url"); return
        host = urllib.parse.urlparse(u).netloc
        if host not in IMG_HOSTS:
            self._send(403, b"host not allowed"); return
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "image/jpeg")
        except Exception as e:
            self._send(502, str(e).encode()); return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def serve(port):
    cfg = load_config()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"🔥 X Comment Counter (multi-handle) → {url}")
    print(f"   Goal: {cfg['comments_goal']} comments ({cfg.get('comments_stretch','?')} stretch) + {cfg['posts_goal']} post/day")
    print(f"   Cache {cfg['cache_ttl_minutes']}min · backfill {cfg['new_handle_backfill_days']}d · cap {cfg['daily_call_cap']}/day (used {calls_today()})")
    print("   Ctrl+C to stop.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 bye")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--refresh", nargs="?", const="", metavar="HANDLE",
                    help="print today's numbers for HANDLE (default: owner)")
    ap.add_argument("--backfill", type=int, metavar="DAYS",
                    help="fetch N days of history for the contribution graph")
    ap.add_argument("--handle", default=None, help="target handle for --backfill")
    a = ap.parse_args()
    cfg = load_config()
    if a.backfill:
        h = sanitize_handle(a.handle or cfg["handle"])
        print(f"⏳ backfilling {a.backfill} days for @{h}…")
        data = backfill(cfg, h, load_data(h), a.backfill)
        print(f"✅ done · {len(data['days'])} days now tracked")
        return
    if a.refresh is not None:
        h = sanitize_handle(a.refresh or cfg["handle"])
        st = lookup(cfg, h, force=True)
        t = st["today"]
        print(f"@{st['handle']} — {t['date']}")
        print(f"  💬 comments: {t['comments']}/{st['comments_goal']}")
        print(f"  📝 posts:    {t['posts']}/{st['posts_goal']}")
        print(f"  🔥 streak:   {st['streak']} days (best {st['best_streak']})")
        print(f"  {'✅ GOAL MET!' if t['met'] else '⏳ keep going'}")
        return
    serve(a.port)


if __name__ == "__main__":
    main()
