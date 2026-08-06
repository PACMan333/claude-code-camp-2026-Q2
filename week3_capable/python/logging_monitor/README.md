# Logging Monitor

A small Flask app giving three views over the durable logs every boukensha
instance (Python and Ruby tracks alike) and `mud_manager` already write
under `BOUKENSHA_DIR`:

1. **Sessions** — a live-tailing transcript for each `.boukensha/sessions/
   *.jsonl` file: every phase rendered (user/assistant messages, reasoning,
   plan, tool calls with their result, compaction, turn boundaries, and
   now durably-logged errors), each row showing the wall-clock gap since
   the previous log event, plus a per-turn **waterfall** showing where the
   turn's time actually went (API call latency vs. each tool dispatch vs.
   compaction). Open a session's page while it's still running and new
   entries — and new waterfall spans — appear without a reload.
2. **Errors** (`/errors`) — every meaningful `rescue`/`except` in both
   boukensha tracks and `mud_manager` now writes a durable, structured
   entry (what failed, where it was rescued, which session/operation/task
   was active, the full exception class + message + backtrace) to
   `<BOUKENSHA_DIR>/errors.jsonl`. This page reads that file, newest first,
   independent of which session (if any) the error happened in.
3. **Raw MUD command log** (`/mud`) — `mud_manager` now logs every command
   it actually sent to the live MUD and the raw response it read back,
   with timing, to `<MUD_MANAGER_LOG_DIR>/mud_manager.jsonl`. This page
   browses that log.

Why this exists: session logs previously had no live-tailing view, no
sub-second timestamps (so no meaningful "how long did that take"), no raw
MUD command visibility at all, and — most importantly — a failed tool call
or MCP server startup would surface only as a one-line string on stdout,
never durably, with no exception class and no backtrace. A bad-arity
`ArgumentError` inside `mud_manager` could crash the whole MCP subprocess
with nothing but a bare stderr dump to go on. All four gaps are closed by
this app plus the small set of upstream changes described below.

## Running it

```bash
# from the repo root, into the shared .venv every week3_capable/python/*
# package already uses:
.venv/bin/pip install -r week3_capable/python/logging_monitor/requirements.txt

.venv/bin/python3 week3_capable/python/logging_monitor/bin/logging_monitor
# -> http://localhost:4568
```

No env var needed to see this repo's own logs: with `BOUKENSHA_DIR` unset,
it defaults to `<repo root>/.boukensha` (found relative to this script's
own location) if that directory exists, before falling back to
`~/.boukensha` -- so it finds `sessions/`, `errors.jsonl`, and
`mud_manager.jsonl` right where every other tool in this repo already
writes them, not an empty `~/.boukensha`. Set `BOUKENSHA_DIR` explicitly
to point at a different install.

Env vars:

| Variable | Default | |
|---|---|---|
| `BOUKENSHA_DIR` | `<repo root>/.boukensha` if it exists, else `~/.boukensha` | sessions/, errors.jsonl, mud_manager.jsonl are all read from here |
| `LOGGING_MONITOR_PORT` | `4568` | one port over from `log_viz`'s `4567`, so both can run side by side |
| `LOGGING_MONITOR_BIND` | `localhost` | |

`log_viz` (the original Ruby/Sinatra session viewer) is untouched and
still works — this app is additive, not a replacement.

## What changed upstream to make this possible

- **Sub-second timestamps.** `Logger._iso_now`/`Logger#write_log`'s `at`
  field is now microsecond-precision in both the Python and Ruby boukensha
  tracks (`isoformat(timespec="microseconds")` / `Time.now.iso8601(6)`).
  Every existing consumer (`log_viz`, `session_to_traces.py`) already
  parses ISO-8601 with fractional seconds transparently — this is additive,
  not breaking.
- **`Logger.error()` / `Logger#error`** (new): writes one structured entry
  both inline in the current session's JSONL and to the durable, cross-
  session `<BOUKENSHA_DIR>/errors.jsonl`, via a small standalone
  `error_log.py`/`error_log.rb` (deliberately independent of `Logger`, so
  it can be called even before a session/Logger exists — e.g. an MCP
  server startup failure). Every meaningful catch site in both tracks
  (`__init__.py`/`boukensha.rb`'s MCP registration, `agent.py`/`agent.rb`'s
  wind-down and tool-dispatch handling, `repl.py`/`repl.rb`'s turn loop,
  `tui.py`/`tui.rb`'s worker thread) now calls it. `client.py`'s low-level
  retries and `mcp/client.py`'s best-effort pipe closes are deliberately
  left alone — the outer catches above already log the resulting error
  with full session context.
- **`mud_manager` gains its own command log and stops crashing on bad
  arity.** `lib/mud_manager/jsonl_log.rb` is a small, dependency-free JSONL
  writer; `bin/mud-manager`'s `call_tool` now logs every command/response/
  timing on success and every exception (with backtrace) on its existing
  rescue paths, and a new blanket rescue around `run`'s dispatch loop
  means an exception that used to kill the whole MCP subprocess now just
  fails one request. See `week0_explore/mud_manager/README.md`.

## Layout

```
logging_monitor/
├── server.py     # Flask app + all 5 routes, including the SSE tail endpoint
├── sessions.py   # JSONL -> transcript entries, with duration_ms per entry
├── spans.py      # transcript events -> turn/iteration/api_call/tool_call spans + inline SVG waterfall
├── errors.py     # errors.jsonl -> Errors page rows
├── mud_log.py    # mud_manager.jsonl -> raw-command page rows
├── ansi.py       # ANSI SGR -> HTML (ported from log_viz/lib/log_viz/ansi.rb)
└── templates/    # Jinja2 -- autoescaping matters here (backtraces, raw MUD output)
```

## The waterfall

The JSONL log is a flat sequence of point-in-time events, not explicit
span boundaries. `spans.py` reconstructs `turn -> iteration ->
api_call/tool_call` spans from that sequence — the same nesting
`week2_observability/observability/scripts/session_to_traces.py` already
established for shipping to Tempo via OTLP, re-targeted here at inline SVG
instead of an OTLP payload, plus an explicit `api_call` span (a `prompt`
event paired with the `response` event that follows it) isolating LLM
round-trip latency from tool execution time. A failed tool call renders in
red and carries the linked `error` event's class/message/backtrace, if
`Logger.error` recorded one for that dispatch. Requires the microsecond-
precision timestamps above — with only second precision every span would
round to zero or a whole second.

## Tests

```bash
.venv/bin/python3 -m unittest discover -s week3_capable/python/logging_monitor/tests
.venv/bin/python3 -m unittest discover -s week3_capable/python/map_zone/tests   # includes test_error_log.py
cd week0_explore/mud_manager && ruby -Ilib -Itest test/test_jsonl_log.rb
```
