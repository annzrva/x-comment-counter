#!/usr/bin/env python3
"""
ideas_batch.py — reply ideas for the reply queue, written by Claude Code on Anna's Mac.

No API keys / card: uses the local `claude` CLI (Anna's subscription) in headless mode with
NO tools (post text is untrusted). Runs every 2h via launchd (ai.varg.xideas), see STATUS.md.

  1. GET the live queue from prod
  2. pick posts without ideas (skip ones she already replied to), in queue order
  3. ask Claude for 3 drafts per post (insight / take / curious), each ending with a question
  4. merge into ideas.json (pruned to 2 days) → deploy prod so the page shows them

    python3 ideas_batch.py              # generate + deploy
    python3 ideas_batch.py --no-deploy  # generate only
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "api"))
import _core  # noqa: E402

HANDLE = "burninganna"
PROD = "https://x-comment-counter.vercel.app"
IDEAS_PATH = os.path.join(HERE, "ideas.json")
LOG = os.path.join(HERE, "logs", "ideas.log")
SCOPE = "annas-projects-4b7957a4"
CLAUDE = os.path.expanduser("~/.local/bin/claude")

BATCH_SYSTEM = _core.SUGGEST_SYSTEM.split("Reply with JSON only")[0] + (
    "You get several posts, each in a <post id=...> tag. Write 3 replies for EACH post.\n"
    'Reply with JSON only, keyed by post id: {{"<id>": [{{"angle":"insight","text":"..."}},'
    '{{"angle":"take","text":"..."}},{{"angle":"curious","text":"..."}}], ...}}'
)


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def get_queue():
    with urllib.request.urlopen(f"{PROD}/api/queue?handle={HANDLE}", timeout=200) as r:
        return json.loads(r.read().decode())


def ask_claude(posts, voice, who):
    user = ""
    if voice:
        user += "<her_example_replies>\n" + "\n---\n".join(voice) + "\n</her_example_replies>\n\n"
    for it in posts:
        user += (f'<post id="{it["id"]}" author="@{it["handle"]}" name="{it.get("name", "")}" '
                 f'followers="{it.get("followers")}">\n{it["text"]}\n</post>\n\n')
    p = subprocess.run(
        [CLAUDE, "-p", "--tools", "", "--model", "sonnet", "--no-session-persistence",
         "--strict-mcp-config", "--system-prompt", BATCH_SYSTEM.format(who=who)],
        input=user, capture_output=True, text=True, timeout=600)
    m = re.search(r"\{.*\}", p.stdout, re.S)
    if not m:
        raise RuntimeError(f"no JSON from claude: {p.stdout[:200]} {p.stderr[:200]}")
    out = {}
    for tid, reps in json.loads(m.group(0)).items():
        reps = [{"angle": r.get("angle", ""), "text": (r.get("text") or "").strip()}
                for r in reps if isinstance(r, dict) and r.get("text")][:3]
        if reps:
            out[str(tid)] = reps
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=90, help="posts per run")
    ap.add_argument("--chunk", type=int, default=15, help="posts per claude call")
    ap.add_argument("--no-deploy", action="store_true")
    a = ap.parse_args()

    q = get_queue()
    if q.get("error"):
        log(f"queue error: {q['error']}")
        return
    ideas = {}
    if os.path.exists(IDEAS_PATH):
        with open(IDEAS_PATH) as f:
            ideas = json.load(f)
    live = {i["id"] for i in q["items"]}
    replied = set(q.get("replied_ids") or [])
    todo = [i for i in q["items"] if i["id"] not in ideas and i["id"] not in replied][:a.max]
    if not todo:
        log("nothing new")
        return

    voice = _core.owner_voice(HANDLE)
    who = _core.OWNER_CONTEXT[HANDLE]
    chunks = [todo[i:i + a.chunk] for i in range(0, len(todo), a.chunk)]
    new = {}
    with ThreadPoolExecutor(3) as ex:
        for res in ex.map(lambda c: _safe(ask_claude, c, voice, who), chunks):
            new.update(res)
    now = time.time()
    for tid, reps in new.items():
        if tid in live:
            ideas[tid] = {"ts": now, "replies": reps}
    # keep ideas for posts still in the queue, or younger than 2 days
    ideas = {k: v for k, v in ideas.items() if k in live or now - v["ts"] < 172800}
    with open(IDEAS_PATH, "w") as f:
        json.dump(ideas, f, ensure_ascii=False)
    log(f"+{len(new)} posts with ideas ({len(todo)} asked) · total {len(ideas)}")

    if not a.no_deploy and new:
        r = subprocess.run(["npx", "vercel", "deploy", "--prod", "--yes", f"--scope={SCOPE}"],
                           cwd=HERE, capture_output=True, text=True, timeout=600)
        log("deploy " + ("ok" if r.returncode == 0 else f"FAILED: {r.stderr[-300:]}"))


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        log(f"chunk failed: {e}")
        return {}


if __name__ == "__main__":
    main()
