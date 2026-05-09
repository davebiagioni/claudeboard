from __future__ import annotations

import glob
import json
import os
from datetime import datetime

from claudeboard.sessions import ROOT, price_for, short_path

_timeline_cache: dict[str, tuple[float, list[tuple[float, str, int, int, int, int]]]] = {}


def _parse_ts(ts: str) -> float | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return None


def _load_timeline(path: str, mtime: float) -> list[tuple[float, str, int, int, int, int]]:
    hit = _timeline_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    out: list[tuple[float, str, int, int, int, int]] = []
    seen: set = set()
    try:
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                m = d.get("message")
                if not isinstance(m, dict):
                    continue
                u = m.get("usage")
                if not isinstance(u, dict):
                    continue
                key = d.get("requestId") or m.get("id")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                ts = _parse_ts(d.get("timestamp") or "")
                if ts is None:
                    continue
                model = m.get("model") or "unknown"
                out.append(
                    (
                        ts,
                        model,
                        u.get("input_tokens", 0) or 0,
                        u.get("output_tokens", 0) or 0,
                        u.get("cache_read_input_tokens", 0) or 0,
                        u.get("cache_creation_input_tokens", 0) or 0,
                    )
                )
    except OSError:
        return []
    _timeline_cache[path] = (mtime, out)
    return out


def _session_meta(path: str) -> tuple[str, str]:
    cwd = ""
    try:
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("cwd"):
                    cwd = d["cwd"]
                    break
    except OSError:
        pass
    project = os.path.basename(os.path.dirname(path))
    return cwd, project


def aggregate_spend(start: float, end: float, buckets: int = 60) -> dict:
    if end <= start:
        end = start + 1.0
    buckets = max(1, min(200, buckets))
    bucket_size = (end - start) / buckets

    paths = glob.glob(os.path.join(ROOT, "*", "*.jsonl"))

    series_cost = [0.0] * buckets
    series_by_model: list[dict[str, float]] = [dict() for _ in range(buckets)]

    by_model_total: dict[str, dict] = {}
    by_token_cost = {"in": 0.0, "out": 0.0, "cache_r": 0.0, "cache_w": 0.0}
    by_token_count = {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0}
    by_session: dict[str, dict] = {}
    by_project: dict[str, float] = {}

    for path in paths:
        try:
            mtime = os.stat(path).st_mtime
        except FileNotFoundError:
            continue
        timeline = _load_timeline(path, mtime)
        if not timeline:
            continue
        sid = os.path.basename(path)[:-6]
        project = os.path.basename(os.path.dirname(path))
        sess_cost = 0.0
        sess_first_ts: float | None = None
        sess_last_ts: float | None = None
        for ts, model, in_t, out_t, cr, cw in timeline:
            if ts < start or ts >= end:
                continue
            p = price_for(model)
            cost = (in_t * p[0] + out_t * p[1] + cr * p[2] + cw * p[3]) / 1e6

            idx = int((ts - start) / bucket_size)
            if idx < 0:
                idx = 0
            elif idx >= buckets:
                idx = buckets - 1
            series_cost[idx] += cost
            series_by_model[idx][model] = series_by_model[idx].get(model, 0.0) + cost

            bm = by_model_total.setdefault(
                model, {"cost": 0.0, "in": 0, "out": 0, "cache_r": 0, "cache_w": 0}
            )
            bm["cost"] += cost
            bm["in"] += in_t
            bm["out"] += out_t
            bm["cache_r"] += cr
            bm["cache_w"] += cw

            by_token_cost["in"] += in_t * p[0] / 1e6
            by_token_cost["out"] += out_t * p[1] / 1e6
            by_token_cost["cache_r"] += cr * p[2] / 1e6
            by_token_cost["cache_w"] += cw * p[3] / 1e6

            by_token_count["in"] += in_t
            by_token_count["out"] += out_t
            by_token_count["cache_r"] += cr
            by_token_count["cache_w"] += cw

            sess_cost += cost
            if sess_first_ts is None or ts < sess_first_ts:
                sess_first_ts = ts
            if sess_last_ts is None or ts > sess_last_ts:
                sess_last_ts = ts

        if sess_cost > 0:
            cwd, _ = _session_meta(path)
            by_session[sid] = {
                "cost": round(sess_cost, 4),
                "project": project,
                "cwd": short_path(cwd) if cwd else "",
                "first_ts": sess_first_ts,
                "last_ts": sess_last_ts,
            }
            by_project[project] = by_project.get(project, 0.0) + sess_cost

    total_cost = sum(series_cost)

    series = [
        {
            "t": start + i * bucket_size,
            "cost": round(series_cost[i], 6),
            "by_model": {m: round(c, 6) for m, c in series_by_model[i].items()},
        }
        for i in range(buckets)
    ]

    by_model_out = {
        m: {
            "cost": round(v["cost"], 4),
            "in": v["in"],
            "out": v["out"],
            "cache_r": v["cache_r"],
            "cache_w": v["cache_w"],
        }
        for m, v in by_model_total.items()
    }

    top_sessions = sorted(
        (
            {
                "id": sid,
                "cost": v["cost"],
                "project": v["project"],
                "cwd": v["cwd"],
                "first_ts": v["first_ts"],
                "last_ts": v["last_ts"],
            }
            for sid, v in by_session.items()
        ),
        key=lambda x: -x["cost"],
    )[:20]

    top_projects = sorted(
        ({"project": k, "cost": round(v, 4)} for k, v in by_project.items()),
        key=lambda x: -x["cost"],
    )[:20]

    return {
        "start": start,
        "end": end,
        "bucket_size": bucket_size,
        "series": series,
        "total_cost": round(total_cost, 4),
        "by_model": by_model_out,
        "by_token_cost": {k: round(v, 4) for k, v in by_token_cost.items()},
        "by_token_count": by_token_count,
        "top_sessions": top_sessions,
        "top_projects": top_projects,
        "session_count": len(by_session),
    }
