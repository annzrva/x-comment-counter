# Deploy to Vercel

The app is split into:
- `index.html` — static frontend (served at `/`)
- `api/lookup.py` — serverless function → `/api/lookup`
- `api/img.py` — serverless image proxy → `/img` (rewritten to `/api/img`)
- `app.py` — shared core logic (counting, streak, KV-aware storage)
- `vercel.json` — routing + bundles `app.py` into the functions

> Vercel's filesystem is **read-only**, so the per-handle cache and the daily
> budget counter live in **Redis (Upstash / Vercel KV)**. The code auto-detects
> the KV env vars; locally (no env) it falls back to files. **KV is required in
> prod** — without it lookups can't persist and the budget cap won't work.

---

## One-time setup

### 1. Log in (only interactive step)
```
npx vercel login
```
(opens a browser — pick the email/GitHub you want the project under)

### 2. Create + link the project
```
npx vercel link --yes
```

### 3. Add Redis (Upstash, free)
In the Vercel dashboard → your project → **Storage** → **Create / Connect Store**
→ **Upstash Redis** (Marketplace, free tier). Connect it to the project.
This auto-injects `KV_REST_API_URL` and `KV_REST_API_TOKEN` as env vars.

*(Alternative: sign up at upstash.com, create a Redis DB, then set
`UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` as Vercel env vars — the
code accepts either name pair.)*

### 4. Add the twitterapi.io key
```
printf '%s' "$TWITTERAPI_KEY" | npx vercel env add TWITTERAPI_KEY production
```
(or paste it when prompted by `npx vercel env add TWITTERAPI_KEY production`)

---

## Deploy
```
npx vercel deploy --prod --yes
```
You'll get a `https://<project>.vercel.app` URL. Share it — anyone can type a
handle. Repeat visits / shared `?h=name` links hit the cache (free).

## Redeploy after changes
```
npx vercel deploy --prod --yes
```

## Cost guardrails (in config.json / DEFAULT_CONFIG)
- `cache_ttl_minutes` 360 — a handle's data is reused for 6h (no API call)
- `new_handle_backfill_days` 14 — history depth on first lookup
- `daily_call_cap` 1500 — hard ceiling on twitterapi.io calls/day; over it,
  cached handles still load, new fetches return a "try tomorrow" message

## Custom domain (optional)
Vercel dashboard → project → **Domains** → add e.g. `streak.varg.ai`
(or a subdomain you like) and point the DNS CNAME as Vercel instructs.
