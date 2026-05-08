from __future__ import annotations

import json
import os
import re
import subprocess

from claudeboard.sessions import ROOT, SESSIONS_STATE_DIR

TTY_RE = re.compile(r"^/dev/[a-zA-Z0-9/]+$")


def _claude_pid_tty() -> dict[str, str]:
    try:
        r = subprocess.run(
            ["ps", "-axo", "pid=,tty=,comm="],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return {}
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        if os.path.basename(parts[2].strip()) != "claude":
            continue
        pid = parts[0].strip()
        tty = parts[1].strip()
        if not tty or tty == "??":
            continue
        out[pid] = tty if tty.startswith("/") else "/dev/" + tty
    return out


def _pid_cwds(pids: list[str]) -> dict[str, str]:
    if not pids:
        return {}
    try:
        r = subprocess.run(
            ["lsof", "-a", "-p", ",".join(pids), "-d", "cwd", "-Fpn"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        return {}
    out: dict[str, str] = {}
    cur_pid: str | None = None
    for line in r.stdout.splitlines():
        if line.startswith("p"):
            cur_pid = line[1:]
        elif line.startswith("n/") and cur_pid:
            out[cur_pid] = line[1:]
            cur_pid = None
    return out


def _session_to_tty_from_state(pid_to_tty: dict[str, str]) -> dict[str, str]:
    try:
        entries = os.listdir(SESSIONS_STATE_DIR)
    except OSError:
        return {}
    out: dict[str, str] = {}
    for name in entries:
        if not name.endswith(".json"):
            continue
        pid = name[:-5]
        tty = pid_to_tty.get(pid)
        if not tty:
            continue
        try:
            with open(os.path.join(SESSIONS_STATE_DIR, name)) as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        sid = d.get("sessionId")
        if sid:
            out[sid] = tty
    return out


def _session_to_tty_legacy(pid_to_tty: dict[str, str]) -> dict[str, str]:
    pid_to_cwd = _pid_cwds(list(pid_to_tty.keys()))
    if not pid_to_cwd:
        return {}
    by_cwd: dict[str, list[str]] = {}
    for pid in sorted(pid_to_cwd.keys(), key=lambda p: int(p)):
        by_cwd.setdefault(pid_to_cwd[pid], []).append(pid)
    out: dict[str, str] = {}
    for cwd, pids in by_cwd.items():
        proj_dir = os.path.join(ROOT, cwd.replace("/", "-"))
        try:
            entries = [e for e in os.listdir(proj_dir) if e.endswith(".jsonl")]
        except OSError:
            continue
        scored: list[tuple[float, str]] = []
        for e in entries:
            try:
                scored.append((os.stat(os.path.join(proj_dir, e)).st_mtime, e))
            except OSError:
                continue
        if not scored:
            continue
        scored.sort()
        recent = scored[-len(pids) :]
        for pid, (_, fname) in zip(pids, recent, strict=False):
            out[fname[:-6]] = pid_to_tty[pid]
    return out


def session_to_tty() -> dict[str, str]:
    pid_to_tty = _claude_pid_tty()
    if not pid_to_tty:
        return {}
    out = _session_to_tty_from_state(pid_to_tty)
    if out:
        return out
    return _session_to_tty_legacy(pid_to_tty)


_FOCUS_APPLESCRIPT = """
on run
    set targetTty to "__TTY__"
    tell application "System Events"
        set itermRunning to (exists (processes where name is "iTerm2"))
        set termRunning to (exists (processes where name is "Terminal"))
    end tell
    if itermRunning then
        try
            tell application id "com.googlecode.iterm2"
                repeat with w in windows
                    repeat with t in tabs of w
                        repeat with s in sessions of t
                            if (tty of s) is targetTty then
                                select s
                                activate
                                return "ok"
                            end if
                        end repeat
                    end repeat
                end repeat
            end tell
        end try
    end if
    if termRunning then
        try
            tell application "Terminal"
                repeat with w in windows
                    repeat with t in tabs of w
                        if (tty of t) is targetTty then
                            set selected of t to true
                            set frontmost of w to true
                            activate
                            return "ok"
                        end if
                    end repeat
                end repeat
            end tell
        end try
    end if
    return "notfound"
end run
"""


def focus_session(sid: str) -> tuple[bool, str]:
    tty = session_to_tty().get(sid)
    if not tty:
        return False, "no live terminal tab found"
    if not TTY_RE.match(tty):
        return False, "invalid tty"
    script = _FOCUS_APPLESCRIPT.replace("__TTY__", tty)
    try:
        r = subprocess.run(
            ["osascript", "-"],
            input=script,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"osascript failed: {e}"
    if (r.stdout or "").strip() == "ok":
        return True, "focused"
    err = (r.stderr or "").strip()
    return False, err or f"no tab matched {tty} in iTerm2/Terminal"
