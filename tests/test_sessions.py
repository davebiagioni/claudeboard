"""Tests for sessions.parse_session, session_meta, scan, short_path."""

from __future__ import annotations

import os

from claudeboard import sessions


def test_short_path_replaces_home():
    home = os.path.expanduser("~")
    assert sessions.short_path(home + "/dev/foo") == "~/dev/foo"


def test_short_path_leaves_other_paths_alone():
    assert sessions.short_path("/tmp/foo") == "/tmp/foo"
    assert sessions.short_path("") == ""


def test_session_meta_extracts_fields(sample_jsonl):
    info = sessions.session_meta(str(sample_jsonl), sample_jsonl.stat().st_mtime)
    assert info is not None
    assert info["cwd"] == "/tmp/claudeboard-test"
    assert info["branch"] == "main"
    assert info["ai_title"] == "Test session"
    assert info["slug"] == "test-slug-name"
    assert info["first_user"] == "do the thing"
    assert info["last_user"] == "another prompt"
    assert info["last_role"] == "user"
    # Cost from sample fixture: in=100, out=50, cache_r=1000, cache_w=500
    # = (300 + 750 + 300 + 1875) / 1e6 = 0.003225
    assert info["cost"] == 0.0032


def test_session_meta_caches_by_mtime(sample_jsonl, monkeypatch):
    info1 = sessions.session_meta(str(sample_jsonl), 1.0)
    info2 = sessions.session_meta(str(sample_jsonl), 1.0)
    assert info1 is info2  # same dict instance from cache
    info3 = sessions.session_meta(str(sample_jsonl), 2.0)
    assert info3 is not info1  # mtime changed -> recomputed


def test_session_meta_returns_none_for_missing_file(tmp_path):
    info = sessions.session_meta(str(tmp_path / "does-not-exist.jsonl"), 0.0)
    assert info is None


def test_parse_session_aggregates(sample_jsonl):
    s = sessions.parse_session(str(sample_jsonl))
    assert s["cwd"] == "/tmp/claudeboard-test"
    assert s["branch"] == "main"
    assert s["first_ts"] == "2026-05-04T01:00:00.000Z"
    assert s["in"] == 100
    assert s["out"] == 50
    assert s["cache_r"] == 1000
    assert s["cache_w"] == 500
    assert s["tools"] == {"Edit": 1, "Read": 1}
    assert s["files"] == {"/tmp/claudeboard-test/foo.py": {"read": 1, "edit": 1, "write": 0}}
    # Three text-bearing turns: do the thing, done, another prompt
    assert len(s["msgs"]) == 3
    assert s["msgs"][0]["role"] == "user"
    assert s["msgs"][-1]["text"] == "another prompt"


def test_parse_session_events_have_timestamps(sample_jsonl):
    s = sessions.parse_session(str(sample_jsonl))
    kinds = [e["kind"] for e in s["events"]]
    assert kinds[0] == "user"
    # Two assistant tool events
    assert kinds.count("tool") == 2
    assert {e.get("name") for e in s["events"] if e["kind"] == "tool"} == {"Edit", "Read"}


def test_parse_session_skips_malformed_lines(malformed_jsonl):
    s = sessions.parse_session(str(malformed_jsonl))
    # Should still pick up the user record (the one that's valid)
    assert s["cwd"] == "/tmp/claudeboard-test"


def test_parse_session_handles_empty_file(empty_jsonl):
    s = sessions.parse_session(str(empty_jsonl))
    assert s["msgs"] == []
    assert s["tools"] == {}
    assert s["events"] == []


def test_scan_returns_session_with_expected_fields(fake_root):
    rows = sessions.scan()
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == "12345678-1234-1234-1234-123456789abc"
    assert r["cwd"]  # short_path applied
    assert r["title"] == "Test session"
    assert r["slug"] == "test-slug-name"
    assert r["status"] in ("busy", "idle", "dead")
    # last_role is user (last record), so activity should be "waiting:..."
    assert r["activity"].startswith("waiting:")


def test_find_session_returns_path(fake_root):
    sid = "12345678-1234-1234-1234-123456789abc"
    path = sessions.find_session(sid)
    assert path is not None
    assert path.endswith(sid + ".jsonl")


def test_find_session_returns_none_for_missing(fake_root):
    assert sessions.find_session("does-not-exist") is None


def test_live_session_paths_picks_top_n_by_mtime(tmp_path):
    proj = tmp_path / "-Users-dave-dev-foo"
    proj.mkdir()
    older = proj / "older.jsonl"
    middle = proj / "middle.jsonl"
    newer = proj / "newer.jsonl"
    older.write_text("")
    middle.write_text("")
    newer.write_text("")
    os = __import__("os")
    os.utime(older, (1000, 1000))
    os.utime(middle, (2000, 2000))
    os.utime(newer, (3000, 3000))
    cwd_counts = {"/Users/dave/dev/foo": 2}
    live = sessions._live_session_paths([str(older), str(middle), str(newer)], cwd_counts)
    assert live == {str(newer), str(middle)}


def test_live_session_paths_empty_when_no_processes():
    assert sessions._live_session_paths(["/anything.jsonl"], {}) == set()


def test_live_session_paths_unmatched_cwd_returns_empty(tmp_path):
    cwd_counts = {"/some/random/cwd": 5}
    assert sessions._live_session_paths([], cwd_counts) == set()
