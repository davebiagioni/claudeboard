from __future__ import annotations

import glob
import json
import os
import subprocess
import time

ROOT = os.path.expanduser("~/.claude/projects")
SESSIONS_STATE_DIR = os.path.expanduser("~/.claude/sessions")
MAX_MSG_BYTES = 50_000

# (input, output, cache_read, cache_write_5m) USD per 1M tokens.
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


def _todo_summary(todos: list) -> dict | None:
    if not todos:
        return None
    total = len(todos)
    done = sum(1 for t in todos if isinstance(t, dict) and t.get("status") == "completed")
    current = ""
    for t in todos:
        if isinstance(t, dict) and t.get("status") == "in_progress":
            current = t.get("activeForm") or t.get("content", "")
            break
    if not current:
        for t in todos:
            if isinstance(t, dict) and t.get("status") != "completed":
                current = t.get("activeForm") or t.get("content", "")
                break
    return {"done": done, "total": total, "current": (current or "")[:200]}


# Returns None if the file disappeared mid-read.
def session_meta(path: str, mtime: float) -> dict | None:
    hit = _meta_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    cwd = branch = ai_title = slug = ""
    first_user = last_user = last_text = last_tool = last_role = ""
    last_assistant_kind = ""
    todos: list = []
    recent_tools: list[str] = []
    api_errors = 0
    turns = 0
    by_model: dict[str, dict[str, int]] = {}
    seen: set = set()
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
                if d.get("type") == "system" and d.get("subtype") == "api_error":
                    api_errors += 1
                m = d.get("message")
                if not isinstance(m, dict):
                    continue
                u = m.get("usage")
                # Claude Code splits one assistant API response into multiple
                # jsonl rows (thinking/text/tool_use), each redundantly carrying
                # the same usage. Dedup by requestId/message.id so cost isn't
                # multiplied by the number of content blocks.
                if isinstance(u, dict):
                    key = d.get("requestId") or m.get("id")
                    if key and key in seen:
                        u = None
                    elif key:
                        seen.add(key)
                if isinstance(u, dict):
                    model = m.get("model") or "unknown"
                    bm = by_model.setdefault(model, {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0})
                    bm["in"] += u.get("input_tokens", 0) or 0
                    bm["out"] += u.get("output_tokens", 0) or 0
                    bm["cache_r"] += u.get("cache_read_input_tokens", 0) or 0
                    bm["cache_w"] += u.get("cache_creation_input_tokens", 0) or 0
                    turns += 1
                role = m.get("role", "")
                c = m.get("content")
                text = ""
                tool = ""
                row_tools: list[str] = []
                if isinstance(c, str):
                    text = c
                elif isinstance(c, list):
                    for b in c:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text" and not text:
                            text = b.get("text", "")
                        elif b.get("type") == "tool_use":
                            nm = b.get("name", "")
                            row_tools.append(nm)
                            if not tool:
                                tool = nm
                            if nm == "TodoWrite":
                                inp = b.get("input")
                                if isinstance(inp, dict):
                                    t = inp.get("todos")
                                    if isinstance(t, list):
                                        todos = t
                if role == "assistant" and row_tools:
                    recent_tools.extend(row_tools)
                    if len(recent_tools) > 12:
                        recent_tools = recent_tools[-12:]
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
                        last_assistant_kind = "tool"
                    elif text:
                        last_assistant_kind = "text"
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
        "last_assistant_kind": last_assistant_kind,
        "cost": cost,
        "models": sorted(by_model.keys()),
        "todos": _todo_summary(todos),
        "recent_tools": recent_tools[-8:],
        "api_errors": api_errors,
        "turns": turns,
    }
    _meta_cache[path] = (mtime, info)
    return info


def parse_session(path: str) -> dict:
    in_t = out_t = cache_r = cache_w = 0
    turns = 0
    by_model: dict[str, dict[str, int]] = {}
    api_errors = 0
    tools: dict[str, int] = {}
    msgs: list[dict] = []
    events: list[dict] = []
    files: dict[str, dict] = {}
    cwd = branch = ""
    first_ts: str | None = None
    seen: set = set()
    with open(path) as fh:
        for line in fh:
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
            # See session_meta: dedup split assistant rows by requestId/id.
            if isinstance(u, dict):
                key = d.get("requestId") or m.get("id")
                if key and key in seen:
                    u = None
                elif key:
                    seen.add(key)
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
                turns += 1
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
                                fc = files.setdefault(fp, {"read": 0, "edit": 0, "write": 0})
                                if nm in ("Edit", "MultiEdit", "NotebookEdit"):
                                    fc["edit"] += 1
                                elif nm == "Write":
                                    fc["write"] += 1
                                elif nm == "Read":
                                    fc["read"] += 1
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
        "turns": turns,
        "events": events,
        "files": files,
        "api_errors": api_errors,
        "by_model": by_model,
    }


def _running_claude_pids() -> set[str]:
    try:
        r = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True, text=True, timeout=2)
    except (subprocess.TimeoutExpired, OSError):
        return set()
    pids: set[str] = set()
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and os.path.basename(parts[1].strip()) == "claude":
            pids.add(parts[0].strip())
    return pids


# Returns {jsonl_path: {"status", "updated_at"}} for live claude processes.
# claude writes ~/.claude/sessions/<pid>.json with {pid, sessionId, cwd,
# status, updatedAt, ...} for each live process — authoritative pid→session
# mapping. updatedAt advances only on real state changes (busy↔idle), so it
# distinguishes "just finished" from "long parked."
# Stale entries (pid no longer running) are filtered out.
def claude_session_state() -> dict[str, dict]:
    try:
        entries = os.listdir(SESSIONS_STATE_DIR)
    except OSError:
        return {}
    if not entries:
        return {}
    running = _running_claude_pids()
    out: dict[str, dict] = {}
    for name in entries:
        if not name.endswith(".json"):
            continue
        pid = name[:-5]
        if running and pid not in running:
            continue
        try:
            with open(os.path.join(SESSIONS_STATE_DIR, name)) as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        sid = d.get("sessionId")
        cwd = d.get("cwd")
        if not sid or not cwd:
            continue
        proj = cwd.replace("/", "-")
        jsonl_path = os.path.join(ROOT, proj, f"{sid}.jsonl")
        if not os.path.exists(jsonl_path):
            continue
        ts = d.get("updatedAt") or 0
        out[jsonl_path] = {
            "status": d.get("status") or "",
            "updated_at": ts / 1000.0 if ts else 0.0,
        }
    return out


def claude_cwd_counts() -> dict[str, int]:
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


_STATUS_RANK = {"busy": 0, "ready": 1, "idle": 2, "dead": 3}
# How recently claude must have transitioned to idle for the session to count
# as "ready". Older idle sessions are just idle — the user has already moved on.
READY_FRESHNESS_SECS = 600


def _status_for(
    age: float,
    is_live: bool,
    info: dict,
    claude_status: str = "",
    updated_at: float = 0.0,
    now: float | None = None,
) -> str:
    if not is_live:
        return "busy" if age < 60 else "dead"
    if claude_status == "busy":
        return "busy"
    if info["last_role"] == "assistant" and info["last_assistant_kind"] == "text":
        # Only freshly-transitioned idle counts as "needs you". A session that
        # has been parked at idle for an hour isn't waiting on you in any
        # meaningful sense — you've moved on.
        if updated_at:
            t = now if now is not None else time.time()
            if (t - updated_at) > READY_FRESHNESS_SECS:
                return "idle"
        return "ready"
    if claude_status == "idle":
        return "idle"
    if age < 30:
        return "busy"
    return "idle"


def _warnings_for(info: dict) -> list[str]:
    w: list[str] = []
    if info.get("api_errors"):
        w.append("api_err")
    recent = info.get("recent_tools") or []
    if len(recent) >= 4 and len(set(recent[-4:])) == 1:
        w.append("loop")
    turns = info.get("turns") or 0
    cost = info.get("cost") or 0
    if turns >= 5 and (cost / turns) > 1.0:
        w.append("burn")
    return w


def scan() -> list[dict]:
    now = time.time()
    paths = glob.glob(os.path.join(ROOT, "*", "*.jsonl"))
    state = claude_session_state()
    if state:
        live: set[str] = set(state.keys())
    else:
        # No state files (older claude versions, or none running): fall back.
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
        st_entry = state.get(path) or {}
        status = _status_for(
            age,
            path in live,
            info,
            st_entry.get("status", ""),
            st_entry.get("updated_at", 0.0),
            now,
        )
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
                "todos": info.get("todos"),
                "warnings": _warnings_for(info),
                "api_errors": info.get("api_errors", 0),
                "turns": info.get("turns", 0),
                "updated_at": st_entry.get("updated_at", 0.0),
            }
        )
    out.sort(key=lambda x: (_STATUS_RANK.get(x["status"], 9), -x["mtime"]))
    return out
