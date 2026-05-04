"""Tests for detail.cost_estimate, time_breakdown, trim_turn, detail."""

from __future__ import annotations

from claudeboard import detail


def test_cost_estimate_zero():
    assert detail.cost_estimate(0, 0, 0, 0) == 0


def test_cost_estimate_known_values():
    # 1M input @ $3, 1M output @ $15, 1M cache_r @ $0.30, 1M cache_w @ $3.75
    cost = detail.cost_estimate(1_000_000, 1_000_000, 1_000_000, 1_000_000)
    assert cost == 22.05


def test_cost_estimate_realistic_session():
    # 100*3 + 50*15 + 1000*0.30 + 500*3.75 = 3225, divided by 1e6 = 0.003225
    cost = detail.cost_estimate(100, 50, 1000, 500)
    assert cost == 0.0032


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
