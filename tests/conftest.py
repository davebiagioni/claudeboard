"""Shared fixtures: a synthetic jsonl file representing one Claude Code session."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SAMPLE_RECORDS = [
    # Header records — non-message types
    {"type": "ai-title", "aiTitle": "Test session", "sessionId": "test"},
    # First user prompt with cwd + branch
    {
        "type": "user",
        "cwd": "/tmp/claudeboard-test",
        "gitBranch": "main",
        "timestamp": "2026-05-04T01:00:00.000Z",
        "message": {"role": "user", "content": "do the thing"},
    },
    # Assistant tool_use with usage
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
    # Another tool_use to the same file (Read)
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
    # Final assistant text
    {
        "type": "assistant",
        "timestamp": "2026-05-04T01:02:00.000Z",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
    },
    # User reply that triggers a slug
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
    """Write SAMPLE_RECORDS to a real .jsonl file in tmp_path and return the path."""
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
    """A file with a mix of valid records and malformed lines."""
    p = tmp_path / "malformed.jsonl"
    with p.open("w") as f:
        f.write("not json at all\n")
        f.write(json.dumps(SAMPLE_RECORDS[0]) + "\n")
        f.write("{broken\n")
        f.write(json.dumps(SAMPLE_RECORDS[1]) + "\n")
    return p


@pytest.fixture
def fake_root(tmp_path: Path, monkeypatch) -> Path:
    """A fake ~/.claude/projects/ root with one project containing one session."""
    project = tmp_path / "claude-projects" / "-tmp-claudeboard-test"
    project.mkdir(parents=True)
    sid = "12345678-1234-1234-1234-123456789abc"
    p = project / f"{sid}.jsonl"
    with p.open("w") as f:
        for r in SAMPLE_RECORDS:
            f.write(json.dumps(r) + "\n")
    root = tmp_path / "claude-projects"
    monkeypatch.setattr("claudeboard.sessions.ROOT", str(root))
    # The cache survives across tests; clear it so monkeypatched ROOT takes effect.
    monkeypatch.setattr("claudeboard.sessions._meta_cache", {})
    return root
