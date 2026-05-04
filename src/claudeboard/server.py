"""HTTP server: routes for /, /data.json, /session/<id>, /summary/<id>."""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

from claudeboard.detail import detail
from claudeboard.page import PAGE
from claudeboard.sessions import scan
from claudeboard.summary import invalidate_summary_cache, summarize

PORT = 8765
HOST = "127.0.0.1"
ID_RE = re.compile(r"^[0-9a-f-]{36}$")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        return

    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _empty(self, code: int) -> None:
        self.send_response(code)
        self.end_headers()

    def _route_summary(self, sid: str, force: bool) -> None:
        if force:
            invalidate_summary_cache(sid)
        d = summarize(sid)
        if d is None:
            self._json({"error": "session not found"}, 404)
            return
        self._json(d)

    def do_GET(self):
        if self.path == "/data.json":
            self._json(scan())
            return
        if self.path.startswith("/session/"):
            sid = self.path[len("/session/") :]
            if not ID_RE.match(sid):
                self._empty(400)
                return
            d = detail(sid)
            if d is None:
                self._empty(404)
                return
            self._json(d)
            return
        if self.path.startswith("/summary/"):
            sid = self.path[len("/summary/") :]
            if not ID_RE.match(sid):
                self._empty(400)
                return
            self._route_summary(sid, force=False)
            return
        body = PAGE
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.startswith("/summary/"):
            sid = self.path[len("/summary/") :]
            if not ID_RE.match(sid):
                self._empty(400)
                return
            self._route_summary(sid, force=True)
            return
        self._empty(404)


def run(host: str = HOST, port: int = PORT) -> None:
    print(f"http://{host}:{port}")
    HTTPServer((host, port), Handler).serve_forever()
