"""Git activity helpers: commits since session start, total diff vs pre-session HEAD."""

from __future__ import annotations

import os
import re
import subprocess


def session_diff(cwd: str, since: str) -> dict | None:
    """Total diff (working tree) vs the commit that was HEAD when the session started.

    Returns None if there's no pre-session commit (e.g., session predates the repo's history).
    """
    if not cwd or not os.path.isdir(cwd) or not since:
        return None
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "rev-list", "-n", "1", "--before", since, "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    start_sha = r.stdout.strip()
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "diff", "--shortstat", start_sha],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    files = ins = dels = 0
    m = re.search(r"(\d+) files? changed", out)
    if m:
        files = int(m.group(1))
    m = re.search(r"(\d+) insertions?", out)
    if m:
        ins = int(m.group(1))
    m = re.search(r"(\d+) deletions?", out)
    if m:
        dels = int(m.group(1))
    return {"start": start_sha[:7], "files": files, "add": ins, "rm": dels}


def git_activity(cwd: str, since: str) -> dict | None:
    """Commits in cwd since timestamp, with per-commit and total LOC deltas.

    Returns None if cwd is missing, isn't a git repo, or git fails for any reason.
    """
    if not cwd or not os.path.isdir(cwd) or not since:
        return None
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "log", "--since", since, "--pretty=format:%h %s", "--numstat"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    commits: list[dict] = []
    cur: dict | None = None
    add = rm = 0
    for line in r.stdout.split("\n"):
        line = line.rstrip()
        if not line:
            continue
        if "\t" in line:
            parts = line.split("\t", 2)
            if len(parts) >= 2 and cur is not None:
                try:
                    a = int(parts[0])
                except ValueError:
                    a = 0
                try:
                    d = int(parts[1])
                except ValueError:
                    d = 0
                cur["add"] += a
                cur["rm"] += d
                add += a
                rm += d
        else:
            if cur is not None:
                commits.append(cur)
            sha, _, msg = line.partition(" ")
            cur = {"sha": sha, "msg": msg, "add": 0, "rm": 0}
    if cur is not None:
        commits.append(cur)
    return {"commits": commits[:10], "add": add, "rm": rm, "n": len(commits)}
