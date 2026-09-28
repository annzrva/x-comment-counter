# STATUS — Comment Counter

**Created:** 2026-06-22

## 🔔 Live sounds (2026-09-27) — LIVE
- While the page is open (even in a background tab) it polls `/api/lookup?live=1` every **2 min**.
  Live mode = today only, no profile fetch → ~4 twitterapi.io calls per poll. Sleeps after **3h** without interaction on the page.
- New comment → "boing" pop (the smiley sound) that climbs in pitch per extra comment, plus a smiley burst.
  New post → the disc zap + sparkle, plus a disc burst.
- Sounds unlock after the first tap/key on the page (browser autoplay rule); 🔊/🔇 toggle respected.
- Delay: up to ~2 min + twitterapi.io indexing lag. Instant would need a browser extension on x.com (idea).

## 🟢 FIXED & LIVE again (2026-09-27)
**Cause of the outage:** the Upstash Redis store (`upstash-kv-pink-xylophone`) got uninstalled while the KV_* env vars stayed,
and the code swallowed errors → every lookup said "no such X account".
**Done:**
- Removed stale KV_* / REDIS_URL vars; provisioned new **Upstash for Redis `x-comment-counter-kv`** (team *Anna's projects*, free) and connected it.
  ⚠️ The project lives in the **annas-projects-4b7957a4** team, not vargai — use `--scope=annas-projects-4b7957a4` for integration commands.
- Prod `TWITTERAPI_KEY` replaced with the working local key (the old prod one could not be verified).
- `fetch_profile`: only a real "user not found" → invalid_handle; other errors surface as a 500 with the real message.
- **Found & fixed a data leak:** `dict(_EMPTY)` shallow copy → on a reused Fluid instance a new/non-existent handle
  showed the previous handle's history. Now `_empty()` returns a fresh dict.
- Seeded @burninganna history (local 81 days) + `--backfill 96` → 106 active days in KV.
- Deployed (`npx vercel deploy --prod --yes`) and verified in prod: burninganna ✅, levelsio ✅, fake handle → proper invalid_handle ✅.

## Launch video (2026-06-24) — ✅ rendered
- HyperFrames composition in `launch-video/` — 5-scene vertical promo (1080×1920, 25s).
  Story: the void → invisible grind → "a Duolingo for your replies" → triumph (heatmap +
  streak) → "type any handle, free, no login" + URL.
- Y2K/kawaii aesthetic matching the app (pastel gradient, Fredoka, emoji sprinkles, crossfades).
- **Fredoka embedded locally** (`fonts/fredoka-latin.woff2`, variable woff2) for deterministic render.
- Contrast bumped on green/blue/pink accents. Lint clean (0/0).
- **Music**: bubbly hyperpop, generated via **varg** (`music_v1`, ElevenLabs, 25s, ~30 credits).
  Track `launch-video/music.mp3`. Added as a separate `<audio>` track (data-volume 0.85).
- **Outputs** (both 30fps, high quality):
  - Vertical 9:16 (1080×1920): `…launch.mp4` (silent) · **`…launch-music.mp4`** (5.5 MB, with music) ✅
  - Landscape 16:9 (1920×1080): `…launch-16x9.mp4` (silent) · **`…launch-16x9-music.mp4`** (5.7 MB, with music) ✅
    (re-laid-out composition in `launch-video/landscape/`).
  - All in `launch-video/renders/`. The `-music` files are the final deliverables.
- **Product reveal + personal copy (landscape only)**: scene 4's abstract heatmap replaced with a
  real dashboard screenshot (`launch-video/landscape/app-shot.jpg`) in a browser frame.
  Screencast version to be recorded later (Anna). Vertical 9:16 left as-is (desktop shot ≠ portrait).
- **v4 (current cut, 2026-06-25)**: simplified to **4 slides, ~2s each, ~9.5s total**, snappy.
  1) "engaging with other people / builds real relationships on X." 2) "the ratio i'm aiming for"
  → 10 : 1 (count-up). 3) "so i built a tracker." + dashboard + ✓ goal-hit sticker.
  4) "made it for me." / "but you can try too →" + URL + @burninganna.
  Music trimmed to 9.5s w/ fade (`landscape/music-short.mp3`).
  → **`launch-video/renders/x-comment-counter-launch-16x9-v4.mp4`** (3.9 MB). ✅ FINAL landscape cut.
  Earlier longer cuts kept in `renders/` for reference (v2 25s, v3 21s, -product).
- **Post copy** (Anna's final, English): "engaging with other people is how you actually build
  relationships on X / so i built myself a tiny tracker to stay consistent / made it for me,
  but you can try too 👇 + URL".

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
