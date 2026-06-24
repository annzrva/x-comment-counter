#!/usr/bin/env python3
"""
X Comment Counter — local-dev entrypoint.

All logic lives in api/_core.py (so Vercel auto-bundles it with the serverless
functions). This shim just re-exports it and runs the local http.server / CLI:

    python3 app.py                 # server + open browser
    python3 app.py --port 8765
    python3 app.py --refresh [h]   # print today's numbers for handle h
    python3 app.py --backfill 90 [h]  # fetch N days of history
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))
from _core import *          # noqa: F401,F403  (re-export core for local tooling)
from _core import main       # noqa: E402

if __name__ == "__main__":
    main()
