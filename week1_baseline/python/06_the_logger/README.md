# 06 · The Logger (Python port)

Python port of `week1_baseline/ruby/06_the_logger`. This step adds
`Logger`: a file logger that records each agent turn as structured JSON
Lines, and threads it through `Agent` so every phase of the loop — not
just the final response — is captured for later inspection.

**Like steps 04–05, this step's example makes real, billed HTTP requests
to a live LLM API**, using whatever key is configured in `.boukensha/.env`
— inherited from the `Client`/`Agent` built in earlier steps, not new
here.

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/06_the_logger/requirements.txt
.venv/bin/pip install -e week1_baseline/python/06_the_logger
```

This step is a self-contained copy of the `boukensha` package (mirroring
Ruby's per-step-folder duplication). `tool.py`, `message.py`, `context.py`,
`registry.py`, `client.py`, `tasks/player.py`, `tasks/base.py`,
`backends/base.py`, all five backends, and `prompts/system.md` are copied
forward unchanged from `python/05_agent_loop` — their Ruby sources are
byte-identical at this step too. Installing this step editable repoints
`import boukensha` at this step's copy.

## New Files

| File | Description |
|---|---|
| `boukensha/logger.py` | `Logger` — writes one JSONL event per phase of an agent turn to `.boukensha/sessions/<session-id>.jsonl` |

## Updated Files

| File | Change |
|---|---|
| `boukensha/__init__.py` | Adds a small module-level singleton (`current_config`, `quiet`/`is_quiet`, `loud`, `debug`/`is_debug`) that backs the logger's default session directory and its debug-gated `raw` event; drops `LoopError` (see below) |
| `boukensha/errors.py` | Removes `LoopError` — it was never raised (step 05's own README already flagged this as unused dead code); Ruby's step-06 source deletes it outright, confirming that read |
| `boukensha/config.py` | Removes `mud_host`/`mud_port`/`mud_username`/`mud_password` — unused dead code, confirmed removed nowhere-referenced in both languages |
| `boukensha/prompt_builder.py` | Adds a `backend()` accessor, so `Logger` can pull `model`/`usage_unit`/`estimate_cost` from the active backend for cost logging |
| `boukensha/agent.py` | Threads a `logger=` through; logs every phase (`iteration`, `prompt`, `raw`, `response`, `turn_end`, `limit_reached`, `tool_call`, `tool_result`); a tool call that raises is now caught and logged as `ok: false` instead of crashing the turn |

## How It Works

`Agent` calls `self._logger.<phase>(...)` at each step of the loop instead
of (or in addition to) doing anything else observable. Nothing about the
loop's actual control flow changes — `Logger` is a side effect, not a
dependency of the decision logic.

## `boukensha.Logger`

A plain object with one method per phase, matching the real
`lib/boukensha/logger.rb` source (not the Ruby step's own README table,
which is missing several parameters and two whole methods — see
Considerations):

| Method | Phase | Logs |
|---|---|---|
| `iteration(n=, max=)` | `iteration` | loop counter and ceiling |
| `limit_reached(kind=, n=, max=)` | `limit_reached` | why the ceiling tripped |
| `prompt(messages=, tools=)` | `prompt` | message count/list, tool count/names |
| `tool_call(name=, args=)` | `tool_call` | tool name and arguments |
| `tool_result(name=, result=, ok=True, error=None)` | `tool_result` | tool result, and whether it succeeded |
| `response(text=, usage=None, stop_reason=None, task=None, backend=None)` | `response` | response text, normalized token usage, task/provider/model, estimated cost |
| `turn_end(reason=, iterations=, tokens=None)` | `turn_end` | how and when the turn ended |
| `raw(data=)` | `raw` | raw provider response, only when `boukensha.is_debug()` is on |
| `close()` | — | closes the underlying file handle |

```python
logger = Logger()
agent = Agent(
    context=ctx,
    registry=registry,
    builder=builder,
    client=client,
    logger=logger,
    task_settings=player_settings,
)
```

You can also provide a session id or override the destination directory:

```python
Logger(session_id="manual-session")
Logger(dir="/tmp/boukensha-sessions")
```

`log=` still accepts an explicit file path, but normal usage should write
under `.boukensha/sessions`.

## Session Logs

Each `Logger` instance creates a session id and writes one log file:

```
.boukensha/sessions/<session-id>.jsonl
```

Every line is a complete JSON object with `session_id`, `at`, and `phase`
fields, plus phase-specific data. This is a real, captured example (from
an actual live run, `.boukensha/sessions/20260723T195204Z-e0d3c74d.jsonl`)
— not the Ruby README's illustrative snippet:

```json
{"phase": "session_start", "session_id": "20260723T195204Z-e0d3c74d", "at": "2026-07-23T15:52:04-04:00"}
{"phase": "iteration", "n": 1, "max": 25, "session_id": "20260723T195204Z-e0d3c74d", "at": "2026-07-23T15:52:04-04:00"}
{"phase": "response", "text": "(tool use — 1 call)", "usage": {"input_tokens": 704, "output_tokens": 56, "...": "..."}, "stop_reason": "tool_use", "task": "player", "provider": "anthropic", "model": "claude-haiku-4-5", "usage_unit": "tokens", "input_tokens": 704, "output_tokens": 56, "cost_usd": 0.000984, "session_id": "...", "at": "..."}
{"phase": "tool_call", "name": "read_file", "args": {"path": "README.md"}, "session_id": "...", "at": "..."}
{"phase": "tool_result", "name": "read_file", "result": "...", "ok": true, "error": null, "session_id": "...", "at": "..."}
{"phase": "turn_end", "reason": "completed", "iterations": 2, "tokens": null, "session_id": "...", "at": "..."}
```

Model response lines include the active task, provider, model, normalized
token counts, and estimated USD cost when the backend has token pricing
data.

## Task Configuration

Unchanged from step 05:

```yaml
tasks:
  player:
    provider: anthropic
    model: claude-haiku-4-5
    prompt_override:
      system: true
```

## Debug Events

Call `boukensha.debug()` before running the agent to include raw provider
responses in the log:

```python
import boukensha
boukensha.debug()
```

## Considerations

**`boukensha.current_config()`, not `boukensha.config()`.** Ruby's
`Boukensha.config` (a module method) and `boukensha/config.py` (a Python
submodule already imported by every step's `example.py`, e.g.
`from boukensha.config import PROMPTS_DIR`) live in separate namespaces in
Ruby but would collide in Python — a module-level function named `config`
inside `boukensha/__init__.py` would reassign the `boukensha.config`
attribute, shadowing the submodule for any future attribute-style access.
Renamed to `current_config()` to avoid relying on Python's import-system
internals to paper over the collision.

**`boukensha.quiet()`/`is_quiet()` and `boukensha.debug()`/`is_debug()`,
not `quiet()`/`quiet()` and `debug()`/`debug()`.** Ruby's `quiet!`/`quiet?`
and `debug!`/`debug?` share a root name across separate bang/query method
tables — dropping the punctuation per this port's usual convention would
collapse each pair onto one identical Python name (same shape as step
03's `model_info` collision). Setter keeps the bare verb name; getter gets
an `is_`-prefixed boolean name. Only `is_debug()` is actually exercised by
the shipped fixture (via `Logger.raw`'s guard) — `quiet()`/`is_quiet()`/
`loud()` are unused this step too, real public API but dead code for now
(the same situation `LoopError` was in during step 05, before Ruby
deleted it this step).

**`Logger`'s `_provider_name` normalizes `"OpenAI"` → `"openai"` rather
than preserving Ruby's regex-derived `"open_ai"`.** Ruby's CamelCase→
snake_case regex gets every other backend right (`OllamaCloud`→
`ollama_cloud`, `Anthropic`→`anthropic`, `Gemini`→`gemini`, `Ollama`→
`ollama`), but inserts an underscore for `OpenAI`→`open_ai`, which doesn't
match the real provider key (`"openai"`) used everywhere else in
`settings.yaml`/config. Fixture-masked (the shipped fixture uses
`provider: anthropic`), same shape as step 03's `to_messages` bug and step
05's `PROMPTS_DIR` regression — but here resolved in favor of
**normalizing**, since this is an internal log-metadata helper rather than
user-facing Ruby-lesson content, and a correct `provider` field in the log
is more useful than faithfully reproducing an incidental regex quirk.

**Two Ruby→Python default-argument translations this step, not literal
copies.** Ruby method-parameter default *expressions*
(`logger: Logger.new`, `snapshot: {}`) are evaluated fresh on every call;
Python default *values* are evaluated once, at function-definition time,
and then reused (and, for mutable objects, shared) across every call that
doesn't override them. `Agent.__init__(..., logger=None, ...)` builds its
own `Logger()` inside the body when `logger` is `None`, rather than
`logger=Logger()` in the signature (which would silently share **one**
`Logger` — one file, one session id — across every `Agent` built without
an explicit `logger=`, for the life of the process). `Logger.__init__`
does the same for `snapshot=None` → `snapshot or {}`.

**A raised tool call no longer crashes the turn.** `Agent._handle_tool_calls`
wraps each `registry.dispatch(...)` call in `try/except Exception`,
turning any error (including `UnknownToolError` for an unregistered tool
name) into an `"ERROR: {type}: {message}"` tool_result string and an
`ok: false` log entry, instead of propagating and ending the whole run.
The one cosmetic difference from Ruby: the fallback string uses
`type(e).__name__` (e.g. `ValueError`), not Ruby's fully qualified
`e.class` (e.g. `Boukensha::UnknownToolError`) — same class of cosmetic
repr difference already accepted since step 00, not a new one.

## Run Example

```bash
./week1_baseline/bin/python/06_the_logger
```

This makes one or more real POSTs to the configured provider's API (same
as step 05) and prints the agent's final response; every phase of the
turn is additionally written to `.boukensha/sessions/<session-id>.jsonl`.
Exact iteration count, response text, token counts, and session id will
differ run to run since it's a live model call, not a fixture.
