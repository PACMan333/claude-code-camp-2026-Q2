# 12 · Context Management (Python port)

Python port of `week1_baseline/ruby/12_context`. When you call an LLM
directly you are responsible for the context window — there is no
auto-compacting. This step adds real token tracking, colour-coded
warnings, and automatic compaction so the agent never silently blows past
the limit, on top of the MCP-host tool model and Textual TUI carried
forward from step 11.

The standard tool library is still **MCP** — boukensha ships no tools of
its own. Everything from steps 10–11 (`boukensha.mcp.Client`,
`boukensha.tools.mcp`, `mcp_servers:` config, the Textual TUI itself) is
unchanged in its fundamentals here — see `python/10_standard_tool_library/README.md`
and `python/11_tui/README.md` for that material. This README covers only
what step 12 adds.

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/12_context/requirements.txt
.venv/bin/pip install -e week1_baseline/python/12_context
```

No new third-party dependency this step (still just `PyYAML`,
`python-dotenv`, `textual`).

This step is a self-contained copy of the `boukensha` package.
`version.py`, `models.py` (new), `context.py`, `config.py`, `agent.py`,
`logger.py`, all five `backends/*.py`, `mcp/client.py`, `repl.py`,
`tui.py`, and `__init__.py` change; everything else is copied forward
unchanged from `python/11_tui`.

## What's new

### Accurate context tracking

`Context` now maintains two distinct token counts:

| Attribute | What it measures |
|-----------|-------------------|
| `context_window` | The model's maximum input token capacity, looked up from `models.context_window(model)` |
| `current_tokens` | Tokens actually used in the most recent API call (`usage.input_tokens` from the response) |

Previously the *output* token cap was the only thing tracked/displayed,
and the TUI's "ctx" figure was a session-wide cumulative sum that grew
without bound even after `/clear`. Both are fixed: `current_tokens` is
overwritten (not accumulated) after every response, including mid-turn
tool-use calls, so the display always reflects what the *next* call will
actually send.

### `boukensha.models`

A static model → capability table built from every backend's own
`MODELS` dict, so `Context` can be sized correctly before a backend is
constructed:

```python
boukensha.models.context_window("gpt-5.5")  # => 1_000_000
```

Unknown models fall back to a conservative `DEFAULT_CONTEXT_WINDOW`
(32,000) rather than silently assuming a huge window.

### Context colour coding

The TUI's progress and status lines now colour the context indicator by
how full the window is:

| Usage | Colour | Meaning |
|-------|--------|---------|
| < 70% | Grey | Normal |
| 70–84% | Yellow | Approaching limit |
| ≥ 85% | Red | Compaction imminent |

A `⚠` symbol also appears in the status bar at 85%+.

### Auto-compaction

At the start of each agent turn, if `current_tokens / context_window ≥`
the configured `agent.compaction_threshold` (default `0.85`), `Agent`
automatically compacts the context before making any API call:

```
[context compacted — 12 messages dropped to free space]
```

Compaction drops the oldest 40% of messages (keeping at least 2) and
resets `current_tokens` to 0; the next API response reports the true new
size.

### `Context.compact_messages`

```python
dropped = ctx.compact_messages(target_fraction=0.60)
# => 12  (number of messages dropped)
```

`target_fraction` is accepted but never actually used in the body — Ruby's
own `compact_messages!(target_fraction: 0.60)` has the same unused
parameter. Ported faithfully rather than silently dropping or "fixing" an
unused keyword that costs nothing to keep.

### `/compact` command

Manual compaction from the REPL or TUI:

```
boukensha> /compact
(compacted context — 12 messages dropped)
```

### `Logger.compaction` event

```json
{"phase": "compaction", "before": 172000, "dropped": 12, "context_window": 200000}
```

Emitted whenever auto- or manual compaction runs. The TUI subscribes to
this event to show the compaction notice in the conversation view.

### A second, independent circuit breaker: `max_turn_tokens`

`Agent` now stops a turn on whichever of two thresholds trips first: the
existing `max_iterations` (tool-call count) or `max_turn_tokens`
(cumulative input+output tokens spent this turn). Both read from
`settings.yaml`'s `agent:` block (`agent.max_iterations`,
`agent.max_output_tokens`, `agent.max_turn_tokens`,
`agent.compaction_threshold`), with the same defaults Ruby ships (25 /
1024 / 60,000 / 0.85) when the block is absent — confirmed safe against
the repo's real `.boukensha/settings.yaml`, which has none of these keys
today.

### Reasoning/thinking normalization

Every backend now normalizes provider-specific "thinking" output into a
common `{"type": "reasoning", ...}` content block (see
`backends/base.py`'s module docstring for the full contract), so the
agent's reasoning is a first-class, loggable step regardless of provider:

- **Anthropic**: native `thinking`/`redacted_thinking` blocks, signature
  preserved for round-tripping (the API rejects a modified thinking block
  on a continued conversation).
- **Gemini**: `thought`/`thoughtSignature` parts; `thinkingConfig` added
  to every request (`{"thinkingBudget": 0}` for every model in the
  shipped table).
- **Ollama** / **Ollama Cloud**: `message["thinking"]`; `think: false`
  added to the request payload.

`Logger.reasoning`/`Logger.plan` log these as their own event types;
`Agent._log_reasoning` emits one `reasoning` event per block, skipping
empty non-redacted ones.

### The OpenAI backend now targets `/v1/responses`

gpt-5.x rejects `reasoning_effort` + tools on `/v1/chat/completions`
("Please use /v1/responses"), so the OpenAI backend migrated to the
Responses API. That changes more than the URL: messages become `input`
items, the system prompt becomes a top-level `instructions` string, tool
defs are flat (no `function:` wrapper), and tool results round-trip via
`function_call_output` items matched by `call_id` rather than a
`{"role": "tool"}` message.

### `boukensha.run` / `boukensha.start_repl` — `context_window=` keyword

```python
boukensha.start_repl(context_window=128_000)  # override for a smaller model
```

Defaults to `models.context_window(model)` when not given.

### `boukensha.mcp.Client` — stderr diagnostics on crash

If the spawned server dies before answering (bad interpreter, missing
dependency, an unhandled exception before its request loop starts), the
raised error now includes whatever the subprocess wrote to stderr, e.g.
`"server closed the connection — stderr: ModuleNotFoundError: ..."`
instead of a bare, undiagnosable `"server closed the connection"`.

### `Repl` — `/quiet` / `/loud` / `/clear` / `/compact`

`Repl` still doesn't hard-code `print()`/`input()`; `on_output`,
`handle_command`, `run_turn`, `banner()`, and the `logger`/`context`/
`model`/`version` properties are unchanged from step 11. `handle_command`
gains a `"/compact"` branch; `run_turn`'s constructed `Agent` now also
takes `max_turn_tokens`.

### `Logger.response` — cost/provider/model metadata

```json
{"phase": "response", "text": "...", "usage": {...}, "stop_reason": "end_turn", "provider": "anthropic", "model": "claude-haiku-4-5", "usage_unit": "tokens", "input_tokens": 1200, "output_tokens": 340, "cost_usd": 0.0029}
```

Unchanged in shape from step 11 — carried forward here since it's the
main consumer of the token-usage fix below.

## Run the demo

```bash
# Offline, no API key, no live MUD -- uses the daemon's built-in fake MUD:
python examples/mcp_mud_demo.py --dry

# One-shot demo:
python examples/example.py

# launches the Textual TUI:
BOUKENSHA_DIR=/path/to/.boukensha BOUKENSHA_PATH=~/Sites/boukensha/week1_baseline/python/12_context .venv/bin/boukensha

# plain REPL (no textual rendering, just print()/input()):
BOUKENSHA_PATH=~/Sites/boukensha/week1_baseline/python/12_context .venv/bin/boukensha --no-tui
```

```bash
./week1_baseline/bin/python/12_context
```

## Considerations

**A real bug in Ruby's own step 12, fixed rather than ported forward:
`Agent#record_usage`/`Logger#response` read `response["usage"]` directly,
with no fallback.** Only Anthropic's and OpenAI's (Responses API) raw HTTP
responses actually nest usage under a literal `"usage"` key. Gemini's raw
response uses `usageMetadata` (`promptTokenCount`/`candidatesTokenCount`);
Ollama/OllamaCloud's raw response has flat top-level `prompt_eval_count`/
`eval_count` fields, not nested under `"usage"` at all. As Ruby wrote it,
Gemini/Ollama/OllamaCloud sessions would silently show 0 context usage,
never auto-compact, and log no cost estimate — invisible in the shipped
`.boukensha/settings.yaml` fixture, which is pinned to `anthropic`. This
port's `Agent._normalize_usage` restores the union lookup (`"usage"` →
`"usageMetadata"` remapped → flat `prompt_eval_count`/`eval_count`
remapped → `{}`) that steps 10/11's Python `Agent` already had before this
step would otherwise have silently lost it by faithfully copying Ruby's
regression. Verified directly against fake responses shaped like all
three non-Anthropic providers (see this step's build history) — not
exercisable against the shipped fixture itself, since that's pinned to
Anthropic.

**`Config.provider_type()`/`Config.model()` are dead code, ported anyway.**
Ruby's step 12 adds these two methods, but no real code path calls
them — `Tasks::Base`/`Tasks::Player` (this port's `tasks/player.py`) still
resolve provider/model the old way via `task_settings`, unchanged from
step 11. The only caller is `Config.__repr__`'s debug string. The Ruby
step 12 README's claim that provider/model resolution "now goes through
Tasks::Base/Tasks::Player, restoring a bundled-default fallback" doesn't
match what the shipped Ruby code actually does — a stale doc claim, not a
stale-vs-current-code discrepancy this port introduced. Ported
`provider_type()`/`model()` into `config.py` faithfully anyway, matching
Ruby line-for-line, rather than silently dropping unused code.

**`Mcp::Client`'s Bundler-unbundled-env spawn fix has no Python
equivalent — not a missed port.** Ruby's step 12 wraps the MCP server
spawn in `Bundler.with_unbundled_env` so a server with its own Gemfile
doesn't inherit boukensha's `BUNDLE_GEMFILE`/`RUBYOPT`. There is no Python
analog of Bundler's `Process.spawn` monkey-patch that force-re-injects a
captured environment into every child process — `subprocess.Popen(env=...)`
already only passes exactly the environment dict it's given. The
stderr-diagnostics half of that same Ruby change *was* ported (see above);
only the Bundler-specific half doesn't apply.

**The `"turn_interrupted"` Tui event phase is ported but unreachable.**
Ruby's `Tui#handle_event` has a `"turn_interrupted"` branch for when
`Thread#raise(Interrupt)` actually lands after Esc. Step 11 already
established that Python has no safe equivalent — Esc is a documented
no-op — so `_run_turn_worker` never has an `Interrupt` to catch and never
emits this phase in Python. Kept the branch anyway, with a comment
explaining why it's dead, for structural parity with Ruby's own
`handle_event` rather than leaving an unexplained gap next to the
`"turn_error"` branch it sits beside.

**A pre-existing step-11 gap, fixed while touching this code: `Tui`'s
`_handle_event` never had a `"turn_error"` branch at all**, even though
`_run_turn_worker`'s `except` clause already emitted a `{"phase":
"turn_error", ...}` event. The state still recovered correctly (the
guaranteed `"turn_complete"` event in the `finally` block always fires
right after), but the error text itself was silently swallowed — never
shown in the conversation view. Ruby's own `handle_event` has always had
this branch. Added it here to match, verified via a headless pilot check
that emits a fake `turn_error` event and confirms it appears in the
conversation.

**Verified without spending live API budget on the parts that don't need
it.** `models.context_window`, `Context`'s compaction/usage-fraction
methods, `Config`'s new `agent_*` defaults, the `Agent._normalize_usage`
fix (against fake responses shaped like all four provider families), the
MCP client's stderr diagnostics (against a deliberately-crashing fake
server), and the Tui's colour-coding/compaction/turn_error event handling
(headless, via `Textual.run_test()` with a fake `Repl`/real `Context`)
were all confirmed this way. The one-shot config/servers comparison
against the real Ruby step 12 (`Config` repr, `mcp_servers` keys, API-key
presence) matches exactly, modulo the same cosmetic repr/boolean-casing
differences accepted since step 00.

**No committed Python test suite, consistent with every prior step's
policy** (see `python/10_standard_tool_library/README.md`'s Considerations
for the established precedent).
