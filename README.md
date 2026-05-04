# claudeboard

Web dashboard for [Claude Code](https://claude.com/claude-code) sessions. Reads
the jsonl files under `~/.claude/projects/` and serves a live single-page UI.

![status](https://github.com/davebiagioni/claudeboard/actions/workflows/ci.yml/badge.svg)

## What it shows

- **Sidebar** — every session, sorted by recency, color-coded
  busy / idle / dead. Slug (matches the Claude Code terminal-tab name) on top,
  aiTitle underneath, last user prompt below.
- **Detail tabs** — STATS (token/message counts), WORK (cost, active vs idle
  time, files touched, tools used, session-start git diff), GIT (commits in
  the cwd since session start), TRANSCRIPT (text-only filtered turns).
- **Summary** — optional Sonnet-generated 3-5 sentence summary, cached on
  disk by message count. Requires `ANTHROPIC_API_KEY`.

## Install & run

```bash
uv sync
uv run claudeboard
```

Then open http://localhost:8765.

For Sonnet summaries:

```bash
ANTHROPIC_API_KEY=sk-ant-... uv run claudeboard
```

## Develop

```bash
uv sync --extra dev
uv run pre-commit install
uv run pytest
uv run ruff check
uv run ruff format
```

## Layout

```
src/claudeboard/
  __init__.py
  __main__.py     # python -m claudeboard
  cli.py          # entry point
  server.py       # HTTP routing
  sessions.py     # jsonl parsing, scan, mtime cache
  detail.py       # per-session aggregates (cost, time, files)
  git.py          # git_activity, session_diff
  summary.py      # Sonnet API call + on-disk cache
  page.py         # the static HTML/CSS/JS blob
tests/
  ...
```

Stdlib only at runtime. `pytest`, `ruff`, and `pre-commit` are dev-only.
