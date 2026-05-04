from __future__ import annotations

import datetime

from claudeboard.git import git_activity, session_diff
from claudeboard.sessions import find_session, model_cost, parse_session, price_for, short_path

TURN_CHARS = 480
TURN_LIMIT = 60


def trim_turn(m: dict) -> dict:
    t = m["text"]
    if len(t) > TURN_CHARS:
        t = t[:TURN_CHARS].rstrip() + "..."
    return {"role": m["role"], "text": t, "ts": m["ts"]}


def cost_breakdown(by_model: dict[str, dict[str, int]]) -> dict:
    in_c = out_c = cr_c = cw_c = 0.0
    for model, t in by_model.items():
        p = price_for(model)
        in_c += t.get("in", 0) * p[0] / 1e6
        out_c += t.get("out", 0) * p[1] / 1e6
        cr_c += t.get("cache_r", 0) * p[2] / 1e6
        cw_c += t.get("cache_w", 0) * p[3] / 1e6
    return {
        "in": round(in_c, 4),
        "out": round(out_c, 4),
        "cache_r": round(cr_c, 4),
        "cache_w": round(cw_c, 4),
    }


# Active vs idle wall-clock seconds. Gaps under 5 minutes count as continuous activity.
def time_breakdown(events: list[dict]) -> dict | None:
    ts: list[float] = []
    for e in events:
        s = e.get("ts")
        if not s:
            continue
        try:
            ts.append(datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
        except (ValueError, AttributeError):
            continue
    if len(ts) < 2:
        return None
    ts.sort()
    elapsed = ts[-1] - ts[0]
    # Gaps under 5 min count as continuous activity.
    active = sum(g for g in (ts[i] - ts[i - 1] for i in range(1, len(ts))) if g < 300)
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
    turns = s["turns"]
    tools_total = sum(s["tools"].values())
    total_cost, per_model = model_cost(s["by_model"])
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
            "turns": turns,
            "tools_total": tools_total,
            "avg_out_per_turn": int(s["out"] / turns) if turns else 0,
            "tools_per_turn": round(tools_total / turns, 2) if turns else 0,
            "api_errors": s["api_errors"],
            "cost_per_turn": round(total_cost / turns, 4) if turns else 0,
            "cost_mix": cost_breakdown(s["by_model"]),
            "cost_by_model": per_model,
        },
        "tools": sorted(s["tools"].items(), key=lambda x: -x[1]),
        "files": files_list[:30],
        "session_diff": session_diff(s["cwd"], s["first_ts"]),
        "time": time_breakdown(s["events"]),
        "cost": total_cost,
        "git": git_activity(s["cwd"], s["first_ts"]),
        "messages": [trim_turn(m) for m in s["msgs"][-TURN_LIMIT:]],
    }
