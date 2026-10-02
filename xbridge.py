#!/usr/bin/env python3
"""
xbridge.py — keeps the live tracker fed without twitterapi.io.

X data comes from Sasha's X connector (claude.ai MCP `mcp__claude_ai_X__*`), reached through the
local `claude` CLI in headless mode: Claude only makes the tool calls (no other tools), and we read
the raw tool results from the stream. Results are written straight into the prod KV (creds in
.env.bridge, pulled with `vercel env pull`), and prod (`remote_fetch: False`) just serves them.

Runs every 5 min via launchd (ai.varg.xbridge):
  every run   → new replies/posts since the last sync (since_time) → today's counts, replied ids/users
  hourly      → profile + follower count, newest followers diff
  every 45min → reply queue (≈14 searches over targets.json)

    python3 xbridge.py            # one sync pass
    python3 xbridge.py --all      # force profile + followers + queue too
"""

import argparse
import fcntl
import glob
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env(path):
    if not os.path.exists(path):
        sys.exit("❌ .env.bridge missing — run: npx vercel env pull .env.bridge --environment=production")
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"'))


_load_env(os.path.join(HERE, ".env.bridge"))
sys.path.insert(0, os.path.join(HERE, "api"))
import _core  # noqa: E402

HANDLE = "burninganna"
CLAUDE = os.path.expanduser("~/.local/bin/claude")
LOG = os.path.join(HERE, "logs", "bridge.log")
T_SEARCH, T_USER, T_FOLLOWERS = ("mcp__claude_ai_X__twitter_search", "mcp__claude_ai_X__twitter_get_user",
                                 "mcp__claude_ai_X__twitter_followers")
QUEUE_EVERY, PROFILE_EVERY = 45 * 60, 60 * 60


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


# ── MCP via headless claude ───────────────────────────────────────────────

def mcp(instructions, tool, timeout=240):
    """Let Claude (haiku, only `tool` allowed) make the calls; return every parsed tool result."""
    p = subprocess.run(
        [CLAUDE, "-p", "--model", "haiku", "--tools", "", "--allowedTools", tool,
         "--output-format", "stream-json", "--verbose", "--no-session-persistence"],
        input=instructions + "\nDo not do anything else. When finished reply only: DONE",
        capture_output=True, text=True, timeout=timeout)
    results = []
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") != "user":
            continue
        for c in (ev.get("message") or {}).get("content") or []:
            if not isinstance(c, dict) or c.get("type") != "tool_result":
                continue
            body = c.get("content")
            if isinstance(body, list):
                body = "".join(x.get("text", "") for x in body if isinstance(x, dict))
            try:
                results.append(json.loads(body))
            except (TypeError, ValueError):
                log(f"non-JSON tool result: {str(body)[:160]}")
    if not results:
        log(f"no tool results ({tool}): {p.stdout[-200:]} {p.stderr[-200:]}")
    return results


def search_all(query, max_calls):
    res = mcp(
        f'Call {T_SEARCH} with arguments {json.dumps({"query": query, "type": "Latest", "count": 100})}.\n'
        f"If the result has 20 items and a cursor.bottom, call it again with the same arguments plus "
        f'"cursor" set to that exact cursor.bottom string. Make at most {max_calls} calls in total.',
        T_SEARCH)
    out, seen = [], set()
    for r in res:
        for t in r.get("items") or []:
            if t.get("id") and t["id"] not in seen:
                seen.add(t["id"])
                out.append(t)
    return out


def _avatar_map():
    """Avatars/follower counts for queue authors (the connector's search omits them) from icp_build's cache."""
    files = sorted(glob.glob(os.path.expanduser("~/Developer/X growth/out/cache/icp_beh_*.json")))
    m = {}
    if files:
        for h, b in json.load(open(files[-1])).items():
            p = (b or {}).get("profile") or {}
            m[h.lower()] = (p.get("profilePicture") or "", p.get("followers"))
    return m


def to_twapi(t, avatars=None):
    """Connector tweet → the twitterapi.io shape _core expects."""
    a = t.get("author") or {}
    reply_to = t.get("in_reply_to_tweet_id")
    m = re.match(r"@(\w+)", t.get("text") or "") if reply_to else None
    av, fol = (avatars or {}).get((a.get("username") or "").lower(), ("", None))
    return {
        "id": str(t["id"]), "url": t.get("url"), "text": t.get("text") or "",
        "createdAt": t.get("created_at"), "isReply": bool(reply_to),
        "inReplyToId": reply_to, "inReplyToUsername": m.group(1) if m else None,
        "likeCount": t.get("likes", 0), "replyCount": t.get("replies", 0), "viewCount": t.get("views"),
        "author": {"userName": a.get("username", ""), "name": a.get("name", ""),
                   "profilePicture": av, "followers": fol},
    }


# ── sync steps ────────────────────────────────────────────────────────────

def sync_counts(cfg, data, tz):
    st = data.setdefault("bridge", {})
    seen = st.setdefault("seen", {})            # {date: {tweet_id: "comments"|"posts"|"q"}}
    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")
    if today not in seen or not st.get("last_sync"):
        since = int(_core._midnight_since(tz, 0).timestamp())
        calls = 15                               # first pass of the day: everything since midnight
        st["full_days"] = sorted(set(st.get("full_days", [])) | {today})[-3:]
    else:
        since = int(st["last_sync"]) - 300       # overlap; dedup by id
        calls = 4
    tweets = search_all(f"from:{HANDLE} since_time:{since}", calls)
    replied, users = _core._replied(data, tz), _core._replied_users(data, tz)
    for raw in tweets:
        if (raw.get("text") or "").startswith("RT @"):
            continue
        t = to_twapi(raw)
        try:
            k = _core.day_key(_core.parse_created(t["createdAt"]), tz)
        except Exception:
            continue
        kind = "comments" if t["isReply"] else "posts"
        if kind == "comments" and t["text"].rstrip().endswith("?"):
            kind = "q"                           # a comment that ends with a question
        seen.setdefault(k, {})[t["id"]] = kind
        if t["isReply"]:
            replied[str(t["inReplyToId"])] = k
            if t["inReplyToUsername"]:
                u = t["inReplyToUsername"].lower()
                users[u] = max(users.get(u, ""), k)
    for k, ids in seen.items():
        if k not in st.get("full_days", []):    # a partial day (e.g. overlap past midnight) must not overwrite
            continue
        v = list(ids.values())
        data.setdefault("days", {})[k] = {"comments": v.count("comments") + v.count("q"),
                                          "posts": v.count("posts"), "q": v.count("q")}
    data["days"].setdefault(today, {"comments": 0, "posts": 0, "q": 0})
    for k in sorted(seen)[:-3]:                  # keep 3 days of ids
        del seen[k]
    st["last_sync"] = time.time()
    return len(tweets)


def sync_profile(cfg, data, tz):
    res = mcp(f'Call {T_USER} with arguments {json.dumps({"username": HANDLE})}.', T_USER, timeout=120)
    u = res[0] if res else None
    if not u or not u.get("username"):
        return False
    old = data.get("profile") or {}
    data["profile"] = {
        "id": u.get("id"), "name": u.get("name", ""), "bio": u.get("description") or "",
        "avatar": (u.get("profile_image_url") or "").replace("_normal", "_400x400"),
        "cover": old.get("cover", ""), "verified": bool(u.get("verified")),
        "followers": u.get("followers"), "following": u.get("following"),
    }
    data["profile_ts"] = time.time()
    _core.log_followers(data, data["profile"], tz)
    return True


def sync_followers(cfg, data, tz):
    uid = (data.get("profile") or {}).get("id")
    if not uid:
        return 0
    res = mcp(f'Call {T_FOLLOWERS} with arguments {json.dumps({"user_id": str(uid), "count": 100})}.',
              T_FOLLOWERS, timeout=120)
    page = [{"id": f.get("id"), "userName": f.get("username"), "name": f.get("name"),
             "profile_image_url_https": f.get("profile_image_url"), "followers_count": f.get("followers"),
             "description": f.get("description")} for r in res for f in (r.get("items") or [])]
    if not page:
        return 0
    before = len(data.get("new_followers", []))
    real_call = _core.call
    _core.call = lambda path, params, **k: {"followers": page}   # feed the diff logic our page
    try:
        data["followers_checked"] = 0
        _core.track_new_followers(cfg, HANDLE, data, tz)
    finally:
        _core.call = real_call
    return len(data.get("new_followers", [])) - before


def sync_queue(cfg):
    targets, segments = _core.load_targets(HANDLE)
    queries = _core.queue_queries(cfg, targets)
    avatars = _avatar_map()
    with ThreadPoolExecutor(4) as ex:
        batches = list(ex.map(lambda q: search_all(q, 3), queries))
    tweets = [to_twapi(t, avatars) for b in batches for t in b]
    items = _core.build_queue(cfg, tweets, segments)
    if items:
        _core._kv_json("cc:queue:" + HANDLE, {"ts": time.time(), "items": items})
    return len(tweets), len(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    lock = open(os.path.join(HERE, "logs", ".bridge.lock") if os.path.isdir(os.path.join(HERE, "logs"))
                else os.path.join(HERE, ".bridge.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return                                   # previous run still going

    cfg = _core.load_config()
    tz = _core.local_tz(cfg)
    data = _core.load_data(HANDLE)
    st = data.setdefault("bridge", {})
    msg = []
    msg.append(f"tweets {sync_counts(cfg, data, tz)}")
    if a.all or time.time() - data.get("profile_ts", 0) > PROFILE_EVERY:
        if sync_profile(cfg, data, tz):
            msg.append(f"followers {data['profile'].get('followers')}")
            msg.append(f"new followers +{sync_followers(cfg, data, tz)}")
    data["last_refresh"] = datetime.now(tz).isoformat(timespec="seconds")
    _core.save_data(HANDLE, data)
    t = data["days"].get(datetime.now(tz).strftime("%Y-%m-%d"), {})
    msg.append(f"today {t.get('comments')}c/{t.get('posts')}p")
    if a.all or time.time() - st.get("queue_ts", 0) > QUEUE_EVERY:
        n, k = sync_queue(cfg)
        if k:
            data = _core.load_data(HANDLE)
            data.setdefault("bridge", {})["queue_ts"] = time.time()
            _core.save_data(HANDLE, data)
        msg.append(f"queue {k} items from {n} tweets")
    log(" · ".join(msg))


if __name__ == "__main__":
    main()
