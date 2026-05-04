from __future__ import annotations

from claudeboard import detail


def test_cost_breakdown_empty():
    out = detail.cost_breakdown({})
    assert out == {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0}


def test_cost_breakdown_per_model():
    # Opus: 1M each at (15, 75, 1.50, 18.75)
    by_model = {
        "claude-opus-4-7": {
            "in": 1_000_000,
            "out": 1_000_000,
            "cache_r": 1_000_000,
            "cache_w": 1_000_000,
        }
    }
    out = detail.cost_breakdown(by_model)
    assert out == {"in": 15.0, "out": 75.0, "cache_r": 1.5, "cache_w": 18.75}


def test_cost_breakdown_mixed_models():
    by_model = {
        "claude-opus-4-7": {"in": 1_000_000, "out": 0, "cache_r": 0, "cache_w": 0},
        "claude-sonnet-4-6": {"in": 1_000_000, "out": 0, "cache_r": 0, "cache_w": 0},
    }
    out = detail.cost_breakdown(by_model)
    # Opus $15 + Sonnet $3 = $18 input cost
    assert out["in"] == 18.0


def test_time_breakdown_basic():
    events = [
        {"ts": "2026-05-04T01:00:00.000Z"},
        {"ts": "2026-05-04T01:00:30.000Z"},
        {"ts": "2026-05-04T01:01:00.000Z"},
    ]
    t = detail.time_breakdown(events)
    assert t is not None
    assert t["elapsed"] == 60
    assert t["active"] == 60
    assert t["idle"] == 0


def test_time_breakdown_with_idle_gap():
    events = [
        {"ts": "2026-05-04T01:00:00.000Z"},
        {"ts": "2026-05-04T01:00:30.000Z"},
        # 10 minute gap → counted as idle
        {"ts": "2026-05-04T01:10:30.000Z"},
        {"ts": "2026-05-04T01:11:00.000Z"},
    ]
    t = detail.time_breakdown(events)
    assert t is not None
    assert t["elapsed"] == 660
    assert t["active"] == 60  # two 30s gaps both under threshold
    assert t["idle"] == 600


def test_time_breakdown_too_few_events():
    assert detail.time_breakdown([]) is None
    assert detail.time_breakdown([{"ts": "2026-05-04T01:00:00.000Z"}]) is None


def test_time_breakdown_skips_invalid_timestamps():
    events = [
        {"ts": "not a date"},
        {"ts": "2026-05-04T01:00:00.000Z"},
        {"ts": ""},
        {"ts": "2026-05-04T01:00:30.000Z"},
    ]
    t = detail.time_breakdown(events)
    assert t is not None
    assert t["elapsed"] == 30


def test_trim_turn_truncates_long_text():
    long = "x" * 1000
    out = detail.trim_turn({"role": "user", "text": long, "ts": "t"})
    assert len(out["text"]) == detail.TURN_CHARS + 3  # + "..."
    assert out["text"].endswith("...")


def test_trim_turn_leaves_short_text_alone():
    out = detail.trim_turn({"role": "user", "text": "short", "ts": "t"})
    assert out["text"] == "short"


def test_detail_returns_none_for_missing_session(fake_root):
    assert detail.detail("00000000-0000-0000-0000-000000000000") is None


def test_detail_returns_full_response(fake_root):
    sid = "12345678-1234-1234-1234-123456789abc"
    d = detail.detail(sid)
    assert d is not None
    assert d["id"] == sid
    assert d["stats"]["msgs"] == 3
    assert d["stats"]["tools_total"] == 2
    assert d["cost"] >= 0
    assert isinstance(d["tools"], list)
    assert isinstance(d["files"], list)
    assert isinstance(d["messages"], list)
    # No git repo at the cwd, so git is None
    assert d["git"] is None or d["git"].get("error")


def test_detail_includes_derived_stats(fake_root):
    sid = "12345678-1234-1234-1234-123456789abc"
    d = detail.detail(sid)
    s = d["stats"]
    # Sample: 1 assistant turn with usage (input=100, output=50, cache_r=1000, cache_w=500)
    assert s["turns"] == 1
    assert s["avg_out_per_turn"] == 50
    assert s["tools_per_turn"] == 2.0
    assert s["api_errors"] == 0
    # cost = (100*3 + 50*15 + 1000*0.30 + 500*3.75) / 1e6 = 0.003225
    assert s["cost_per_turn"] == 0.0032
    mix = s["cost_mix"]
    assert mix["in"] == 0.0003  # 100 * 3 / 1e6
    assert mix["out"] == 0.0008  # 50 * 15 / 1e6 = 0.00075 → 0.0008
    assert mix["cache_r"] == 0.0003  # 1000 * 0.30 / 1e6
    assert mix["cache_w"] == 0.0019  # 500 * 3.75 / 1e6 = 0.001875 → 0.0019


def test_detail_handles_zero_turns(fake_root, tmp_path, monkeypatch):
    project = tmp_path / "claude-projects" / "-tmp-empty"
    project.mkdir(parents=True)
    sid = "99999999-9999-9999-9999-999999999999"
    p = project / f"{sid}.jsonl"
    import json as _json

    p.write_text(
        _json.dumps(
            {
                "type": "user",
                "cwd": "/tmp/empty",
                "timestamp": "2026-05-04T01:00:00.000Z",
                "message": {"role": "user", "content": "hi"},
            }
        )
        + "\n"
    )
    monkeypatch.setattr("claudeboard.sessions.ROOT", str(tmp_path / "claude-projects"))
    monkeypatch.setattr("claudeboard.sessions._meta_cache", {})
    d = detail.detail(sid)
    assert d is not None
    assert d["stats"]["turns"] == 0
    assert d["stats"]["avg_out_per_turn"] == 0
    assert d["stats"]["tools_per_turn"] == 0
    assert d["stats"]["cost_per_turn"] == 0
