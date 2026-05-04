from __future__ import annotations

import os
import re
import subprocess


# Working-tree diff vs the commit that was HEAD when `since` was recorded.
# Returns None if no pre-session commit exists or git fails.
def session_diff(cwd: str, since: str) -> dict | None:
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

    def n(pat: str) -> int:
        m = re.search(pat, out)
        return int(m.group(1)) if m else 0

    return {
        "start": start_sha[:7],
        "files": n(r"(\d+) files? changed"),
        "add": n(r"(\d+) insertions?"),
        "rm": n(r"(\d+) deletions?"),
    }


# Commits in cwd since `since`, with per-commit and total LOC deltas.
# Returns None if cwd is missing, isn't a git repo, or git fails.
def git_activity(cwd: str, since: str) -> dict | None:
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
