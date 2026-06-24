"""Vercel serverless function → GET /img?u=<pbs.twimg.com url> (image proxy)"""
import os
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _core as app  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _err(self, code, msg):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(msg.encode())

    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        u = qs.get("u", [""])[0]
        if not u:
            self._err(400, "no url"); return
        if urllib.parse.urlparse(u).netloc not in app.IMG_HOSTS:
            self._err(403, "host not allowed"); return
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "image/jpeg")
        except Exception as e:
            self._err(502, str(e)); return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
