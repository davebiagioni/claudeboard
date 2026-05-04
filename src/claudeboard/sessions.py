"""Session jsonl loading: scanning the project dir, parsing files, caching by mtime."""

from __future__ import annotations

import glob
import json
import os
import time

ROOT = os.path.expanduser("~/.claude/projects")
MAX_MSG_BYTES = 50_000

_meta_cache: dict[str, tuple[float, dict]] = {}


def short_path(p: str) -> str:
    home = os.path.expanduser("~")
    if p.startswith(home):
        return "~" + p[len(home) :]
    return p


def find_session(sid: str) -> str | None:
    matches = glob.glob(os.path.join(ROOT, "*", sid + ".jsonl"))
    return matches[0] if matches else None


def session_meta(path: str, mtime: float) -> dict | None:
    """Cheap fields read from the whole jsonl, cached by mtime.

    Returns None if the file disappeared mid-read.
    """
    hit = _meta_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    cwd = branch = ai_title = slug = ""
    first_user = last_user = last_text = last_tool = last_role = ""
    try:
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not cwd and d.get("cwd"):
                    cwd = d["cwd"]
                if not branch and d.get("gitBranch"):
                    branch = d["gitBranch"]
                if not slug and d.get("slug"):
                    slug = d["slug"]
                if d.get("type") == "ai-title" and not ai_title:
                    ai_title = d.get("aiTitle", "")
                m = d.get("message")
                if not isinstance(m, dict):
                    continue
                role = m.get("role", "")
                c = m.get("content")
                text = ""
                tool = ""
                if isinstance(c, str):
                    text = c
                elif isinstance(c, list):
                    for b in c:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text" and not text:
                            text = b.get("text", "")
                        elif b.get("type") == "tool_use" and not tool:
                            tool = b.get("name", "")
                text = text.strip()
                if text.startswith("<"):
                    text = ""
                if not text and not tool:
                    continue
                if role == "user" and text:
                    if not first_user:
                        first_user = text
                    last_user = text
                    last_role = "user"
                    last_tool = ""
                    last_text = ""
                elif role == "assistant":
                    last_role = "assistant"
                    if tool:
                        last_tool = tool
                    if text:
                        last_text = text
    except OSError:
        return None
    info = {
        "cwd": cwd,
        "branch": branch,
        "ai_title": ai_title,
        "slug": slug,
        "first_user": first_user[:240],
        "last_user": last_user[:240],
        "last_text": last_text[:240],
        "last_tool": last_tool,
        "last_role": last_role,
    }
    _meta_cache[path] = (mtime, info)
    return info


def parse_session(path: str) -> dict:
    """Full parse of a session jsonl. Returns aggregates needed for the detail view."""
    in_t = out_t = cache_r = cache_w = 0
    tools: dict[str, int] = {}
    msgs: list[dict] = []
    spark: list[dict] = []
    events: list[dict] = []
    files: dict[str, dict] = {}
    cwd = branch = ""
    first_ts: str | None = None
    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not cwd and d.get("cwd"):
                cwd = d["cwd"]
            if not branch and d.get("gitBranch"):
                branch = d["gitBranch"]
            ts = d.get("timestamp") or ""
            if ts and not first_ts:
                first_ts = ts
            m = d.get("message")
            if not isinstance(m, dict):
                continue
            role = m.get("role", "")
            u = m.get("usage")
            if isinstance(u, dict):
                in_t += u.get("input_tokens", 0) or 0
                out_t += u.get("output_tokens", 0) or 0
                cache_r += u.get("cache_read_input_tokens", 0) or 0
                cache_w += u.get("cache_creation_input_tokens", 0) or 0
                spark.append({"ts": ts, "out": u.get("output_tokens", 0) or 0})
            c = m.get("content")
            text = ""
            tool_names_here: list[str] = []
            if isinstance(c, str):
                text = c
            elif isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        nm = b.get("name", "")
                        tools[nm] = tools.get(nm, 0) + 1
                        tool_names_here.append(nm)
                        inp = b.get("input")
                        if isinstance(inp, dict):
                            fp = inp.get("file_path") or inp.get("notebook_path") or inp.get("path")
                            if fp and isinstance(fp, str):
                                f = files.setdefault(fp, {"read": 0, "edit": 0, "write": 0})
                                if nm in ("Edit", "MultiEdit", "NotebookEdit"):
                                    f["edit"] += 1
                                elif nm == "Write":
                                    f["write"] += 1
                                elif nm == "Read":
                                    f["read"] += 1
                    elif b.get("type") == "text" and not text:
                        text = b.get("text", "")
            text = text.strip()
            shown = bool(text) and not text.startswith("<")
            if shown:
                msgs.append({"role": role, "text": text[:MAX_MSG_BYTES], "ts": ts})
            if ts:
                if role == "user" and shown:
                    events.append({"ts": ts, "kind": "user"})
                elif role == "assistant":
                    for nm in tool_names_here:
                        events.append({"ts": ts, "kind": "tool", "name": nm})
                    if not tool_names_here and shown:
                        events.append({"ts": ts, "kind": "assistant"})
    return {
        "cwd": cwd,
        "branch": branch,
        "first_ts": first_ts,
        "in": in_t,
        "out": out_t,
        "cache_r": cache_r,
        "cache_w": cache_w,
        "tools": tools,
        "msgs": msgs,
        "spark": spark,
        "events": events,
        "files": files,
    }


def scan() -> list[dict]:
    """List all sessions sorted by mtime desc, with cheap metadata for the sidebar."""
    now = time.time()
    out = []
    for path in glob.glob(os.path.join(ROOT, "*", "*.jsonl")):
        try:
            st = os.stat(path)
        except FileNotFoundError:
            continue
        info = session_meta(path, st.st_mtime)
        if info is None:
            continue
        age = now - st.st_mtime
        status = "busy" if age < 60 else "idle" if age < 1800 else "dead"
        title = info["ai_title"] or info["first_user"] or "(untitled)"
        if info["last_role"] == "assistant" and info["last_tool"]:
            activity = "running " + info["last_tool"]
        elif info["last_role"] == "assistant" and info["last_text"]:
            activity = "replied: " + info["last_text"]
        elif info["last_role"] == "user":
            activity = "waiting: " + info["last_user"]
        else:
            activity = ""
        out.append(
            {
                "id": os.path.basename(path)[:-6],
                "project": os.path.basename(os.path.dirname(path)),
                "cwd": short_path(info["cwd"]) if info["cwd"] else "",
                "branch": info["branch"],
                "status": status,
                "mtime": st.st_mtime,
                "age": age,
                "title": title,
                "activity": activity,
                "slug": info["slug"],
                "last_user": info["last_user"],
            }
        )
    out.sort(key=lambda x: -x["mtime"])
    return out
