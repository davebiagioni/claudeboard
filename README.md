# claudeboard

A live web dashboard for [Claude Code](https://claude.com/claude-code) sessions.
Watches `~/.claude/projects/` and tells you what every terminal tab is doing,
what each session has cost, and how your month-to-date burn compares to the
$200 Claude Max plan.

![ci](https://github.com/davebiagioni/claudeboard/actions/workflows/ci.yml/badge.svg)

![claudeboard dashboard](docs/screenshot.png)

> **The pitch in one number:** if you're a heavy Opus user, your `$200/mo` Max
> plan is probably costing you the equivalent of more than `$1,000/mo` at API
> list prices. claudeboard tells you exactly how much, per session and
> month-to-date, computed at real per-model rates.

## Why

Claude Code in a single terminal tab is fine. Claude Code across **seven** tabs
in **four** worktrees, with no way to know which tabs are still running, what
each is working on, or what they're costing — that's where this exists.

- **What is each tab doing right now?** Sidebar shows every session with its
  slug (the same human-readable name Claude Code gives the terminal tab),
  the latest user prompt, and a live `busy` / `idle` / `dead` pill driven by
  whether a `claude` process is actually pointing at that working directory
  (`ps` + `lsof`, falls back to mtime).
- **What did this session cost?** Per-row dollar amount, computed at real
  Anthropic list prices for the actual model used (Opus / Sonnet / Haiku 4.x).
  Hover for a 4-decimal exact value.
- **Am I getting value from my Max plan?** Header shows month-to-date cost
  vs the `$200` plan, color-coded (gray under 75%, amber 75–100%, red over).
- **Where did the money go?** Per-session stats tab visualizes cost by
  token type (in / out / cache_r / cache_w) and, when multiple models were
  used, by model. Cache reads dominate token *volume*; output and cache
  writes dominate the *bill*.
- **What did this session actually do?** WORK tab shows the
  session-start-to-HEAD git diff (`+N / -M / files-changed`) and a list of
  every file edited / written / read with op counts. GIT tab shows commits
  in the cwd since the session started. TRANSCRIPT shows the filtered
  text-only turns.
- **What's it about?** Optional one-click Sonnet-generated summary,
  cached to disk by message count so it only re-runs when there are new
  turns. Requires `ANTHROPIC_API_KEY`.

## Install & run

```bash
uv sync
uv run claudeboard
```

Open <http://localhost:8765>. Sidebar lists everything; click a session to
drill into its detail.

For on-demand Sonnet summaries:

```bash
ANTHROPIC_API_KEY=sk-ant-... uv run claudeboard
```

## What's where

```
src/claudeboard/
  __init__.py
  __main__.py            # python -m claudeboard
  cli.py                 # console entry point
  server.py              # HTTP routes: /, /data.json, /session/<id>, /summary/<id>
  sessions.py            # jsonl parsing, scan, mtime cache, PRICING table
  detail.py              # per-session aggregates: cost, time, files
  git.py                 # git_activity, session_diff
  summary.py             # Sonnet API + disk cache
  page.py                # one-liner that loads...
  static/
    index.html           # ...the actual HTML/CSS/JS
tests/
  conftest.py            # synthetic jsonl fixtures
  test_sessions.py
  test_detail.py
  test_git.py            # uses a real tmp git repo
```

Runtime is stdlib only — no third-party Python deps. `pytest`, `ruff`, and
`pre-commit` are dev tools.

## Pricing notes

`sessions.py` ships a `PRICING` table with `(input, output, cache_read,
cache_write_5m)` rates per million tokens for the model families this
project sees. Update when Anthropic changes prices or new families ship.
Unknown models fall back to Sonnet rates.

The four token types in one paragraph: every Claude Code turn re-sends the
whole conversation history + system prompt + tool definitions, so volume is
dominated by **cache reads** at `$1.50` / MTok (Opus). The bill is
dominated by **output** at `$75` / MTok (50× the cache read rate, even
though output is < 1% of token volume) and **cache writes** at `$18.75` /
MTok (the 25%-premium-on-input cost of *creating* the cache so reads can
be cheap).

## Develop

```bash
uv sync --extra dev
uv run pre-commit install
uv run pytest
uv run ruff check
uv run ruff format
```

CI runs ruff + pytest on Python 3.10 / 3.11 / 3.12 via uv on every push and PR.
