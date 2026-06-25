"""Vercel serverless function → GET /api/lookup?handle=H&force=0/1"""
import os
import sys
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _core as app  # noqa: E402  (shared core logic + KV-aware storage)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        cfg = app.load_config()
        handle = app.sanitize_handle(qs.get("handle", [cfg["handle"]])[0])
        force = qs.get("force", ["0"])[0] in ("1", "true", "yes")
        cached_only = qs.get("cached", ["0"])[0] in ("1", "true", "yes")
        c = app._with_graph(cfg, qs)
        try:
            body, code = json.dumps(app.lookup(c, handle, force=force, cached_only=cached_only)), 200
        except app.InvalidHandle as e:
            body, code = json.dumps({"error": str(e), "invalid_handle": True}), 200
        except app.BudgetExceeded as e:
            body, code = json.dumps({"error": str(e), "budget": True}), 200
        except Exception as e:
            body, code = json.dumps({"error": str(e)}), 500
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode())
