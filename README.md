# 🔥 Comment Counter

A Duolingo-style tracker for your X (Twitter) reply grind. Type any handle and
see that account's **replies (comments)**, **posts**, daily **streak**, and a
contribution **heatmap** — with confetti when you hit the goal. 🎉

**Live:** https://x-comment-counter.vercel.app — type any handle, no login.

Built by [@burninganna](https://x.com/burninganna). Open source.

## Why
Small accounts grow by replying every day — but the grind is invisible, so people
quit. This turns it into a game: hit your daily goal, keep the streak alive, and
watch the map go green.

## The daily goal
**20 replies + 1 post** keeps your streak alive (the day turns green). Hit the
**30-reply stretch** for the brightest tile. Goals are configurable.

## Use it
Open the live site and type a handle (`@name`, `name`, or an `x.com/...` link).
Shareable: a `?h=handle` link deep-links straight to an account.

## Run locally
```bash
python3 app.py
```
Opens a dashboard at http://127.0.0.1:8765. No dependencies — pure Python standard
library. Quick CLI check without a server:
```bash
python3 app.py --refresh yourhandle
```
You'll need a [twitterapi.io](https://twitterapi.io) key in `.env`:
```
TWITTERAPI_KEY=your_key_here
```

## Self-host / deploy
The app runs on Vercel (serverless) with an Upstash Redis cache. Full steps in
**[DEPLOY.md](DEPLOY.md)**.

## What's on the dashboard
- 🔥 **Streak** — consecutive days the goal was met (dims to 0 when broken).
- 💬 / 📝 **Progress bars** — today's replies and posts vs. the goal.
- 🗓 **14-day heatmap** — green = goal met, yellow = active but short of goal,
  empty = nothing. Hover for details.
- 🏆 **Best streak** — your record.
- 📸 **Share card** — a PNG to post on X ("can you beat my streak?").

## How replies are counted
Via twitterapi.io advanced search: `from:<handle> filter:replies` for comments and
`from:<handle> -filter:replies` for posts. Each tweet's timestamp maps to a local
day. Numbers can shift slightly between refreshes — that's normal, data comes
straight from X.

## Cost controls (public-safe)
- `cache_ttl_minutes` (360) — a handle's data is reused for 6h; repeat / shared
  views are free.
- `new_handle_backfill_days` (14) — history depth fetched the first time a handle
  is seen.
- `daily_call_cap` (1500) — hard ceiling on API calls per day; past it, cached
  handles still load and new lookups get a "try tomorrow" message.

## Config
`config.json` (optional — sensible defaults are built in):
```json
{
  "handle": "burninganna",
  "comments_goal": 20,
  "comments_stretch": 30,
  "posts_goal": 1,
  "timezone_offset_hours": null
}
```

## Files
- `api/_core.py` — all logic: API counting, streak, KV-aware storage, HTTP handler.
- `app.py` — thin local-dev entrypoint (re-exports `_core`).
- `api/lookup.py`, `api/img.py` — Vercel serverless functions.
- `index.html` — the dashboard (vanilla JS, canvas confetti).
- `pyproject.toml`, `vercel.json` — deploy config.

## Tech
Pure Python standard library (no deps). Vercel + Upstash Redis in production, local
files in dev — switched automatically by env vars.
