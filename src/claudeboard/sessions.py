"""Session jsonl loading: scanning the project dir, parsing files, caching by mtime."""

from __future__ import annotations

import glob
import json
import os
import subprocess
import time

ROOT = os.path.expanduser("~/.claude/projects")
MAX_MSG_BYTES = 50_000

# Anthropic list pricing in USD per 1M tokens: (input, output, cache_read, cache_write_5m).
# Cache write 5m is the standard; some calls may use 1h pricing but we approximate.
# Update when Anthropic updates pricing or when new model families ship.
PRICING: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-4-7": (15.0, 75.0, 1.50, 18.75),
    "claude-opus-4-6": (15.0, 75.0, 1.50, 18.75),
    "claude-opus-4-5": (15.0, 75.0, 1.50, 18.75),
    "claude-opus-4": (15.0, 75.0, 1.50, 18.75),
    "claude-sonnet-4-7": (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-4-5": (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-4": (3.0, 15.0, 0.30, 3.75),
    "claude-haiku-4-5": (1.0, 5.0, 0.10, 1.25),
    "claude-haiku-4": (1.0, 5.0, 0.10, 1.25),
}
DEFAULT_PRICING = (3.0, 15.0, 0.30, 3.75)


def price_for(model: str) -> tuple[float, float, float, float]:
    if not model:
        return DEFAULT_PRICING
    if model in PRICING:
        return PRICING[model]
    for k, v in PRICING.items():
        if model.startswith(k):
            return v
    return DEFAULT_PRICING


def model_cost(by_model: dict[str, dict[str, int]]) -> tuple[float, dict[str, float]]:
    """Return (total_cost_usd, per_model_cost) given a {model: {in/out/cache_r/cache_w}} map."""
    total = 0.0
    by_m: dict[str, float] = {}
    for model, t in by_model.items():
        p = price_for(model)
        c = (
            t.get("in", 0) * p[0]
            + t.get("out", 0) * p[1]
            + t.get("cache_r", 0) * p[2]
            + t.get("cache_w", 0) * p[3]
        ) / 1e6
        by_m[model] = round(c, 4)
        total += c
    return round(total, 4), by_m


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
    by_model: dict[str, dict[str, int]] = {}
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
                u = m.get("usage")
                if isinstance(u, dict):
                    model = m.get("model") or "unknown"
                    bm = by_model.setdefault(model, {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0})
                    bm["in"] += u.get("input_tokens", 0) or 0
                    bm["out"] += u.get("output_tokens", 0) or 0
                    bm["cache_r"] += u.get("cache_read_input_tokens", 0) or 0
                    bm["cache_w"] += u.get("cache_creation_input_tokens", 0) or 0
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
    cost, _ = model_cost(by_model)
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
        "cost": cost,
        "models": sorted(by_model.keys()),
    }
    _meta_cache[path] = (mtime, info)
    return info


def parse_session(path: str) -> dict:
    """Full parse of a session jsonl. Returns aggregates needed for the detail view."""
    in_t = out_t = cache_r = cache_w = 0
    by_model: dict[str, dict[str, int]] = {}
    api_errors = 0
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
            if d.get("type") == "system" and d.get("subtype") == "api_error":
                api_errors += 1
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
                model = m.get("model") or "unknown"
                bm = by_model.setdefault(model, {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0})
                bm["in"] += u.get("input_tokens", 0) or 0
                bm["out"] += u.get("output_tokens", 0) or 0
                bm["cache_r"] += u.get("cache_read_input_tokens", 0) or 0
                bm["cache_w"] += u.get("cache_creation_input_tokens", 0) or 0
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
        "api_errors": api_errors,
        "by_model": by_model,
    }


def claude_cwd_counts() -> dict[str, int]:
    """How many running `claude` processes have each cwd.

    Used to mark sessions whose terminal tab is still open as 'live' even if
    the jsonl hasn't been written to recently. Returns {} on any failure.
    """
    try:
        r = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True, text=True, timeout=2)
    except (subprocess.TimeoutExpired, OSError):
        return {}
    pids = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and os.path.basename(parts[1].strip()) == "claude":
            pids.append(parts[0].strip())
    if not pids:
        return {}
    try:
        r = subprocess.run(
            ["lsof", "-a", "-p", ",".join(pids), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        return {}
    counts: dict[str, int] = {}
    for line in r.stdout.splitlines():
        if line.startswith("n/"):
            cwd = line[1:]
            counts[cwd] = counts.get(cwd, 0) + 1
    return counts


def _live_session_paths(all_paths: list[str], cwd_counts: dict[str, int]) -> set[str]:
    """For each cwd with running claude(s), the N most-recent jsonls in its project dir are live."""
    if not cwd_counts:
        return set()
    by_project: dict[str, list[tuple[float, str]]] = {}
    for p in all_paths:
        try:
            mtime = os.stat(p).st_mtime
        except FileNotFoundError:
            continue
        proj = os.path.basename(os.path.dirname(p))
        by_project.setdefault(proj, []).append((mtime, p))
    live: set[str] = set()
    for cwd, n in cwd_counts.items():
        proj = cwd.replace("/", "-")
        files = by_project.get(proj)
        if not files:
            continue
        files.sort(reverse=True)
        for _, path in files[:n]:
            live.add(path)
    return live


def scan() -> list[dict]:
    """List all sessions sorted by mtime desc, with cheap metadata for the sidebar."""
    now = time.time()
    paths = glob.glob(os.path.join(ROOT, "*", "*.jsonl"))
    live = _live_session_paths(paths, claude_cwd_counts())
    out = []
    for path in paths:
        try:
            st = os.stat(path)
        except FileNotFoundError:
            continue
        info = session_meta(path, st.st_mtime)
        if info is None:
            continue
        age = now - st.st_mtime
        is_live = path in live
        if age < 60:
            status = "busy"
        elif is_live:
            status = "idle"
        else:
            status = "dead"
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
                "cost": info["cost"],
            }
        )
    out.sort(key=lambda x: (x["status"] == "dead", -x["mtime"]))
    return out
