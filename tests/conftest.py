from __future__ import annotations

import json
from pathlib import Path

import pytest

SAMPLE_RECORDS = [
    {"type": "ai-title", "aiTitle": "Test session", "sessionId": "test"},
    {
        "type": "user",
        "cwd": "/tmp/claudeboard-test",
        "gitBranch": "main",
        "timestamp": "2026-05-04T01:00:00.000Z",
        "message": {"role": "user", "content": "do the thing"},
    },
    {
        "type": "assistant",
        "timestamp": "2026-05-04T01:01:00.000Z",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Edit",
                    "input": {"file_path": "/tmp/claudeboard-test/foo.py"},
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 500,
            },
        },
    },
    {
        "type": "assistant",
        "timestamp": "2026-05-04T01:01:30.000Z",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Read",
                    "input": {"file_path": "/tmp/claudeboard-test/foo.py"},
                }
            ],
        },
    },
    {
        "type": "assistant",
        "timestamp": "2026-05-04T01:02:00.000Z",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
    },
    {
        "slug": "test-slug-name",
        "type": "system",
        "subtype": "informational",
        "timestamp": "2026-05-04T01:02:30.000Z",
    },
    {
        "type": "user",
        "timestamp": "2026-05-04T01:03:00.000Z",
        "message": {"role": "user", "content": "another prompt"},
    },
]


@pytest.fixture
def sample_jsonl(tmp_path: Path) -> Path:
    p = tmp_path / "sample-session-id.jsonl"
    with p.open("w") as f:
        for r in SAMPLE_RECORDS:
            f.write(json.dumps(r) + "\n")
    return p


@pytest.fixture
def empty_jsonl(tmp_path: Path) -> Path:
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    return p


@pytest.fixture
def malformed_jsonl(tmp_path: Path) -> Path:
    p = tmp_path / "malformed.jsonl"
    with p.open("w") as f:
        f.write("not json at all\n")
        f.write(json.dumps(SAMPLE_RECORDS[0]) + "\n")
        f.write("{broken\n")
        f.write(json.dumps(SAMPLE_RECORDS[1]) + "\n")
    return p


@pytest.fixture
def fake_root(tmp_path: Path, monkeypatch) -> Path:
    project = tmp_path / "claude-projects" / "-tmp-claudeboard-test"
    project.mkdir(parents=True)
    sid = "12345678-1234-1234-1234-123456789abc"
    p = project / f"{sid}.jsonl"
    with p.open("w") as f:
        for r in SAMPLE_RECORDS:
            f.write(json.dumps(r) + "\n")
    root = tmp_path / "claude-projects"
    monkeypatch.setattr("claudeboard.sessions.ROOT", str(root))
    monkeypatch.setattr("claudeboard.sessions._meta_cache", {})
    return root
