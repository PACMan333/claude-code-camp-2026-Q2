# 07 · The Run DSL (Python port)

Python port of `week1_baseline/ruby/07_the_run_dsl`. This step adds a
single top-level entry point, `boukensha.run(...)`, plus a small `RunDSL`
host object a caller can register ad-hoc tools against. Every previous
step required manually constructing and wiring `Context`, `Registry`, a
backend, `PromptBuilder`, `Client`, `Logger`, and `Agent`; `boukensha.run`
hides all of that behind one call.

**Like steps 04–06, this step's example makes real, billed HTTP requests
to a live LLM API** — inherited from `Client`/`Agent`, not new here.

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/07_the_run_dsl/requirements.txt
.venv/bin/pip install -e week1_baseline/python/07_the_run_dsl
```

This step is a self-contained copy of the `boukensha` package (mirroring
Ruby's per-step-folder duplication). `tool.py`, `message.py`, `context.py`,
`registry.py`, `client.py`, `agent.py`, `prompt_builder.py`,
`tasks/player.py`, `tasks/base.py`, `backends/base.py`, all five backends,
and `prompts/system.md` are copied forward unchanged from
`python/06_the_logger` — their Ruby sources are byte-identical at this
step too. Installing this step editable repoints `import boukensha` at
this step's copy.

## New Files

| File | Description |
|---|---|
| `boukensha/run_dsl.py` | `RunDSL` — the object passed into `register_tools`; exposes only `tool` |

## Updated Files

| File | Change |
|---|---|
| `boukensha/__init__.py` | Adds `run()`, the top-level DSL entry point |
| `boukensha/logger.py` | Adds `turn(n=)` (a new, currently-unused log phase) and `subscribe(callback)` (broadcasts every event to registered callbacks as it's written) |
| `boukensha/config.py` | **Re-adds** `mud_host`/`mud_port`/`mud_username`/`mud_password` — deleted in step 06, back this step (see Considerations) |
| `boukensha/errors.py` | **Re-adds** `LoopError` — also deleted in step 06, also back this step |

## How It Works

`boukensha.run` builds every primitive internally — `Config`, `Context`,
`Registry`, a backend, `PromptBuilder`, `Client`, `Logger`, `Agent` — from
just a `task` string and a handful of optional overrides, then runs the
agent and returns its final response.

## `boukensha.run`

```python
def register(dsl):
    dsl.tool(
        "read_file",
        description="Read a file from disk",
        parameters={"path": {"type": "string", "description": "File path"}},
        block=lambda *, path: open(path).read(),
    )

result = boukensha.run(task="Summarise boukensha/__init__.py", register_tools=register)
```

| Option | Default | Description |
|---|---|---|
| `task` | *(required)* | The user message handed to the agent |
| `system` | task's configured system prompt | System prompt override |
| `model` | task's configured model | Model name override |
| `backend` | task's configured provider | `"anthropic"`, `"openai"`, `"gemini"`, `"ollama"`, or `"ollama_cloud"` |
| `api_key` | the matching `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`GEMINI_API_KEY`/`OLLAMA_API_KEY` env var | API key for the chosen backend; not needed for `"ollama"` |
| `ollama_host` | `"http://localhost:11434"` | Ollama base URL |
| `log` | `None` | Optional JSONL path override; defaults to `.boukensha/sessions/<session-id>.jsonl` |
| `max_output_tokens` | task's configured value (1024) | Per-reply output cap |
| `register_tools` | `None` | A callable taking the `RunDSL` instance — see below |

This table is built directly from the real `boukensha/__init__.py`
source, not adapted from the Ruby step's own README table, which
documents a **different, later** signature (see Considerations for why).

### `register_tools`, not a bare block

Ruby's `Boukensha.run(task: "...") do ... end` does `instance_eval` on the
block, so `self` inside it silently becomes a `RunDSL` and bare
`tool "name", ...` calls work with no explicit receiver. Python has no way
to rebind a plain function's implicit `self`, so `register_tools` takes
the `RunDSL` object as an explicit argument instead — callers write
`dsl.tool(...)`, not bare `tool(...)`. It's called once, right after
`Context`/`Registry` are built and before the backend/logger/agent exist,
matching Ruby's real ordering.

## Session Logs

Unchanged from step 06 — every phase of the turn still goes to
`.boukensha/sessions/<session-id>.jsonl`, now also carrying a snapshot of
`task`/`max_iterations`/`max_output_tokens`/`model`/`provider` in the
`session_start` event, since `boukensha.run` has that information handy
at construction time and passes it through as `Logger(snapshot=...)`.

## Task Configuration

Unchanged from steps 05–06:

```yaml
tasks:
  player:
    provider: anthropic
    model: claude-haiku-4-5
    prompt_override:
      system: true
```

## Considerations

**The Ruby README for this step is unusually unreliable — it describes a
different, later signature, not this step's real one.** It's titled "Step
6" (off by one), and its options table lists `token_budget:` (default
`8192`) and `max_tokens:` (default `1024`) — neither exists anywhere in
the real `lib/boukensha.rb` (the real parameter is `max_output_tokens:`,
with no hardcoded numeric default — it falls through to the task's
configured value). Cross-checked against `week1_baseline/ruby/ITERATIONS.md`'s
step-11 entry: *"`Boukensha.run` / `.repl` — `context_window:` keyword
replaces `token_budget:`"* — confirming `token_budget:` is a **future**
rename target the README describes prematurely. It also documents
`backend:` as "`:anthropic` or `:ollama`" only, though the real code has
supported all five backends since step 03. This port's table above comes
straight from the real source, not the Ruby README.

**A genuine off-by-one in Ruby's `example.rb` fallback path doesn't
carry into the Python port, because the two runners mask it
differently.** Ruby's `example.rb` sets
`ENV["BOUKENSHA_DIR"] ||= File.expand_path("../../../.boukensha", __dir__)`
— one `../` short of the real repo root, resolving to a nonexistent
`week1_baseline/.boukensha`. In Ruby this never surfaces because
`week1_baseline/bin/ruby/07_the_run_dsl` (the actual entry point)
`export`s the correct `BOUKENSHA_DIR` *before* invoking `ruby`, so the
`||=` in `example.rb` is always a no-op in practice. The **Python runner
doesn't do that** — `week1_baseline/bin/python/07_the_run_dsl` relies
entirely on `example.py`'s own fallback — so a literal translation of
Ruby's broken relative path would have actually broken the Python
example (unable to find `settings.yaml`, `.env`, or `prompts/`). This
port uses the correct 5-`.parent()` resolution instead (the same one
steps 05–06's `example.py` already used correctly), not Ruby's off-by-one.

**`Config#mud_host`/`mud_port`/`mud_username`/`mud_password` and
`LoopError` are re-added, not newly invented** — both were deleted in
step 06 (that step's own README documented them as unused dead code), and
both are back in step 07 with identical bodies to their pre-deletion
form. Still referenced nowhere in the shipped `lib`/`examples` (confirmed
by `grep`) — still dead code today. Per `ITERATIONS.md`'s step-10 entry,
`mud_*` scaffolds a future MUD-connection tool ("MUD gameplay comes from
the `mud-manager --mcp` daemon, the same `mud_manager` gem the old
`Tools::Mud` wrapped"); `LoopError` is mentioned in the step-5 entry
alongside `Boukensha.run` itself, suggesting a future error path that
hasn't landed yet. Ported back faithfully rather than treated as churn to
second-guess.

**`Logger.turn`/`Logger.subscribe` are new and also currently unused —
both are forward-looking scaffolding, confirmed via `ITERATIONS.md`.**
`Agent` is byte-identical to step 06 and still only calls `iteration`,
never `turn` — likely scaffolding for step 08's REPL, where a `turn`
phase distinct from the existing per-API-call `iteration` phase would
track multi-turn sessions ("A single `Context` is shared across all
turns"). `subscribe` is confirmed by the step-11 entry as the mechanism
a future TUI uses for its live progress line ("every structured log event
is now broadcast to subscribers... which is how `Tui` updates its
progress line in real time without polling") — a plain observer callback
appended to a list and invoked with each event after it's written and
flushed, not another instance of the `instance_eval`/`RunDSL` problem.

**`RunDSL.tool` mirrors `Registry.tool`'s existing Python signature
shape** (`description` as a plain positional-or-keyword parameter, not
keyword-only) rather than independently re-deriving a "more faithful"
keyword-only translation of Ruby's `description:` — `RunDSL.tool` is a
thin pass-through, so it follows whatever shape `Registry.tool` already
settled on since step 02.

**Ruby's `||`/`||=` only treat `nil`/`false` as "unset"; the five
default-fills in `run()` use `is not None`, not `or`.** Python's `or`
would also treat `0`, `""`, etc. as "unset," which would silently discard
a caller's explicit `max_output_tokens=0` and substitute the task's
configured default instead — a real behavior difference, not just style.

## Run Example

```bash
./week1_baseline/bin/python/07_the_run_dsl
```

Makes one or more real POSTs to the configured provider's API (same as
steps 05–06) and prints the agent's final response; every phase is
additionally written to `.boukensha/sessions/<session-id>.jsonl`. Exact
iteration count, response text, token counts, and session id will differ
run to run since it's a live model call, not a fixture.
