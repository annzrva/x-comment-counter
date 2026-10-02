# STATUS — Comment Counter

**Created:** 2026-06-22

## 🌉 Bridge (2026-10-01) — ✅ LIVE: prod no longer uses twitterapi.io
- `remote_fetch: False` → prod never calls twitterapi.io, only serves KV. **`xbridge.py`** on Anna's Mac feeds KV:
  X data from Sasha's claude.ai X connector (`mcp__claude_ai_X__*`) via headless `claude -p --model haiku`
  (only the one X tool allowed; raw tool results parsed from stream-json). KV creds: `.env.bridge` (vercel env pull, gitignored).
- Every run: new tweets via `from:burninganna since_time:<last-5min>` (first run of day = full day, ~15 calls) → counts by
  tweet id (`data.bridge.seen`, only for "full days"), replied ids/users, "?" share. Hourly: profile + followers diff (50 newest).
  Every 45 min: reply queue (14 OR-searches, 4 parallel; avatars from icp_build cache). ≈8s per quick run, ~3.5 min full.
- First run 2026-10-01 20:54: 68 comments (prod had frozen at 13), 1,760 followers, +3 new followers, 250-post queue.
- Schedule: every 5 min via launchd `ai.varg.xbridge` — Anna installs it (agent isn't allowed to create LaunchAgents).
- Downsides: works only while the Mac is on/awake; other handles on the public site show "isn't tracked right now".

## ⚠️ 2026-10-01 — twitterapi.io credits ran out (402 "Credits is not enough")
Prod froze at 13 comments (last refresh 14:00 PT) — the page silently showed stale numbers. Burned by: 2 ICP builds
(~1.5k calls), the reply queue (~28 calls per refresh), follower checks, live polls.
- Fix: yellow banner on the page when the API fails (credits → "Top up" link). Cost cuts: queue cache 20→45 min,
  forced-refresh floor 3→10 min, follower checks 30→60 min.
- **Anna must top up at https://twitterapi.io/dashboard** — nothing refreshes until then.

## 📈 Follower gain tracking (2026-10-01) — ✅ LIVE
- Road card: **+today / +last 7 days** (from `followers_log`; "since tracking began" until 7 days exist), daily bars (14 days),
  **👋 New followers** list with badges 💬 "you replied" (to any of their posts in the last 30 days) and 🎯 "in your list",
  plus "X/Y new followers you'd replied to" = are replies converting.
- Owner-only (handles in targets.json): every ≤30 min (`followers_check_minutes`) on any refresh incl. the 2-min live poll:
  profile (count) + newest 200 followers diffed vs `followers_seen` (first run only seeds). `replied_users` from her replies.
  +~2 API calls / 30 min while the page is open. Unfollows aren't listed (only the net count shows them).

## 💡 Reply ideas (2026-09-30) — ✅ LIVE (pre-written batches)
- Each queue post gets 3 drafts (insight / take / curious), each ending with a question; "💡 ideas" expands them, tap = copy,
  Anna rewrites on X herself.
- Written by **`ideas_batch.py`** on Anna's Mac: local `claude -p` (her subscription, **no tools** — post text is untrusted),
  Sonnet, 15 posts per call ×3 parallel, voice = her ~15 recent replies. Result → `ideas.json` (pruned to 2 days) → prod deploy.
  `get_queue` attaches `item.ideas`. First run 2026-09-30: 135/250 posts. ~2 min per 120 posts.
- Schedule: `ai.varg.xideas.plist` (10:30–22:30 every 2h). Install: `cp ai.varg.xideas.plist ~/Library/LaunchAgents/ &&
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.varg.xideas.plist`. Logs: `logs/ideas.log`.
- AI Gateway on-click path (`/api/suggest`) is still in the code but unused — needs a card on team annas-projects.

## 🎯 Reply queue (2026-09-30) — ✅ LIVE (deployed ca5798d)
So Anna doesn't scroll the feed to hit 150 replies/day. Replies are ALWAYS written by hand on X (X bans automated replies) —
the app only picks which posts to open.
- **Who (updated same day → ICP list):** `targets.json` = `{"burninganna": {handles, segments, built}}`, 210 people,
  built by `~/Developer/X growth/icp_build.py` (see its STATUS). Queue interleaves by segment per `queue_mix`
  (sf .35 / builder .30 / founder .25 / reach .10), chips 🌉🛠🚀📣 on each post. Refresh ≈ 44s, ~28 calls.
- ~~Old list~~: `targets.json` → `{"burninganna": [129 handles]}` = digest.py 9 + anchor_rank (score>0, ≥0.3 posts/day) + ladder 110,
  people only (dropped theworldlabs, bfl_ai, FlowbyGoogle, sesame, DecartAI). Edit that file to change the list.
  Queue shows only for handles present in targets.json (others: hidden).
- **What:** `/api/queue` → OR-searches (16 handles/query, 2 pages) for original posts < 16h, ranked by
  velocity × visibility (few replies = your reply is seen) × freshness bonus < 2h; max 4 posts per person; ≤250.
  Cached in KV `cc:queue:<handle>` 20 min; forced refresh floor 3 min. Cost ≈ 18 API calls / ~20s per refresh.
- **Done-detection:** her replies' `inReplyToId` are stored in `data.replied` (last 2 days) on every lookup/live poll →
  replied posts auto-grey/hide. "Reply ↗" click = "opened" (dimmed), "skip" — both in localStorage.
- Verified locally: 103–161 posts from 129 people.

## 🚀 Reply-guy playbook (2026-09-30) — ✅ LIVE
Based on the "0 → 5k followers" post (150–400 replies/day ≈ 250 followers/week; <5k nothing goes viral, >10k it's routine).
- **Goal raised: 150 comments floor / 300 stretch** (+1 post). ⚠️ The streak is recomputed with the new goal → old days no longer count.
- **Road to 5k / 10k card**: followers → next milestone, ETA at the measured weekly pace (last ≤28 days, needs ≥3 days of log),
  falls back to the 250/wk benchmark. Config: `follower_milestones`, `benchmark_followers_per_week`.
- **Weekly chart**: replies/week (green) vs new followers/week (pink), last 8 weeks.
  Follower history starts now: `data.followers_log` = one count per day, written on every profile fetch
  (live poll fetches the profile once a day just for this → +1 API call/day per open handle). No backfill possible.
- **"❓ N% end with ?"** in the comments pill — replies whose text ends with "?" (new field `q` per day; old days have none).
- **Playbook** collapsible block with the 5 tactics.
- Verified locally (burninganna: 1,756 followers → 5k ETA ~13 wks at benchmark). Commit + `npx vercel deploy --prod --yes` pending.

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
