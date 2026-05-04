"""Per-session detail view: aggregates parse_session output into the API response shape."""

from __future__ import annotations

import datetime

from claudeboard.git import git_activity, session_diff
from claudeboard.sessions import find_session, parse_session, short_path

TURN_CHARS = 480
TURN_LIMIT = 60


def trim_turn(m: dict) -> dict:
    t = m["text"]
    if len(t) > TURN_CHARS:
        t = t[:TURN_CHARS].rstrip() + "..."
    return {"role": m["role"], "text": t, "ts": m["ts"]}


def cost_estimate(in_t: int, out_t: int, cache_r: int, cache_w: int) -> float:
    """Rough USD cost at Sonnet 4.x list pricing.

    Real cost varies by model (Opus, Haiku) and tier; this is a single-rate estimate.
    """
    return round((in_t * 3 + out_t * 15 + cache_r * 0.30 + cache_w * 3.75) / 1e6, 4)


def time_breakdown(events: list[dict]) -> dict | None:
    """Active vs idle wall-clock seconds. Gaps under 5 minutes count as continuous activity."""
    ts: list[float] = []
    for e in events:
        s = e.get("ts")
        if not s:
            continue
        try:
            t = datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
            ts.append(t)
        except (ValueError, AttributeError):
            continue
    if len(ts) < 2:
        return None
    ts.sort()
    elapsed = ts[-1] - ts[0]
    active = 0.0
    for i in range(1, len(ts)):
        gap = ts[i] - ts[i - 1]
        if gap < 300:
            active += gap
    return {"elapsed": int(elapsed), "active": int(active), "idle": int(elapsed - active)}


def detail(sid: str) -> dict | None:
    path = find_session(sid)
    if not path:
        return None
    s = parse_session(path)
    files_list = sorted(
        ({"path": short_path(p), **counts} for p, counts in s["files"].items()),
        key=lambda x: -(x["edit"] * 3 + x["write"] * 3 + x["read"]),
    )
    return {
        "id": sid,
        "cwd": short_path(s["cwd"]) if s["cwd"] else "",
        "branch": s["branch"],
        "stats": {
            "in": s["in"],
            "out": s["out"],
            "cache_r": s["cache_r"],
            "cache_w": s["cache_w"],
            "msgs": len(s["msgs"]),
            "tools_total": sum(s["tools"].values()),
        },
        "tools": sorted(s["tools"].items(), key=lambda x: -x[1]),
        "files": files_list[:30],
        "session_diff": session_diff(s["cwd"], s["first_ts"]),
        "time": time_breakdown(s["events"]),
        "cost": cost_estimate(s["in"], s["out"], s["cache_r"], s["cache_w"]),
        "git": git_activity(s["cwd"], s["first_ts"]),
        "messages": [trim_turn(m) for m in s["msgs"][-TURN_LIMIT:]],
    }
