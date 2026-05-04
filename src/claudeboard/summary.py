"""Sonnet-generated session summary, cached on disk by msg count."""

from __future__ import annotations

import contextlib
import json
import os
import urllib.error
import urllib.request

from claudeboard.sessions import find_session, parse_session

SONNET = "claude-sonnet-4-6"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_TOKENS = 400


def call_sonnet(prompt: str) -> dict:
    """POST /v1/messages and return {"text": ...} or {"error": ...}."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"error": "ANTHROPIC_API_KEY not set"}
    body = json.dumps(
        {
            "model": SONNET,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"{e.code} {e.read().decode()[:200]}"}
    except urllib.error.URLError as e:
        return {"error": str(e)[:200]}
    text = ""
    for b in d.get("content", []):
        if b.get("type") == "text":
            text = b.get("text", "")
            break
    return {"text": text}


def summarize(sid: str) -> dict | None:
    path = find_session(sid)
    if not path:
        return None
    s = parse_session(path)
    msgs = s["msgs"]
    cache = path[:-6] + ".summary.json"
    if os.path.exists(cache):
        try:
            with open(cache) as fh:
                c = json.load(fh)
            if c.get("msg_count") == len(msgs):
                return c
        except (OSError, json.JSONDecodeError):
            pass
    if not msgs:
        return {"summary": "(no transcript)", "msg_count": 0}
    recent = msgs[-60:]
    transcript = "\n\n".join(f"[{m['role']}] {m['text'][:2500]}" for m in recent)
    prompt = (
        "Summarize what this Claude Code session is doing in 3-5 sentences. "
        "Focus on the user's goal, what's been accomplished, and what's in progress. "
        "Be concrete; reference filenames or commands where relevant. "
        "No preamble, no markdown headers.\n\n"
        f"--- TRANSCRIPT ---\n{transcript}"
    )
    r = call_sonnet(prompt)
    if "error" in r:
        return r
    out = {"msg_count": len(msgs), "summary": r["text"]}
    try:
        with open(cache, "w") as fh:
            json.dump(out, fh)
    except OSError:
        pass
    return out


def invalidate_summary_cache(sid: str) -> None:
    path = find_session(sid)
    if not path:
        return
    cache = path[:-6] + ".summary.json"
    if os.path.exists(cache):
        with contextlib.suppress(OSError):
            os.remove(cache)
