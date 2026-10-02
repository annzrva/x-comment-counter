#!/usr/bin/env python3
"""
taste_build.py — reply targets built from Anna's actual taste, not a persona.

Anna (2026-10-01): the ICP list surfaced people she doesn't care about; what she *does* care
about is visible in who she replies to. So:
  1. seeds   = everyone she replied to in the last N days (data.replied_users in KV, kept by xbridge)
  2. network = who those seeds follow (their most recent ~100 follows, via Sasha's X connector)
  3. similar = accounts followed by several seeds → same circles / topics as her picks
  4. targets.json ← seeds (⭐) + top similar (✨); the reply queue mixes them 50/50

    python3 taste_build.py               # build + write targets.json
    python3 taste_build.py --no-write    # report only
"""

import argparse
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import xbridge                      # loads .env.bridge (KV) + _core, gives mcp()
from xbridge import _core, mcp, log

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser("~/Developer/X growth/out")
CACHE = os.path.join(OUT, "cache")
ME = "burninganna"
OWN = {"burninganna", "vargastartup", "vargaihq"}
T_USER, T_FOLLOWING = "mcp__claude_ai_X__twitter_get_user", "mcp__claude_ai_X__twitter_following"

SF_RE = re.compile(r"\b(sf|san francisco|bay area|palo alto|mountain view|berkeley|oakland|menlo park)\b", re.I)
JUNK_RE = re.compile(r"(\bnft|crypto|web3|\bdefi\b|memecoin|\$[A-Z]{2,}|forex|airdrop|\bdegen|onchain|solana|"
                     r"bitcoin|\bbtc\b|onlyfans|giveaway)", re.I)
BRAND_RE = re.compile(r"^(we |the official|official )|\bwe (help|build|are|make)\b|\bour (platform|team|product)\b|"
                      r"(institute|foundation|university|\bnews\b|podcast network)", re.I)
BRAND_HANDLE_RE = re.compile(r"(_app|_io$|hq$|official|labs?$|inc$)", re.I)


def cached(name, fn):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"taste_{name}_{datetime.now():%Y-%m-%d}.json")
    if os.path.exists(p):
        return json.load(open(p))
    v = fn()
    json.dump(v, open(p, "w"))
    return v


def chunks(xs, n):
    return [xs[i:i + n] for i in range(0, len(xs), n)]


def resolve(handles):
    """@handles → connector profiles (id, followers, following, bio, location…)."""
    def one(group):
        calls = "\n".join(f'- {T_USER} with {json.dumps({"username": h})}' for h in group)
        return mcp(f"Make these calls (in parallel is fine):\n{calls}", T_USER, timeout=300)
    with ThreadPoolExecutor(4) as ex:
        res = [u for b in ex.map(one, chunks(handles, 12)) for u in b]
    return {u["username"].lower(): u for u in res if isinstance(u, dict) and u.get("username")}


def follows(seed_profiles):
    """seed → list of accounts they follow (2 pages ≈ their 100 most recent follows)."""
    def one(group):
        lines = "\n".join(f'- user_id {p["id"]}' for p in group)
        res = mcp(
            f"For EACH user below call {T_FOLLOWING} with "
            f'{{"user_id": "<id>", "count": 100}}, then call it once more for that user with "cursor" set '
            f"to the exact cursor.bottom string from the first result.\n{lines}", T_FOLLOWING, timeout=600)
        return res
    out = []
    with ThreadPoolExecutor(4) as ex:
        for b in ex.map(one, chunks(seed_profiles, 6)):
            out += b
    return out


def is_person(u):
    blob = f"{u.get('description') or ''} {u.get('name') or ''}"
    return not (JUNK_RE.search(blob) or BRAND_RE.search((u.get("description") or "").strip())
                or BRAND_HANDLE_RE.search(u.get("username") or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-overlap", type=int, default=3)
    ap.add_argument("--keep", type=int, default=260)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()

    data = _core.load_data(ME)
    cutoff = (datetime.now() - timedelta(days=a.days)).strftime("%Y-%m-%d")
    seeds = sorted(u for u, d in data.get("replied_users", {}).items() if d >= cutoff and u not in OWN)
    log(f"taste: {len(seeds)} seeds (replied to in {a.days}d)")

    prof = cached("seeds", lambda: resolve(seeds))
    seed_people = [prof[h] for h in seeds if h in prof and is_person(prof[h])]
    log(f"taste: {len(prof)} resolved, {len(seed_people)} people")

    # following pages come back as {"items":[...]} per call; we can't tell which seed a page belongs to
    # from the result alone, so count overlap by how many *pages* list an account (≈ seeds, 2 pages each
    # never repeat the same account for one seed).
    pages = cached("follows", lambda: follows(seed_people))
    cnt, pool = Counter(), {}
    seed_set = {p["username"].lower() for p in seed_people}
    for page in pages:
        for u in (page or {}).get("items") or []:
            h = (u.get("username") or "").lower()
            if not h or h in OWN or h in seed_set:
                continue
            cnt[h] += 1
            pool[h] = u
    log(f"taste: {len(pages)} following pages, {len(cnt)} accounts in the network")

    sim = []
    for h, n in cnt.items():
        u = pool[h]
        fol, fwg = u.get("followers") or 0, u.get("following") or 0
        if n < a.min_overlap or not is_person(u) or not (1500 <= fol <= 600_000):
            continue
        score = n * 10
        score += 8 if SF_RE.search(u.get("location") or "") else 0
        score += 6 if 3000 <= fol <= 150_000 else 0
        score += 4 if fwg >= 0.5 * fol else 0          # Anna's ≥50% rule, as a bonus not a filter
        sim.append((score, h, n, u))
    sim.sort(reverse=True)
    sim = sim[:max(0, a.keep - len(seed_people))]

    rows = [("seed", p["username"], 0, p) for p in seed_people] + [("similar", u["username"], n, u) for _, _, n, u in sim]
    write(rows, a.no_write)


def write(rows, no_write):
    date = f"{datetime.now():%Y-%m-%d}"
    os.makedirs(OUT, exist_ok=True)
    md = os.path.join(OUT, f"taste_targets_{date}.md")
    with open(md, "w") as f:
        f.write(f"# Кому комментить — по твоему вкусу · {date}\n\n")
        f.write("⭐ = ты им отвечала за последнюю неделю · ✨ = их читают несколько твоих ⭐ (число = сколько)\n\n")
        f.write("| | Кто | Фолл. | Подписок | Где | Bio |\n|---|---|---|---|---|---|\n")
        for kind, h, n, u in rows:
            tag = "⭐" if kind == "seed" else f"✨{n}"
            bio = (u.get("description") or "").replace("\n", " ").replace("|", "/")[:100]
            f.write(f"| {tag} | [@{h}](https://x.com/{h}) {u.get('name') or ''} | {u.get('followers') or 0:,} | "
                    f"{u.get('following') or 0:,} | {u.get('location') or ''} | {bio} |\n")
    log(f"taste: ✅ {md} ({sum(r[0] == 'seed' for r in rows)} ⭐ + {sum(r[0] == 'similar' for r in rows)} ✨)")
    if no_write:
        return
    path = os.path.join(HERE, "targets.json")
    t = json.load(open(path))
    t[ME] = {"handles": [h for _, h, _, _ in rows],
             "segments": {h.lower(): [kind] + (["sf"] if SF_RE.search(u.get("location") or "") else [])
                          for kind, h, _, u in rows},
             "built": date, "source": "taste_build.py"}
    json.dump(t, open(path, "w"), indent=1, ensure_ascii=False)
    log(f"taste: ✅ targets.json ← {len(rows)}")


if __name__ == "__main__":
    main()
