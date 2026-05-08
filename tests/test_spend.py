from __future__ import annotations

import json

from claudeboard import spend


def test_parse_ts_handles_z_and_offset():
    assert spend._parse_ts("2026-05-04T01:00:00.000Z") is not None
    assert spend._parse_ts("2026-05-04T01:00:00+00:00") is not None
    assert spend._parse_ts("") is None
    assert spend._parse_ts("garbage") is None


def test_aggregate_spend_buckets_and_totals(fake_root, monkeypatch):
    monkeypatch.setattr("claudeboard.spend.ROOT", str(fake_root))
    monkeypatch.setattr("claudeboard.spend._timeline_cache", {})
    # Sample fixture spans 2026-05-04T01:00 -> 01:03 UTC
    import datetime

    start = datetime.datetime(2026, 5, 4, 0, tzinfo=datetime.timezone.utc).timestamp()
    end = datetime.datetime(2026, 5, 4, 2, tzinfo=datetime.timezone.utc).timestamp()
    d = spend.aggregate_spend(start, end, buckets=4)
    assert d["session_count"] == 1
    assert d["total_cost"] > 0
    assert len(d["series"]) == 4
    # Activity is in the second bucket (01:00-01:30 UTC)
    nonzero = [s for s in d["series"] if s["cost"] > 0]
    assert len(nonzero) >= 1
    # Token totals should match the fixture's single usage entry
    assert d["by_token_count"]["in"] == 100
    assert d["by_token_count"]["out"] == 50
    assert d["by_token_count"]["cache_r"] == 1000
    assert d["by_token_count"]["cache_w"] == 500
    assert d["top_sessions"][0]["id"] == "12345678-1234-1234-1234-123456789abc"


def test_aggregate_spend_empty_window(fake_root, monkeypatch):
    monkeypatch.setattr("claudeboard.spend.ROOT", str(fake_root))
    monkeypatch.setattr("claudeboard.spend._timeline_cache", {})
    d = spend.aggregate_spend(0, 1, buckets=10)
    assert d["total_cost"] == 0
    assert d["session_count"] == 0
    assert d["top_sessions"] == []
    assert d["top_projects"] == []


def test_aggregate_spend_caches_timelines(tmp_path, monkeypatch):
    proj = tmp_path / "claude-projects" / "-tmp-x"
    proj.mkdir(parents=True)
    sid = "abcdef01-2345-6789-abcd-ef0123456789"
    p = proj / f"{sid}.jsonl"
    p.write_text(
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-05-04T01:00:00.000Z",
                "message": {
                    "id": "m1",
                    "role": "assistant",
                    "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cache_read_input_tokens": 1,
                        "cache_creation_input_tokens": 1,
                    },
                },
            }
        )
        + "\n"
    )
    monkeypatch.setattr("claudeboard.spend.ROOT", str(tmp_path / "claude-projects"))
    monkeypatch.setattr("claudeboard.spend._timeline_cache", {})
    mtime = p.stat().st_mtime
    t1 = spend._load_timeline(str(p), mtime)
    t2 = spend._load_timeline(str(p), mtime)
    assert t1 is t2
    t3 = spend._load_timeline(str(p), mtime + 1)
    assert t3 is not t1
