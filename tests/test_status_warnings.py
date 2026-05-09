from __future__ import annotations

import json

from claudeboard import sessions


def _write_jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_todo_summary_picks_in_progress():
    todos = [
        {"content": "a", "activeForm": "doing a", "status": "completed"},
        {"content": "b", "activeForm": "doing b", "status": "in_progress"},
        {"content": "c", "activeForm": "doing c", "status": "pending"},
    ]
    assert sessions._todo_summary(todos) == {"done": 1, "total": 3, "current": "doing b"}


def test_todo_summary_falls_back_to_first_pending():
    todos = [
        {"content": "a", "activeForm": "doing a", "status": "completed"},
        {"content": "b", "activeForm": "doing b", "status": "pending"},
    ]
    assert sessions._todo_summary(todos) == {"done": 1, "total": 2, "current": "doing b"}


def test_todo_summary_empty_returns_none():
    assert sessions._todo_summary([]) is None


def test_session_meta_parses_latest_todowrite(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_jsonl(
        p,
        [
            {
                "type": "assistant",
                "timestamp": "2026-05-04T01:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "TodoWrite",
                            "input": {
                                "todos": [
                                    {
                                        "content": "x",
                                        "activeForm": "doing x",
                                        "status": "completed",
                                    },
                                    {"content": "y", "activeForm": "doing y", "status": "pending"},
                                ]
                            },
                        }
                    ],
                },
            },
            {
                "type": "assistant",
                "timestamp": "2026-05-04T01:01:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "TodoWrite",
                            "input": {
                                "todos": [
                                    {
                                        "content": "x",
                                        "activeForm": "doing x",
                                        "status": "completed",
                                    },
                                    {
                                        "content": "y",
                                        "activeForm": "doing y",
                                        "status": "in_progress",
                                    },
                                    {"content": "z", "activeForm": "doing z", "status": "pending"},
                                ]
                            },
                        }
                    ],
                },
            },
        ],
    )
    info = sessions.session_meta(str(p), p.stat().st_mtime)
    assert info is not None
    assert info["todos"] == {"done": 1, "total": 3, "current": "doing y"}


def test_session_meta_tracks_last_assistant_kind_text(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_jsonl(
        p,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "go"},
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Read", "input": {}}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "all done"}],
                },
            },
        ],
    )
    info = sessions.session_meta(str(p), p.stat().st_mtime)
    assert info["last_assistant_kind"] == "text"
    assert info["last_role"] == "assistant"


def test_session_meta_tracks_last_assistant_kind_tool(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_jsonl(
        p,
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "I'll edit it"}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                },
            },
        ],
    )
    info = sessions.session_meta(str(p), p.stat().st_mtime)
    assert info["last_assistant_kind"] == "tool"


def test_claude_session_state_filters_stale_pids(monkeypatch, tmp_path):
    state_dir = tmp_path / "sessions"
    state_dir.mkdir()
    proj = tmp_path / "projects" / "-tmp-x"
    proj.mkdir(parents=True)
    sid_running = "11111111-1111-1111-1111-111111111111"
    sid_stale = "22222222-2222-2222-2222-222222222222"
    (proj / f"{sid_running}.jsonl").write_text("")
    (proj / f"{sid_stale}.jsonl").write_text("")
    (state_dir / "1234.json").write_text(
        json.dumps(
            {
                "pid": 1234,
                "sessionId": sid_running,
                "cwd": "/tmp/x",
                "status": "busy",
                "updatedAt": 1700000000000,
            }
        )
    )
    (state_dir / "9999.json").write_text(
        json.dumps(
            {
                "pid": 9999,
                "sessionId": sid_stale,
                "cwd": "/tmp/x",
                "status": "idle",
                "updatedAt": 1700000000000,
            }
        )
    )
    monkeypatch.setattr("claudeboard.sessions.SESSIONS_STATE_DIR", str(state_dir))
    monkeypatch.setattr("claudeboard.sessions.ROOT", str(tmp_path / "projects"))
    monkeypatch.setattr("claudeboard.sessions._running_claude_pids", lambda: {"1234"})
    state = sessions.claude_session_state()
    assert len(state) == 1
    entry = state[str(proj / f"{sid_running}.jsonl")]
    assert entry["status"] == "busy"
    assert entry["updated_at"] == 1700000000.0


def test_claude_session_state_drops_entries_with_missing_jsonl(monkeypatch, tmp_path):
    state_dir = tmp_path / "sessions"
    state_dir.mkdir()
    sid = "33333333-3333-3333-3333-333333333333"
    (state_dir / "5555.json").write_text(
        json.dumps({"pid": 5555, "sessionId": sid, "cwd": "/tmp/x", "status": "busy"})
    )
    monkeypatch.setattr("claudeboard.sessions.SESSIONS_STATE_DIR", str(state_dir))
    monkeypatch.setattr("claudeboard.sessions.ROOT", str(tmp_path / "projects"))
    monkeypatch.setattr("claudeboard.sessions._running_claude_pids", lambda: {"5555"})
    assert sessions.claude_session_state() == {}


def test_claude_session_state_skips_malformed_json(monkeypatch, tmp_path):
    state_dir = tmp_path / "sessions"
    state_dir.mkdir()
    (state_dir / "1111.json").write_text("{not json")
    monkeypatch.setattr("claudeboard.sessions.SESSIONS_STATE_DIR", str(state_dir))
    monkeypatch.setattr("claudeboard.sessions._running_claude_pids", lambda: {"1111"})
    assert sessions.claude_session_state() == {}


def test_status_for_busy_when_claude_says_busy_even_after_text(tmp_path):
    info = {"last_role": "assistant", "last_assistant_kind": "text"}
    assert (
        sessions._status_for(age=600, is_live=True, info=info, claude_status="busy", now=1000)
        == "busy"
    )


def test_status_for_idle_when_claude_says_idle_and_kind_is_tool(tmp_path):
    info = {"last_role": "assistant", "last_assistant_kind": "tool"}
    assert (
        sessions._status_for(age=5, is_live=True, info=info, claude_status="idle", now=1000)
        == "idle"
    )


def test_status_for_ready_when_recent_idle_transition(tmp_path):
    info = {"last_role": "assistant", "last_assistant_kind": "text"}
    # updated_at 60s ago: well within freshness window
    assert (
        sessions._status_for(
            age=60, is_live=True, info=info, claude_status="idle", updated_at=940, now=1000
        )
        == "ready"
    )


def test_status_for_idle_when_old_idle_transition(tmp_path):
    info = {"last_role": "assistant", "last_assistant_kind": "text"}
    # updated_at 2 hours ago: long past freshness window — no longer "needs you"
    assert (
        sessions._status_for(
            age=7200, is_live=True, info=info, claude_status="idle", updated_at=0, now=7200
        )
        == "ready"
    ), "missing updated_at falls back to ready (preserves old behavior)"
    assert (
        sessions._status_for(
            age=7200, is_live=True, info=info, claude_status="idle", updated_at=1, now=7200
        )
        == "idle"
    )


def test_status_for_ready_when_live_and_text_last(tmp_path):
    info = {
        "last_role": "assistant",
        "last_assistant_kind": "text",
    }
    assert sessions._status_for(age=10, is_live=True, info=info) == "ready"
    # Even an older ready session stays ready.
    assert sessions._status_for(age=600, is_live=True, info=info) == "ready"


def test_status_for_busy_when_fresh_no_text(tmp_path):
    info = {"last_role": "assistant", "last_assistant_kind": "tool"}
    assert sessions._status_for(age=5, is_live=True, info=info) == "busy"


def test_status_for_idle_when_live_old_and_tool(tmp_path):
    info = {"last_role": "assistant", "last_assistant_kind": "tool"}
    assert sessions._status_for(age=600, is_live=True, info=info) == "idle"


def test_status_for_dead_when_not_live_and_old(tmp_path):
    info = {"last_role": "user", "last_assistant_kind": ""}
    assert sessions._status_for(age=600, is_live=False, info=info) == "dead"


def test_status_for_busy_when_not_live_but_fresh(tmp_path):
    info = {"last_role": "user", "last_assistant_kind": ""}
    assert sessions._status_for(age=5, is_live=False, info=info) == "busy"


def test_warnings_api_error():
    info = {"api_errors": 2, "recent_tools": [], "turns": 0, "cost": 0}
    assert "api_err" in sessions._warnings_for(info)


def test_warnings_loop_when_same_tool_4x():
    info = {
        "api_errors": 0,
        "recent_tools": ["Read", "Read", "Read", "Read"],
        "turns": 4,
        "cost": 0,
    }
    assert "loop" in sessions._warnings_for(info)


def test_warnings_no_loop_when_mixed():
    info = {
        "api_errors": 0,
        "recent_tools": ["Read", "Edit", "Read", "Read"],
        "turns": 4,
        "cost": 0,
    }
    assert "loop" not in sessions._warnings_for(info)


def test_warnings_burn_when_high_cost_per_turn():
    info = {"api_errors": 0, "recent_tools": [], "turns": 10, "cost": 15.0}
    assert "burn" in sessions._warnings_for(info)


def test_warnings_no_burn_when_few_turns():
    info = {"api_errors": 0, "recent_tools": [], "turns": 3, "cost": 15.0}
    assert "burn" not in sessions._warnings_for(info)


def test_warnings_empty_for_clean_session():
    info = {"api_errors": 0, "recent_tools": ["Read", "Edit"], "turns": 5, "cost": 0.10}
    assert sessions._warnings_for(info) == []


def test_scan_status_ready_when_live_and_text_last(monkeypatch, tmp_path):
    proj = tmp_path / "claude-projects" / "-tmp-x"
    proj.mkdir(parents=True)
    sid = "abcdef01-2345-6789-abcd-ef0123456789"
    p = proj / f"{sid}.jsonl"
    _write_jsonl(
        p,
        [
            {"type": "user", "cwd": "/tmp/x", "message": {"role": "user", "content": "go"}},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "done"}],
                },
            },
        ],
    )
    monkeypatch.setattr("claudeboard.sessions.ROOT", str(tmp_path / "claude-projects"))
    monkeypatch.setattr("claudeboard.sessions._meta_cache", {})
    monkeypatch.setattr("claudeboard.sessions._live_session_paths", lambda *a: {str(p)})
    monkeypatch.setattr("claudeboard.sessions.claude_cwd_counts", lambda: {"/tmp/x": 1})
    # Make the file old so age-based busy doesn't trigger.
    import os

    old = 1_000_000.0
    os.utime(p, (old, old))
    monkeypatch.setattr("claudeboard.sessions.time.time", lambda: old + 600)
    rows = sessions.scan()
    assert len(rows) == 1
    assert rows[0]["status"] == "ready"


def test_scan_sorts_ready_above_busy_and_idle(monkeypatch, tmp_path):
    root = tmp_path / "claude-projects" / "-tmp-x"
    root.mkdir(parents=True)
    # Build three sessions with different states.
    ids = {
        "ready": "11111111-1111-1111-1111-111111111111",
        "busy": "22222222-2222-2222-2222-222222222222",
        "idle": "33333333-3333-3333-3333-333333333333",
    }
    for kind, sid in ids.items():
        p = root / f"{sid}.jsonl"
        if kind == "ready":
            _write_jsonl(
                p,
                [
                    {"message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}},
                ],
            )
        elif kind == "idle":
            _write_jsonl(
                p,
                [
                    {
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
                        }
                    },
                ],
            )
        else:
            _write_jsonl(
                p,
                [
                    {"message": {"role": "user", "content": "x"}},
                ],
            )
    monkeypatch.setattr("claudeboard.sessions.ROOT", str(tmp_path / "claude-projects"))
    monkeypatch.setattr("claudeboard.sessions._meta_cache", {})
    import glob
    import os

    paths = set(glob.glob(os.path.join(str(tmp_path / "claude-projects"), "*", "*.jsonl")))
    monkeypatch.setattr("claudeboard.sessions._live_session_paths", lambda *a: paths)
    monkeypatch.setattr("claudeboard.sessions.claude_cwd_counts", lambda: {"/tmp/x": 3})
    # busy session: fresh file. ready & idle: old.
    now = 1_000_000.0
    busy_path = os.path.join(str(root), ids["busy"] + ".jsonl")
    ready_path = os.path.join(str(root), ids["ready"] + ".jsonl")
    idle_path = os.path.join(str(root), ids["idle"] + ".jsonl")
    os.utime(ready_path, (now - 600, now - 600))
    os.utime(idle_path, (now - 600, now - 600))
    os.utime(busy_path, (now - 5, now - 5))
    monkeypatch.setattr("claudeboard.sessions.time.time", lambda: now)
    rows = sessions.scan()
    statuses = [r["status"] for r in rows]
    assert statuses[0] == "busy", f"busy should be first, got {statuses}"
    assert statuses.index("ready") < statuses.index("idle"), statuses
    assert statuses.index("busy") < statuses.index("ready"), statuses
