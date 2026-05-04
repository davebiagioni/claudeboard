from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claudeboard import git as cb_git


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\ntwo\nthree\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=tmp_path, check=True)
    return tmp_path


def test_git_activity_not_a_repo(tmp_path):
    assert cb_git.git_activity(str(tmp_path), "2026-01-01T00:00:00Z") is None


def test_git_activity_missing_cwd():
    assert cb_git.git_activity("", "2026-01-01T00:00:00Z") is None
    assert cb_git.git_activity("/does/not/exist", "2026-01-01T00:00:00Z") is None


def test_git_activity_no_since():
    assert cb_git.git_activity("/tmp", "") is None


def test_git_activity_returns_commits(tmp_repo):
    result = cb_git.git_activity(str(tmp_repo), "2000-01-01T00:00:00Z")
    assert "commits" in result
    assert result["n"] == 2
    assert result["add"] >= 3  # at least 3 lines added across the two commits
    assert result["rm"] == 0
    assert all("sha" in c and "msg" in c for c in result["commits"])


def test_session_diff_no_pre_session_commit(tmp_repo):
    # Session timestamp predates all commits → no pre-session commit found
    assert cb_git.session_diff(str(tmp_repo), "1990-01-01T00:00:00Z") is None


def test_session_diff_with_uncommitted_changes(tmp_repo):
    # Modify the file post-second-commit so working tree differs
    (tmp_repo / "a.txt").write_text("one\ntwo\nthree\nfour\n")
    # session_diff finds the commit that was HEAD at session start (2099 = future,
    # so HEAD = the second commit) and diffs working tree against it: +1 line.
    result = cb_git.session_diff(str(tmp_repo), "2099-01-01T00:00:00Z")
    assert result is not None
    assert result["files"] == 1
    assert result["add"] == 1
    assert result["rm"] == 0
