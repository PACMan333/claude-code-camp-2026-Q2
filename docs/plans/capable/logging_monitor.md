# Week 3 (Capable) Plan — Logging Monitor

## Problem

Observability today is scattered and, for errors specifically, actively lossy:

- **Session logs exist but aren't live.** `week1_baseline/log_viz` (a Ruby
  Sinatra app — the plan brief says `log_vis`; the real directory is
  `log_viz`, corrected here) reads `.boukensha/sessions/*.jsonl` and
  renders a transcript, but every page load re-parses the whole file from
  scratch. There's no polling/SSE/websocket anywhere in it — confirmed by
  grepping its views and JS for `refresh|poll|setInterval|EventSource`:
  zero hits. "Sit on the page and watch it update" doesn't exist yet.
- **Timestamps exist but durations don't.** Every JSONL line already has
  an `at` field, but it's second-precision
  (`logger.py`'s `_iso_now`), so back-to-back tool calls that take
  200ms both round to the same second — not enough resolution to show a
  meaningful "duration since the previous event."
- **`mud_manager` logs nothing.** `bin/mud-manager`'s `call_tool`
  (lines 385-410) does `session.drain` → `session.send_command(command)` →
  `text = session.read_until_prompt` with zero logging anywhere in that
  path or in `Session#send_command`/`#read_until_prompt`
  (`lib/mud_manager/session.rb`). The raw commands actually sent to the
  live MUD are invisible today.
- **Errors are real, but their detail is thrown away before it reaches
  anywhere durable.** The motivating example —
  `ArgumentError: wrong number of arguments (given 1, expected 0)` — is a
  classic Ruby arity-mismatch message. Tracing every `rescue` in both
  boukensha tracks and `mud_manager` (full inventory below) turned up
  exactly **one** place where any exception detail reaches the durable
  JSONL log at all: `Agent._handle_tool_calls` catches the dispatch
  exception and logs `tool_result(..., ok=False, error=str(e))` — message
  only, no exception class, no backtrace. Every other catch site either
  prints `class: message` (or just `message`) to stdout/stderr and
  discards it, or silently swallows the exception outright. **Correction
  to the brief:** it states "Session JSONL currently records `error_type`
  for some failed operations" — that field doesn't exist anywhere in
  `logger.py`/`logger.rb`, and a grep of all 81 real session files in this
  repo's own `.boukensha/sessions/` found zero `error_type` occurrences
  and zero `"ok": false` entries. No failed tool call has ever actually
  been durably logged with any detail in this repo's history.
- The single most likely source of the motivating `ArgumentError` is
  `mud_manager` itself: `call_tool`'s `rescue ArgumentError => e` (line
  406-407) returns `"argument_error: #{e.message}"` with **no class
  prefix, no backtrace** — but if a `TOOLS[...][:call]` lambda has a stale
  arity mismatch against `Primitives`, and the failure happens somewhere
  `call_tool`'s own rescue doesn't cover (there's no blanket rescue around
  `handle(msg)` at all in `run`), the exception escapes uncaught, Ruby's
  default top-level handler prints exactly `ArgumentError: wrong number of
  arguments (given 1, expected 0)` with a backtrace to stderr, and the
  whole MCP subprocess dies. This plan both makes that failure mode
  visible *and* stops it from being fatal.

## Goal

One Python app, `week3_capable/python/logging_monitor`, giving three
views over a widened set of durable logs, all rooted under the same
`BOUKENSHA_DIR` tree every other durable boukensha file already uses
(sessions, settings, prompts):

1. **Sessions** — the transcript view `log_viz` provides today, rebuilt
   in Python, plus: a duration-since-previous-event column (needs
   sub-second timestamps — see Design 1), and a live-tailing view via
   Server-Sent Events so a session in progress can be watched update in
   real time.
2. **A raw MUD command log** — `mud_manager` gains its own durable JSONL
   log of every command sent and response received, with timing, and a
   page to browse it.
3. **A top-level Errors page** — backed by a new, durable,
   `BOUKENSHA_DIR`-scoped `errors.jsonl` (see Design 4's note on
   "profile-scoped" — no "profile" concept exists anywhere in `Config`
   today; this plan treats "profile-scoped" as "scoped to one
   `BOUKENSHA_DIR` install," the same scope `sessions/`/`settings.yaml`
   already use) that every meaningful `rescue`/`except` in both boukensha
   tracks and `mud_manager` writes to, capturing: what failed, where it
   was rescued, which session/operation/task was active, when, the full
   exception class + message, and the complete backtrace.

## Where the new code lives

```
week3_capable/python/logging_monitor/     # new -- the unified app
├── README.md
├── requirements.txt                       # flask
├── bin/logging_monitor                    # entry point
├── logging_monitor/
│   ├── __init__.py
│   ├── server.py                          # Flask app + routes
│   ├── sessions.py                        # JSONL -> transcript entries (ports log_viz/lib/log_viz/session.rb)
│   ├── spans.py                           # event sequence -> nested spans, for the waterfall (Design 6)
│   ├── errors.py                          # errors.jsonl -> Errors page rows
│   ├── mud_log.py                         # mud_manager.jsonl -> raw-command page rows
│   ├── ansi.py                            # ANSI SGR -> HTML (ports log_viz/lib/log_viz/ansi.rb)
│   └── templates/                         # Jinja2 (bundled with Flask) -- autoescaping matters here:
│       ├── layout.html                    # backtraces and raw MUD output are untrusted-ish content
│       ├── index.html
│       ├── session.html                   # includes the waterfall (Design 6)
│       ├── errors.html
│       └── mud.html
├── static/style.css                       # adapted from log_viz/public/style.css
└── tests/
    ├── test_sessions.py
    ├── test_spans.py
    └── test_errors.py

week3_capable/python/map_zone/boukensha/   # changed -- Python boukensha
├── error_log.py                           # new
├── logger.py                              # changed: _iso_now precision, Logger.error()
├── __init__.py                            # changed: log MCP startup failures
├── agent.py                               # changed: log_error at existing catch sites
└── repl.py                                # changed: log_error at existing catch sites

week1_baseline/ruby/12_context/lib/boukensha/   # changed -- Ruby boukensha (mirrors Python)
├── error_log.rb                           # new
├── logger.rb                              # changed
├── agent.rb                               # changed
└── repl.rb                                # changed
week1_baseline/ruby/12_context/lib/boukensha.rb # changed

week0_explore/mud_manager/                 # changed
├── bin/mud-manager                        # changed: log every command; rescue-and-log instead of crash
└── lib/mud_manager/jsonl_log.rb           # new -- minimal, dependency-free JSONL writer

.boukensha/settings.yaml                   # changed: mcp_servers.mud.env gains MUD_MANAGER_LOG_DIR
```

Per this track's established convention, `logging_monitor` is a fresh
top-level Python app (not a copy-forward of `boukensha` — it doesn't run
an agent, it only reads logs), so it gets its own `requirements.txt`/
`pyproject.toml`, not a share of `map_zone`'s.

## Design

### 1. Sub-second timestamps (needed before "duration" means anything)

`Logger._iso_now()` (`logger.py`) currently does
`datetime.now().astimezone().isoformat(timespec="seconds")`. Bumped to
`timespec="microseconds"`. Same change in Ruby's `logger.rb`
(`Time.now.iso8601` → `Time.now.iso8601(6)`). ISO-8601 with fractional
seconds is standard; both Python's `datetime.fromisoformat` (already used
by `session_to_traces.py`'s `to_unix_nanos`) and Ruby's `Time.parse`
handle it transparently, so this is additive, not breaking, for every
existing consumer (`log_viz`, `session_to_traces.py`).

`logging_monitor/sessions.py` computes `duration_ms` per entry as
`(this.at - previous.at)` in the same parse pass that builds the
transcript — no change to what gets logged, purely a rendering-time
computation, exactly mirroring how `log_viz/lib/log_viz/session.rb`
already builds its `usage_series` in one streaming pass.

### 2. `boukensha/error_log.py` — durable, cross-session error log

A small module, independent of `Logger` (so it can be called even before
a session/Logger exists — e.g. an MCP server startup failure happens
*before* `run()` constructs its `Logger`, per `__init__.py`'s current
ordering: `_register_mcp_servers` runs, then later `logger = Logger(...)`
inside the `try:` block):

```python
import json
import time
import traceback
from pathlib import Path

ERROR_LOG_NAME = "errors.jsonl"


def log_error(exc, *, where, operation=None, task=None, session_id=None, dir=None):
    """Appends one durable, structured entry for `exc` to
    <dir or current_config().dir>/errors.jsonl. Never raises -- a broken
    error logger must not mask the original failure.
    """
    import boukensha  # local import: avoids a hard circular dependency at module load time

    entry = {
        "at": _iso_now_us(),
        "where": where,
        "operation": operation,
        "task": task,
        "session_id": session_id,
        "error_class": type(exc).__name__,
        "error_message": str(exc),
        "backtrace": traceback.format_exception(type(exc), exc, exc.__traceback__),
    }
    try:
        root = Path(dir or boukensha.current_config().dir)
        root.mkdir(parents=True, exist_ok=True)
        with open(root / ERROR_LOG_NAME, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # logging a failure must never itself raise
```

(`_iso_now_us` is the same helper `logger.py` now uses, imported from
there or duplicated as a two-line function — small enough that either is
fine; duplicating avoids `error_log.py` depending on `Logger` at all.)

`Logger` gains a thin convenience wrapper so call sites that already hold
a `Logger` don't have to pass `session_id` by hand, and so the error is
*also* visible inline in that session's own transcript (not just the
cross-session page):

```python
# boukensha/logger.py
def error(self, exc, *, where, operation=None, task=None):
    from . import error_log
    error_log.log_error(
        exc, where=where, operation=operation, task=task, session_id=self._session_id
    )
    self._write_log(phase="error", where=where, operation=operation, task=task,
                     error_class=type(exc).__name__, error_message=str(exc),
                     backtrace=traceback.format_exception(type(exc), exc, exc.__traceback__))
```

Two writes, same event, two audiences: the per-session JSONL (so
`logging_monitor`'s session transcript can render the error inline,
where it happened, alongside the tool calls around it) and the durable
`errors.jsonl` (so the top-level Errors page shows it without scanning
every session file).

### 3. Which catch sites get upgraded, and which don't

Every `rescue`/`except` found during research, and the call made for each:

| site | change |
|---|---|
| `boukensha/__init__.py:101` (`_register_mcp_servers`, required server) | Before raising `RuntimeError`, call `error_log.log_error(e, where="_register_mcp_servers", operation="mcp_server_startup:{}".format(name))` — no `Logger` exists yet at this point in `run()`, so this goes through the module-level function directly, `session_id=None`. **This is the exact failure class the motivating example represents** — a crashed `mud-manager` subprocess during spawn/handshake. |
| `boukensha/__init__.py:101` (optional server, else branch) | Same `log_error` call, in addition to the existing `print(...)` (kept, for REPL/TTY visibility) — not fatal, but now durably visible too. |
| `boukensha/agent.py:157` (`_wrap_up`, catches `ApiError`) | Currently silently swallowed. Add `self._logger.error(e, where="Agent._wrap_up", operation="api_call")`. |
| `boukensha/agent.py:225` (`_handle_tool_calls`) | Keep the existing `tool_result(..., ok=False, error=str(e))` call (log_viz already renders it). Add `self._logger.error(e, where="Agent._handle_tool_calls", operation="tool_dispatch:{}".format(name))` for the class + full backtrace the existing call never captured. |
| `boukensha/repl.py:178,180` (`LoopError`/`ApiError`) | Currently only `self._output(...)`. Add `self._logger.error(e, where="Repl.<loop>", operation=...)` — `Repl` already holds `logger` (`start_repl` constructs it with `logger=logger`). |
| `boukensha/tui.py:333` (`_run_turn_worker`) | Currently only pushes a TUI-internal `turn_error` event (never reaches the JSONL at all). Add the same `logger.error(...)` call — confirm `Tui` has a `logger` reference via `Repl` at implementation time; if it doesn't already, that's a one-line addition to thread it through, same pattern as `Repl`. |
| `boukensha/client.py:44,55` (retry-exhausted, raises `ApiError`) | **Not changed directly.** `Client` has no `Logger`/session context today, and threading one in is a bigger structural change than this plan needs — the *outer* catches above (`agent.py:157`, `repl.py:180`) already log the resulting `ApiError` with full session context by the time it's actually handled. Noted as a scoped-out tradeoff, not an oversight. |
| `boukensha/mcp/client.py:66,71,75,130` (pipe-close swallows) | **Not changed.** Genuinely best-effort cleanup (closing stdin/stdout/stderr on shutdown) — logging these would be noise, not signal. |

Ruby mirrors the same table at its equivalent sites
(`lib/boukensha.rb:214`, `lib/boukensha/agent.rb:118,170`,
`lib/boukensha/repl.rb:135,137`, `lib/boukensha/tui.rb:276`) with
`lib/boukensha/error_log.rb` as `error_log.py`'s Ruby twin (`Marshal`-free,
plain `File.open(..., "a")` + `JSON.generate`, `e.backtrace` for the
backtrace array).

### 4. `mud_manager`: raw command logging + stop crashing on bad arity

**Logging** (`lib/mud_manager/jsonl_log.rb`, new — `mud_manager` has no
dependency on the `boukensha` gem/package, so this is a small
self-contained twin of the JSONL-line-per-event shape `Logger` already
uses, not a shared import):

```ruby
module MudManager
  class JsonlLog
    def initialize(path)
      @path = path
      @mutex = Mutex.new
    end

    def write(event)
      return unless @path
      @mutex.synchronize do
        File.open(@path, "a") { |f| f.puts(event.merge(at: Time.now.iso8601(6)).to_json) }
      end
    end
  end
end
```

Wired into `bin/mud-manager`'s `call_tool` (lines 385-410), around the
existing `session.drain` / `send_command` / `read_until_prompt` sequence
-- the natural place, since `command` (a `Primitives::Command`, exposing
`.verb`/`.raw`/`.args`) and `text` (the raw response) are both already in
scope there:

```ruby
def self.call_tool(name, raw_args)
  tool = TOOLS_BY_NAME[name]
  return { is_error: true, text: "unknown_tool: no tool named #{name.inspect}" } unless tool

  args = coerce_args(tool, raw_args)
  command = tool[:call].call(args)
  session.drain
  started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  session.send_command(command)
  text = session.read_until_prompt
  mud_log.write(tool: name, args: args, verb: command.verb, raw: command.raw,
                response: text, duration_ms: ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - started) * 1000).round(1))
  { is_error: false, text: text }
rescue ArgumentError => e
  mud_log.write(tool: name, args: args, error_class: e.class.name, error_message: e.message, backtrace: e.backtrace)
  { is_error: true, text: "argument_error: #{e.message}" }
rescue MudManager::Session::Error => e
  mud_log.write(tool: name, args: args, error_class: e.class.name, error_message: e.message, backtrace: e.backtrace)
  { is_error: true, text: "session_error: #{e.class}: #{e.message}" }
end
```

**On by default** (resolved — see Resolved decisions below): `mud_log` is a
module-level

```ruby
mud_log = JsonlLog.new(
  File.join(ENV["MUD_MANAGER_LOG_DIR"] || File.expand_path("../../log", __dir__), "mud_manager.jsonl")
)
```

If `MUD_MANAGER_LOG_DIR` isn't set, it falls back to a `log/` directory
inside `mud_manager` itself (sibling to `bin/`/`lib/`), so command logging
works out of the box for anyone running `mud-manager` directly (the
`play-mud` skill, `examples/mcp_mud_demo.py`, etc.), not just through
boukensha. Pointing `MUD_MANAGER_LOG_DIR` at the shared `.boukensha`
directory (Config wiring, below) is still what makes it show up unified
in `logging_monitor`'s `/mud` page — the fallback just means logging
itself is never silently off.

**Stop crashing on uncaught errors.** Confirmed: `run` (`bin/mud-manager`,
~lines 447-459) has no blanket rescue around `handle(msg)` — only a
`JSON::ParserError` rescue around parsing the incoming line. Any exception
`call_tool`'s own two `rescue`s don't cover (a `NoMethodError`, a
different `ArgumentError` shape, anything) propagates uncaught, kills the
subprocess, and produces exactly the bare, un-logged
`ArgumentError: wrong number of arguments (given 1, expected 0)` crash the
brief describes. Add a blanket rescue around the dispatch in `run`'s loop:

```ruby
begin
  response = handle(JSON.parse(line))
rescue StandardError => e
  mud_log.write(fatal: true, error_class: e.class.name, error_message: e.message, backtrace: e.backtrace)
  response = { jsonrpc: "2.0", id: nil, error: { code: -32603, message: "internal_error: #{e.class}: #{e.message}" } }
end
```

This changes the failure mode from "the whole MCP subprocess dies,
boukensha sees a spawn/pipe failure with no detail" to "one request
fails, gets logged with full backtrace, the subprocess keeps running" —
directly fixing the motivating symptom's blast radius, not just its
visibility.

**Config wiring**: `.boukensha/settings.yaml`'s `mcp_servers.mud.env`
block gains `MUD_MANAGER_LOG_DIR: <repo root>/.boukensha` (same backup-
first precedent as `tool_scoping`/`map_zone`'s earlier edits to this
file) — so `mud_manager.jsonl` lands in the same directory tree
`logging_monitor` already reads `sessions/` and `errors.jsonl` from.

### 5. `logging_monitor` — the app itself

**Flask** (new dependency — resolved, see Resolved decisions below). No
Python web framework exists anywhere in the shared `.venv` today, so this
is a deliberate addition, not a rediscovery of something already
available: `flask` in a new `requirements.txt` scoped to
`week3_capable/python/logging_monitor` only, installed into the shared
`.venv` alongside it (`.venv/bin/pip install -r
week3_capable/python/logging_monitor/requirements.txt`), same pattern
every other `week3_capable/python/*` package already uses for its own
deps. Chosen over `http.server`+hand-rolled templates because: it's the
direct Python analog to `log_viz`'s Sinatra (same minimal-framework
philosophy, so the two apps stay conceptually consistent); it bundles
Jinja2, whose autoescaping matters concretely here (`errors.jsonl`
backtraces and raw MUD output are exactly the kind of content that's
risky to interpolate into HTML by hand); and it has a standard, boring
streaming-response pattern for SSE (`Response(generator(), mimetype=
"text/event-stream")`) instead of reimplementing chunked writes over
`BaseHTTPRequestHandler`. Flask's threaded dev server (`app.run(threaded=
True)`) is sufficient for a local observability tool — an open SSE stream
on one connection doesn't block other requests.

**Routes**:

- `GET /` — session list (id, start time, turn/tool counts, total
  duration, cost if recorded), newest first. Ports
  `log_viz/lib/log_viz/app.rb`'s index + `session.rb`'s summary
  extraction.
- `GET /sessions/<id>` — full transcript: every phase entry rendered
  (ports `session.rb`'s phase-switch and `ansi.rb`'s SGR-to-HTML), each
  row showing `at` and `duration_ms` since the previous entry (Design 1),
  `error` phase entries (Design 2) rendered inline with an
  expand-for-backtrace control, **plus the per-turn waterfall** (Design 6)
  at the top of the page.
- `GET /sessions/<id>/stream` — SSE (`Content-Type: text/event-stream`).
  Tails the file: seeks to end-of-file-at-request-time, then polls (e.g.
  every 500ms) for new lines, parses+renders each as it appears, yields
  `data: <html-fragment>\n\n`. This is what makes "sit on the page and
  watch it update" real. The session page's own JS opens an `EventSource`
  against this endpoint, appends fragments to the transcript, *and*
  appends new spans to the waterfall as they complete.
- `GET /errors` — Errors page: `errors.jsonl` read newest-first, one row
  per entry (`at`, `where`, `operation`, `task`, a link to `session_id`'s
  transcript if present, `error_class`, `error_message`, backtrace
  behind an expand toggle).
- `GET /mud` — raw MUD command log (`mud_manager.jsonl`): tool, args,
  verb/raw command, response, duration; errors highlighted.

**`bin/logging_monitor`**: env-configurable like `log_viz`
(`BOUKENSHA_DIR` for the log root — same resolution `Config` already
uses; `LOGGING_MONITOR_PORT`/`LOGGING_MONITOR_BIND`, defaults `4568`/
`localhost`, one port over from `log_viz`'s `4567` so both run side by
side — resolved: `log_viz` stays as-is, see Resolved decisions below).

### 6. The waterfall — where each turn spends its time

New request, added directly to this plan doc. The goal: for a given
turn, show *where the wall-clock time actually went* — the API call
itself vs. each tool dispatch vs. compaction — as a horizontal timeline,
not just a flat list of timestamped log lines.

**The JSONL log has no explicit span boundaries** — it's a flat sequence
of point-in-time events (`turn`, `iteration`, `prompt`, `tool_call`,
`tool_result`, `response`, ...), not `span_start`/`span_end` pairs. Spans
have to be *reconstructed* from that sequence. This exact reconstruction
already exists in this repo:
`week2_observability/observability/scripts/session_to_traces.py`
converts a session JSONL into `session -> turn -> iteration -> tool_call`
spans (with `prompt`/`plan`/`response` events attached to the enclosing
span) for shipping to Tempo via OTLP. `logging_monitor/spans.py` ports
that same reconstruction logic in-process, targeting inline SVG instead
of an OTLP payload — the nesting rules (which event opens/closes which
span) don't need to be reinvented, just re-target the output.

**Span reconstruction** (`spans.py`):
- A `turn` span runs from one `turn` event to the next `turn` event (or
  `turn_end`).
- Within a turn, an `iteration` span runs from one `iteration` event to
  the next `iteration`/`turn_end`.
- Within an iteration, a `prompt` event paired with the `response` event
  that follows it becomes an `api_call` span — this is the single most
  useful span for "where did the time go," since it's the actual LLM
  round-trip latency, isolated from tool execution time.
- Each `tool_call`/`tool_result` pair (matched positionally — they're
  always emitted adjacently, in order, per dispatch) becomes a
  `tool_call` span, labeled with the tool name; failed ones (`ok: false`)
  render distinctly (red/hatched) and link to the matching `error` event
  if `Logger.error` (Design 2) recorded one for that same dispatch.
- A `compaction` event becomes a zero-duration marker on the timeline
  (it's logged as a single point, not a start/end pair) rather than a
  span with real width.

Every span's start offset and duration are computed directly from the
now-microsecond-precision `at` fields (Design 1) — without that
precision bump this view would be useless (every span rounding to a
whole second).

**Rendering**: inline SVG, generated server-side, no charting library and
no CDN dependency (same "self-contained, no external assets" approach
already used elsewhere for diagrams in this environment) — a `<rect>`
per span, `x` = start offset in ms scaled to pixels, `width` = duration
scaled the same way, `y` = one row per nesting level (turn row, its
iteration rows indented under it, each iteration's `api_call`/`tool_call`
spans indented further), fill color keyed by span type/tool name, a
`<title>` child for hover tooltips with exact numbers, and a text label
truncated to fit the bar. Clicking a `tool_call` span scrolls the
transcript below to that event.

**Scope**: the session page shows the waterfall for the *whole session*
by default (one row per turn, collapsed), with each turn row expandable
to reveal its own iteration/api_call/tool_call sub-waterfall — matching
"where each turn spends its time" as the primary unit of interest, while
still giving the session-wide overview for free from the same
reconstruction pass.

## Testing

1. **Offline, unit** — `tests/test_sessions.py`: feed synthetic JSONL
   fixtures (one per phase, plus an `error` phase entry) through
   `sessions.py`'s parser; assert the rendered entry list and computed
   `duration_ms` values are correct, including sub-second deltas.
   `tests/test_errors.py`: same shape for `errors.py` against a synthetic
   `errors.jsonl`. `tests/test_spans.py`: feed a synthetic multi-turn,
   multi-iteration JSONL fixture (including a failed `tool_call`) through
   `spans.py`; assert the reconstructed span tree has the right nesting,
   start offsets, and durations, and that the failed tool call's span is
   flagged distinctly.
2. **Offline, unit (Python boukensha)** — a new
   `tests/test_error_log.py` in `map_zone`: call `error_log.log_error`
   with a raised-and-caught exception, assert the written JSONL line has
   the right `error_class`/`error_message`/non-empty `backtrace` list,
   and that `Logger.error(...)` writes to *both* the per-session file and
   `errors.jsonl`.
3. **Offline, unit (`mud_manager`)**: a small Ruby test (using the
   existing `FakeMud` harness) asserting `JsonlLog#write` produces one
   JSONL line per call and that `call_tool` calls it exactly once per
   successful tool call plus once more on the `rescue` paths.
4. **Live** — restart `mud-manager` with `MUD_MANAGER_LOG_DIR` set,
   drive a few real moves through `week3_capable/python/map_zone`'s
   `examples/example.py` or `bin/boukensha`, confirm `mud_manager.jsonl`
   picks up real commands/timings, then browse `/mud` in
   `logging_monitor` and confirm the page matches.
5. **Live, forcing the actual motivating symptom** — deliberately call an
   MCP tool with a bad argument shape (or temporarily break a `TOOLS`
   lambda's arity) to reproduce a genuine `ArgumentError`, confirm: (a)
   the subprocess does *not* crash anymore, (b) the error shows up in
   `errors.jsonl` with full backtrace, (c) it renders correctly on
   `logging_monitor`'s `/errors` page.
6. **Live, realtime** — start `bin/boukensha`, open that session's page
   in `logging_monitor` mid-run, confirm new tool calls/responses appear
   without a manual page reload.

## Task list

1. Bump timestamp precision: `logger.py`'s `_iso_now`, `logger.rb`'s
   equivalent, to microsecond precision.
2. Write `boukensha/error_log.py` + `Logger.error()`; Ruby twins
   `error_log.rb` + `Logger#error`.
3. Wire the catch-site table (Design 3) through both `map_zone`'s Python
   boukensha and `week1_baseline/ruby/12_context`'s Ruby boukensha.
4. Write `lib/mud_manager/jsonl_log.rb`; wire into `bin/mud-manager`'s
   `call_tool` (logging + the two existing rescues, on-by-default path
   resolution) and add the new blanket rescue around `run`'s dispatch
   loop.
5. `cp .boukensha/settings.yaml .boukensha/settings.yaml.bak.before-logging_monitor`;
   add `MUD_MANAGER_LOG_DIR` to `mcp_servers.mud.env`, pointed at the
   shared `.boukensha` directory.
6. Scaffold `week3_capable/python/logging_monitor`: `requirements.txt`
   (`flask`), `pyproject.toml`; `.venv/bin/pip install -r
   week3_capable/python/logging_monitor/requirements.txt`.
7. Write `sessions.py`/`ansi.py` (port of `log_viz`'s Ruby parsing logic),
   `errors.py`, `mud_log.py`.
8. Write `spans.py` (port `session_to_traces.py`'s span-reconstruction
   logic, re-targeted at the waterfall's data shape instead of OTLP).
9. Write `server.py`: the five routes, including the SSE tail endpoint.
10. Write Jinja2 `templates/` + `static/style.css` (adapt from
    `log_viz`), including the waterfall SVG rendering in `session.html`.
11. Write and pass the offline unit tests (Testing 1-3).
12. Run the live verifications (Testing 4-6), including deliberately
    forcing the motivating `ArgumentError` to confirm both the crash and
    the visibility gap are actually closed, and confirming the waterfall
    renders correctly for a real multi-turn, multi-tool-call session.
13. Update `README.md` for `logging_monitor` and note the change in
    `map_zone`'s and the Ruby track's own READMEs (a one-line pointer:
    "errors now also logged to `<BOUKENSHA_DIR>/errors.jsonl`, browsable
    via `logging_monitor`").
14. Don't commit until the user reviews.

## Resolved decisions

1. **`log_viz` stays untouched** — `logging_monitor` is additive, not a
   replacement. Both run side by side (`log_viz` on `:4567`,
   `logging_monitor` on `:4568`).
2. **`MUD_MANAGER_LOG_DIR` defaults to *on***, not opt-in — falls back to
   a `log/` directory inside `mud_manager` itself if the env var isn't
   set, so command logging works out of the box even without boukensha
   wiring anything (Design 4).
3. **Catch-site scope (Design 3) confirmed as originally proposed** —
   `client.py`'s low-level retries and `mcp/client.py`'s best-effort pipe
   closes stay untouched; outer catches with real session context cover
   the meaningful cases.
4. **No rotation/retention for `errors.jsonl`** — matches every other
   durable log in this repo today (`sessions/` has none either).
5. **Flask added as a new dependency**, scoped to
   `week3_capable/python/logging_monitor`'s own `requirements.txt` —
   chosen over stdlib `http.server` specifically because of Jinja2's
   autoescaping (backtraces/raw MUD output are risky to hand-interpolate
   into HTML) and its standard SSE streaming-response pattern. Doesn't
   touch any other package's dependencies.
6. **Waterfall interface added** (Design 6) — per-turn timing breakdown
   (API call latency vs. each tool dispatch vs. compaction), reconstructed
   from the existing flat event log using the same span-nesting logic
   `session_to_traces.py` already established for this repo's OTel path,
   rendered as inline SVG with no new dependency and no CDN asset.