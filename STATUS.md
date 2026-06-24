# STATUS — Comment Counter

**Created:** 2026-06-22

## v6 (2026-06-24) — 🟢 LIVE on Vercel
**Public URL: https://x-comment-counter.vercel.app** (no login, public).
- Vercel project `x-comment-counter`.
- **Upstash for Redis** connected (Free tier) → `KV_REST_API_URL/TOKEN` auto-injected.
  `TWITTERAPI_KEY` set in env (Production).
- **Built for the new Vercel Python builder (uv, single entrypoint):**
  - all logic in `api/_core.py`; `pyproject.toml` → `[tool.vercel] entrypoint="api._core:Handler"`.
    `_core.Handler` routes `/`, `/api/lookup`, `/img` and serves index.html.
  - root `app.py` is a thin local-dev shim (hidden from deploy via `.vercelignore`).
  - `pyproject.toml` with `[project]` (deps=[], stdlib) + `[tool.uv] package=false`. requirements.txt removed.
- **Deployment Protection disabled** via API (`PATCH ssoProtection:null`) — otherwise it redirects to SSO.
- Deploy: `npx vercel deploy --prod --yes`.
- **Verified in prod**: /, lookup (levelsio streak 9 / burninganna), cache hit (cached:true),
  img proxy (200). ✅
- Prod cache started empty (KV blank) — burninganna shows a 14-day history in prod, not 79.
  The local 79 days live in `data/burninganna.json` (not uploaded to prod).
- **Next ideas**: custom domain (Vercel → Domains); load burninganna's full history into KV;
  auto-refresh / reminder.

## v5 (2026-06-24) — VERCEL-READY (serverless + Redis)
Prepared for Vercel deploy. Guide: **DEPLOY.md**.
- **KV-aware storage** (`app.py`): Redis (Upstash/Vercel KV) in prod, local files in
  dev — switched by env vars. Redis client on pure urllib (no deps): `kv_cmd()` via
  Upstash REST. `load_data/save_data` → `cc:data:<handle>`; daily cap → `INCR
  cc:usage:<date>` + EXPIRE 2d.
- **Serverless functions**: `api/lookup.py` (/api/lookup), `api/img.py` (/img→/api/img).
- **config.json now optional**: DEFAULT_CONFIG = production values (goal 20),
  load_config doesn't crash on Vercel's read-only FS.
- `.vercelignore` hides .env/data/usage.
- **Tested locally**: file fallback (owner lookup ok), KV path mocked (round-trip data
  + cap via INCR work). ✅

## v4 (2026-06-24) — MULTI-HANDLE ✅ working
From a personal tracker → a product: anyone types a handle (their own or someone
else's) and sees that account's comments/posts/streak/graph.
- **Search box** in the header (`#search`): accepts `@name`, `name`, or an x.com/... link.
  Handle is read from the URL `?h=name` (shared links work) + last-used in localStorage.
- **Per-handle data**: `data/<handle>.json` (instead of a single `data.json`).
  Old history migrated → `data/burninganna.json` (79 days).
- **`lookup()` orchestrator** with cache: calls the API only when the cache is stale/empty.
  Endpoint `/api/lookup?handle=H&force=0/1` (replaced /api/state + /api/refresh).
- **twitterapi.io cost controls** (for public access):
  - `cache_ttl_minutes` 360 — repeat / shared links = free
  - `new_handle_backfill_days` 14 — short history for a new handle (matches the 14-day heatmap)
  - `daily_call_cap` 1500 — hard ceiling on calls/day; over it, serves cache (note=budget)
    instead of burning the balance
  - `rate_per_ip_per_min` 8 — per-IP limit on new lookups
  - handle validation: non-existent → clean `invalid_handle` error
- **Cost per new handle**: depends on activity (levelsio 14d ≈ 40 calls; a normal user much less).
  Cache hits are free.
- **Tested (2026-06-24):** levelsio first-fetch (streak 12, 31 days), cache hit,
  invalid handle, owner — all ✅.

---

## What it is
A Duolingo-style dashboard for daily X activity: counts replies (comments) and posts,
keeps a streak, and celebrates hitting the goal with confetti.

**Daily goal:** 20 comments + 1 post (stretch 30).

## v3 (2026-06-22) — kawaii redesign
- **New Y2K/kawaii aesthetic:** pastel gradient (#7be3ff→#a8c0ff→#e6b3ff),
  Fredoka font, holographic CD (spins), stars, stickers 🦋😎🌈, rainbow stripe.
- **Priority:** 1) Comments (hero, 120px figure) 2) Posts (bubble) 3) Streak (small bubble).
- **Goal 20** comments (was 50/15), stretch 30 kept.
- **Dropped the GitHub grid** → simple 14-day heatmap (green intensity, today pink).
- **Tap animations:** 🦋 flutters + 💿 spins-explodes, both spray confetti/emoji.
- **Share card** reworked into the same aesthetic (1200×675 PNG).

## v2 (2026-06-22) — graph + share
- **Leaderboard removed** (decision 2026-06-22): it was pseudo-social — friends weren't
  "playing", just scraped public numbers. Real social mechanic = the share card (outward,
  into the feed → virality). Code/endpoint/config/cache deleted.
- **GitHub-style contribution graph**: quarter/year, levels 0 empty · 1 active ·
  2 goal · 3 exceeded. Backfill history: `python3 app.py --backfill 90`.
- **Share card** (1200×628 PNG): avatar, streak, today, mini-graph, CTA.
  Download / Copy image / Post on X. Images go through the `/img` proxy
  (pbs.twimg.com) so the canvas isn't tainted and the PNG exports cleanly.

## Goal: two-tier (decided 2026-06-22)
Analysis of 79 days: median 2 comments/day, mean 3.8, max 32 — a goal of 50 was unreal.
Switched to Duolingo mechanics:
- **floor 15** (`comments_goal`) + 1 post → keeps the streak, day = green (level 2)
- **stretch 30** (`comments_stretch`) → brightest tile (level 3)
- Gold floor marker on the comments bar; fill stretches to the stretch goal.
(Floor later set to 20 in v3.)

## Run
`python3 app.py` (or double-click start.command)

## TODO / ideas
- Auto-refresh + evening reminder if the goal isn't met.
- macOS menu-bar widget.
