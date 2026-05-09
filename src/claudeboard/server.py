from __future__ import annotations

import json
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from claudeboard.detail import detail
from claudeboard.focus import focus_session
from claudeboard.page import PAGE
from claudeboard.sessions import scan
from claudeboard.spend import aggregate_spend
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

    def do_GET(self) -> None:
        if self.path == "/data.json":
            self._json(scan())
            return
        if self.path.startswith("/spend"):
            q = parse_qs(urlsplit(self.path).query)
            try:
                end = float(q.get("to", [str(time.time())])[0])
                start = float(q.get("from", [str(end - 86400)])[0])
                buckets = int(q.get("buckets", ["60"])[0])
            except ValueError:
                self._empty(400)
                return
            self._json(aggregate_spend(start, end, buckets))
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
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def do_POST(self) -> None:
        if self.path.startswith("/summary/"):
            sid = self.path[len("/summary/") :]
            if not ID_RE.match(sid):
                self._empty(400)
                return
            self._route_summary(sid, force=True)
            return
        if self.path.startswith("/focus/"):
            sid = self.path[len("/focus/") :]
            if not ID_RE.match(sid):
                self._empty(400)
                return
            ok, detail_msg = focus_session(sid)
            self._json({"ok": ok, "detail": detail_msg}, 200 if ok else 404)
            return
        self._empty(404)


def run(host: str = HOST, port: int = PORT) -> None:
    print(f"http://{host}:{port}")
    HTTPServer((host, port), Handler).serve_forever()
