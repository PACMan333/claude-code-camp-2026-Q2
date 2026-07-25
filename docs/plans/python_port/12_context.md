# Python Port Plan — Step 12: Context Management

## Scope

Ports `week1_baseline/ruby/12_context` to `week1_baseline/python/12_context`,
following the established copy-forward-not-diff convention: a full,
self-contained copy of the `boukensha` package as of this step, not a diff
layered on `python/11_tui`.

This is the largest step since the MCP rewrite. On top of the MCP-host tool
model and Textual TUI carried forward from step 11, step 12 adds real
context-window accounting (`Context` tracks `context_window` vs.
`current_tokens` separately, replacing a stale output-token-limit display),
a second per-turn circuit breaker (`max_turn_tokens`, alongside the existing
`max_iterations`), automatic + manual compaction, a new `Models` module for
per-model context-window lookup, provider-agnostic "reasoning" content
blocks (Anthropic thinking, Gemini thought, Ollama thinking) as a first-class
logged step, and a full migration of the OpenAI backend from
`/v1/chat/completions` to `/v1/responses` (gpt-5.x rejects `reasoning_effort`
+ tools on the old endpoint).

## Source files being ported (reference)

| Ruby source | Change | Python target |
|---|---|---|
| `Gemfile` / `boukensha.gemspec` | unchanged (new `gum` gem arrives transitively via `Gemfile.lock`, no direct line) | `requirements.txt` / `pyproject.toml` — no new dependency |
| `lib/boukensha/version.rb` | `0.11.1` → `0.12.0` | `boukensha/version.py` |
| `lib/boukensha/models.rb` | **new** — model → context_window table | `boukensha/models.py` (new) |
| `lib/boukensha/context.rb` | rewritten — drops `task`, adds context-window/compaction tracking | `boukensha/context.py` (rewrite) |
| `lib/boukensha/config.rb` | adds `agent_max_iterations`/`agent_max_output_tokens`/`agent_max_turn_tokens`/`agent_compaction_threshold`, and (unused) `provider_type`/`model` | `boukensha/config.py` (extend) |
| `lib/boukensha/agent.rb` | rewritten — drops `task_settings`, adds turn-token ceiling, compaction, reasoning/plan logging | `boukensha/agent.py` (rewrite) |
| `lib/boukensha/logger.rb` | adds `compaction`/`reasoning`/`plan` events, `context_window` on `prompt`, `tokens` on `turn_end` | `boukensha/logger.py` (extend) |
| `lib/boukensha/backends/base.rb` | doc-comment-only (normalized content-block contract) | `boukensha/backends/base.py` (comment only) |
| `lib/boukensha/backends/anthropic.rb` | adds thinking/redacted_thinking ↔ reasoning normalization; model table refresh | `boukensha/backends/anthropic.py` (extend) |
| `lib/boukensha/backends/openai.rb` | **migrated to Responses API** (`to_input` replaces `to_messages`, new payload/response shape); model table refresh | `boukensha/backends/openai.py` (rewrite) |
| `lib/boukensha/backends/gemini.rb` | adds `thinkingConfig`/`thought`/`thoughtSignature` reasoning support | `boukensha/backends/gemini.py` (extend) |
| `lib/boukensha/backends/ollama.rb` | adds `think: false`, `message["thinking"]` reasoning support | `boukensha/backends/ollama.py` (extend) |
| `lib/boukensha/backends/ollama_cloud.rb` | same as Ollama; model table reordered | `boukensha/backends/ollama_cloud.py` (extend) |
| `lib/boukensha/mcp/client.rb` | adds stderr diagnostics on unexpected EOF; Bundler-unbundled-env spawn fix (Ruby-only concern) | `boukensha/mcp/client.py` (extend: stderr diagnostics only) |
| `lib/boukensha/repl.rb` | adds `/compact` command; `max_turn_tokens` threaded through | `boukensha/repl.py` (extend) |
| `lib/boukensha/tui.rb` | adds context usage % + colour coding, `compaction` event handling | `boukensha/tui.py` (extend) |
| `lib/boukensha.rb` | `context_window:` kwarg, `Models.context_window` default, `Config#agent_*`-driven limits replace `task_settings` threading | `boukensha/__init__.py` (rewrite of `run`/`start_repl`) |
| `lib/boukensha_loader.rb` | unchanged | `boukensha_loader.py` — unchanged, copy forward |
| `bin/boukensha` | unchanged | `bin/boukensha` — unchanged, copy forward |
| `examples/example.rb` | comment-only (step number) | `examples/example.py` (comment only) |
| `examples/mcp_mud_demo.rb` | `Context.new` call site updated for dropped `task:` | `examples/mcp_mud_demo.py` (update call site) |
| `patches/bubbletea/*` | unchanged | N/A — Ruby-only (native gem patch) |
| `tool.rb`, `message.rb`, `errors.rb`, `registry.rb`, `run_dsl.rb`, `client.rb`, `tasks/*`, `prompt_builder.rb` (comment-only) | unchanged | copy forward unchanged from `python/11_tui` |

## Target layout

```
week1_baseline/python/12_context/
├── requirements.txt
├── pyproject.toml
├── bin/boukensha
├── boukensha_loader.py
├── examples/
│   ├── example.py
│   └── mcp_mud_demo.py
├── prompts/system.md
└── boukensha/
    ├── __init__.py
    ├── version.py            # "0.12.0"
    ├── models.py              # new
    ├── config.py
    ├── context.py
    ├── message.py
    ├── tool.py
    ├── errors.py
    ├── registry.py
    ├── run_dsl.py
    ├── prompt_builder.py
    ├── client.py
    ├── logger.py
    ├── agent.py
    ├── repl.py
    ├── tui.py
    ├── backends/
    │   ├── base.py
    │   ├── anthropic.py
    │   ├── openai.py
    │   ├── gemini.py
    │   ├── ollama.py
    │   └── ollama_cloud.py
    ├── mcp/client.py
    └── tools/mcp.py
```

## Ruby → Python design mapping

### `Context` — token/compaction tracking, `task` dropped

Ruby drops `task` from `Context` entirely (provider/model/task-name
resolution moved out to the `boukensha.rb` call sites, which already have
`task_class`/`task_settings` in scope) and adds:

- `context_window` (read-only, set at construction from `Models.context_window(model)`)
- `current_tokens` — **mutable** (Ruby: `attr_accessor`). This is a real
  deviation from this port's established "`@property` getters only, no
  setters" convention (settled for `Context` back in step 01) — but that
  convention mirrored Ruby's own all-`attr_reader` shape, and Ruby's own
  step-12 source now has a genuine `attr_accessor` here. Python: a plain
  public attribute (`self.current_tokens`), not a property — there's
  nothing to guard, Ruby doesn't either.
- `turn_tokens` (read-only) / `reset_turn_tokens()` / `add_turn_tokens(input, output)`
- `compaction_threshold` (read-only, defaults `0.85`)
- `usage_fraction()` / `usage_pct()` — derived from `current_tokens / context_window`
- `needs_compaction(threshold=None)` — Ruby's `threshold: compaction_threshold`
  (a self-referential keyword default) becomes the established
  None-sentinel-plus-lazy-default idiom: `threshold = self.compaction_threshold if threshold is None else threshold`.
- `compact_messages(target_fraction=0.60)` — Ruby's bang (`compact_messages!`)
  drops the `!` per the established bang-method convention. Drops the
  oldest 40% of messages (keeping ≥ 2), resets `current_tokens` to 0,
  returns the drop count.
- `clear_messages()` (already un-banged from step 08) now also resets
  `current_tokens` to 0, matching Ruby's `clear_messages!`.
- `__str__`/`to_s` drops `task=`, adds `window=`/`current=`.

`update_tokens(n)` sets `current_tokens = int(n)` — called by `Agent` after
every response, not just at turn end.

### `boukensha.models` — new module

Ruby's `Models::BACKEND_CLASSES` is a lazy `-> { [...] }` lambda specifically
to dodge `require`-order issues (the table must not be built until every
backend file has actually loaded). Python's `__init__.py` already imports
every backend module explicitly, in order, before anything could call
`models.context_window(...)` — so the lazy-lambda workaround is pure
Ruby-idiom scaffolding with nothing to port; `models.py` builds its table
once at import time, directly:

```python
from .backends.anthropic import Anthropic
from .backends.openai import OpenAI
from .backends.gemini import Gemini
from .backends.ollama import Ollama
from .backends.ollama_cloud import OllamaCloud

DEFAULT_CONTEXT_WINDOW = 32_000

_BACKEND_CLASSES = [Anthropic, OpenAI, Gemini, Ollama, OllamaCloud]

def _table():
    table = {}
    for backend in _BACKEND_CLASSES:
        table.update(backend.MODELS)
    return table

_TABLE = _table()

def context_window(model: str) -> int:
    return _TABLE.get(str(model), {}).get("context_window", DEFAULT_CONTEXT_WINDOW)
```

Building `_TABLE` once at import time (not lazily memoized per-call like
Ruby's `@table ||=`) is safe here specifically because of the import-order
guarantee above — worth a one-line comment so a future step doesn't "fix" it
back into a lazy-eval pattern for no reason.

### `Config` — new `agent_*` methods, and two admittedly dead ones

`agent_max_iterations` / `agent_max_output_tokens` / `agent_max_turn_tokens`
/ `agent_compaction_threshold` read a new, optional `settings.yaml` `agent:`
block, each with the same numeric default Ruby ships (25 / 1024 / 60,000 /
0.85) when the block or key is absent — confirmed safe against the repo's
real `.boukensha/settings.yaml`, which has no `agent:` block today.

**Resolved (dead-code question):** `Config#provider_type`/`Config#model`
are new in Ruby's step 12 but are never called by any real code path —
`Tasks::Base`/`Tasks::Player` still resolve provider/model the old way via
`task_settings` in `boukensha.rb`, unchanged from step 11. The step 12
README's claim that resolution "now goes through Tasks::Base/Tasks::Player,
restoring a bundled-default fallback" doesn't match what's actually wired up
in this snapshot — a stale doc claim, not a stale-vs-current-code
discrepancy. **Decision: port `provider_type()`/`model()` into `config.py`
faithfully anyway**, matching Ruby line-for-line even though nothing calls
them except `__repr__` — note the stale README claim in the Python README's
Considerations section rather than silently dropping dead code.

### `Agent` — restructured, `task_settings` dropped, new limits/logging

Mirrors Ruby's `agent.rb` directly:

- Constructor drops `task_settings`; takes `max_iterations`/`max_turn_tokens`/
  `max_output_tokens` directly (each already resolved by the caller —
  `boukensha.rb`'s `Config#agent_*` methods — before construction). Python's
  `_resolve_max_iterations`/`_resolve_max_output_tokens` helpers (which read
  `task_settings`/`context.task`) are deleted; replaced by a plain
  `int(max_iterations or MAX_ITERATIONS)` / `max_turn_tokens or 0` /
  `max_output_tokens` (as-is, may be `None`).
- `run()` calls `self._context.reset_turn_tokens()` and
  `self._compact_if_needed()` before the loop starts.
- Two independent stop conditions checked each iteration:
  `_iteration_limit_reached()` (unchanged) and a new `_token_limit_reached()`
  (`max_turn_tokens > 0 and context.turn_tokens >= max_turn_tokens`) — either
  one triggers `wrap_up(reason)`.
- `_logger.prompt(...)` gains `context_window=self._context.context_window`.
- After every response (including mid-turn tool-use calls): `_record_usage(response)`
  updates both `turn_tokens` (spend budget) and `current_tokens` (context
  pressure) — see the Open Questions resolution below for the exact
  normalization logic, since Ruby's own version of this method has a real
  bug for non-Anthropic-shaped responses.
- `_log_reasoning(content)` — new. Emits one `logger.reasoning(text=, redacted=)`
  event per `"type": "reasoning"` block in the parsed content, skipping
  empty non-redacted blocks.
- `_handle_tool_calls` — the "preamble" text accompanying a tool call is now
  logged as its own `logger.plan(text=...)` event (previously folded into
  the placeholder `response` event as its `text`); the placeholder
  `response` event itself is unconditional now, always
  `"(tool use — N calls)"`, never the preamble text.
- `_wrap_up` — same `ApiError`-rescue shape as step 11, now also calls
  `_record_usage`/passes `tokens=self._context.turn_tokens` to `turn_end`.
- `task=None` is now passed explicitly to every `logger.response(...)` call
  (Ruby: `task: nil`, always — `Agent` has no way to know the task anymore
  since `Context` dropped it).

**Resolved (usage-normalization bug):** Ruby's `record_usage`/the
`@logger.response(usage: response["usage"], ...)` call sites read
`response["usage"]` **directly**, with no fallback — but only
Anthropic's and OpenAI's (Responses API) raw HTTP responses actually nest
usage under a literal `"usage"` key. Gemini's raw response uses
`usageMetadata` (`promptTokenCount`/`candidatesTokenCount`); Ollama/
OllamaCloud's raw response has flat top-level `prompt_eval_count`/
`eval_count` fields, not nested under `"usage"` at all. The Ruby source's
`Logger#usage_tokens` *does* still have the full fallback-key list
(`prompt_tokens`, `promptTokenCount`, `prompt_eval_count`, etc.) — but that
logic never gets a chance to run, because `usage` is already `nil`/`{}` by
the time it gets there for those three backends. Net effect in Ruby as
written: Gemini/Ollama/OllamaCloud sessions silently show 0 context usage,
never auto-compact, and log no cost estimate — invisible in the shipped
`.boukensha/settings.yaml` fixture, which is pinned to `anthropic`.

**Decision: fix it in the Python port.** A private `_normalize_usage(response)`
helper restores the union Anthropic/OpenAI (`response["usage"]`) →
Gemini (`response["usageMetadata"]`, remapped to `input_tokens`/`output_tokens`)
→ Ollama-shaped flat keys (`prompt_eval_count`/`eval_count`, remapped the
same way) → `{}`, and both `_record_usage` and every `logger.response(...)`
call site use its result instead of raw `response["usage"]`/`response.get("usage")`.
This restores exactly what steps 10/11's Python `Agent._normalized_usage`
already did — a capability this port already had and Ruby's step 12 rewrite
happens to have dropped. Note this fix explicitly in the ported README's
Considerations section (this is a case of the Python port being *more*
correct than the Ruby lesson it's based on, which is worth calling out
plainly, not quietly).

### `Logger` — new event types

`compaction(before:, dropped:, context_window:)`, `reasoning(text:, redacted:)`,
`plan(text:)` are new methods, each a thin `write_log(phase=..., ...)` call,
directly portable. `prompt(...)` gains `context_window`; `turn_end(...)`
gains an optional `tokens=None` parameter.

### Backends — reasoning normalization (all five) + OpenAI's Responses API migration

Every backend's `parse_response` now maps provider-native "thinking" output
into the common `{"type": "reasoning", "text": ..., "signature": ..., "redacted": ...}`
block shape documented in `Backends::Base`'s docstring (already ported
verbatim into `backends/base.py` as a comment, per step 11's precedent of
keeping the normalized-response-contract docs in the base class):

- **Anthropic**: native `thinking` (`{"text": block["thinking"], "signature": ...}`)
  and `redacted_thinking` (`{"text": "", "redacted": True, "signature": block["data"]}`)
  blocks, normalized by a new `_normalize_block`/denormalized by
  `_assistant_content`/`_denormalize_block` (the inverse, for round-tripping
  signatures back to the API on the next turn — Anthropic rejects a modified
  thinking block on a continued conversation).
- **Gemini**: `part["thought"]` → `{"type": "reasoning", "text": part["text"], "signature": part["thoughtSignature"]}`;
  `thinkingConfig` added to `generationConfig` (`{"thinkingBudget": 0}` for
  every model in the shipped table — `gemini-3.1-pro-preview-customtools` is
  commented out in Ruby's own `MODELS` table, so its `thinkingLevel: "LOW"`
  branch in `thinking_config` is currently unreachable dead code; port it
  as-is as a straight translation, matching Ruby exactly, since it costs
  nothing and the table entry could come back).
- **Ollama** / **OllamaCloud**: `message["thinking"]` → a reasoning block if
  non-empty; `think: false` added to the request payload (explicitly
  disabling thinking mode server-side, distinct from the block-normalization
  path, which handles whatever comes back regardless).
- **OpenAI**: rewritten to target `/v1/responses` instead of
  `/v1/chat/completions` — gpt-5.x rejects `reasoning_effort` + tools on the
  chat-completions endpoint. This isn't a stylistic reasoning-block addition
  like the other four backends, it's a full request/response shape change:
  - `to_messages(system, messages)` → `to_input(messages)`: no more a
    `{"role": "system", ...}` message prepended to the list — `system`
    becomes a top-level `instructions:` string in the payload instead.
  - Tool result messages become `{"type": "function_call_output", "call_id":, "output":}`
    items (matched by `call_id`), not a `{"role": "tool", "tool_call_id":}` message.
  - Tool defs are flat (`{"type": "function", "name":, "description":, "parameters":}`),
    no `function:` wrapper.
  - `parse_response` reads `response["output"]` (a list of typed items —
    `"reasoning"`, `"message"`, `"function_call"`), not
    `response["choices"][0]["message"]`.
  - `_assistant_items` (the inverse of `parse_response`, rebuilding request
    items from stored assistant turns) drops reasoning blocks entirely when
    re-emitting — gpt-5.x doesn't need them echoed back when
    `reasoning: {"effort": "none"}` is set on every call.
  - Model table refresh: `gpt-5.4` removed, `gpt-5.4-nano` added (alongside
    existing `gpt-5.5`/`gpt-5.4-mini`) — a content update, not a structural
    one; port the table Ruby ships, not the one step 11 had.

### `Mcp::Client` — stderr diagnostics ported; Bundler-unbundling is N/A

Ruby's step 12 adds two things to `Mcp::Client`: (1) `spawn_unbundled`,
wrapping the subprocess spawn in `Bundler.with_unbundled_env` so a spawned
MCP server with its own, different Gemfile doesn't inherit boukensha's
`BUNDLE_GEMFILE`/`RUBYOPT`; (2) `stderr_detail`, draining the child's stderr
on an unexpected EOF so a crash during spawn/handshake is diagnosable
instead of a bare "server closed the connection".

**(1) doesn't apply to Python at all** — there is no Python analog of
Bundler's `Process.spawn` monkey-patch that force-re-injects a captured
environment into every child process; `subprocess.Popen(env=merged_env)`
already only passes exactly the environment dict it's given, with no
hidden re-injection to work around. Nothing to port; noted here so it
doesn't read as a missed item.

**(2) is a genuine, worth-having robustness improvement, ported directly**:
`mcp/client.py`'s `_read_until` raises with an added `_stderr_detail()`
suffix on EOF — read whatever's buffered on `self._process.stderr` (after
`self._process.wait()`, matching Ruby's "reap first, then read stderr fully
flushed" ordering) and append it to the error message if non-empty.

### `Repl` — `/compact` command

`handle_command` gains a `"/compact"` branch: calls
`self._context.compact_messages()`, outputs
`"(compacted context — {} messages dropped)".format(dropped)`, returns
`"command"`. `HELP`/`banner()` text gains the `/compact` line. `run_turn`
passes `max_turn_tokens=self._max_turn_tokens` through to `Agent`
(constructor gains a matching `max_turn_tokens=None` parameter).

### `Tui` — context usage colour coding, new event phases

- `_render_progress`/`_render_status` (idle branch) now compute
  `pct = self._ctx.usage_pct()`, `used = fmt_tokens(self._ctx.current_tokens)`,
  `max = fmt_tokens(self._ctx.context_window)`, and colour the ready-state
  line by threshold (`< 70%` grey, `70–84%` yellow, `≥ 85%` red — matching
  Ruby's `CTX_WARN_PCT`/`CTX_ALERT_PCT`). Textual's `Static` widgets happily
  render Rich markup passed to `.update(...)` (the conversation `RichLog`
  is the only widget with `markup=False`, set for a different reason in
  step 11 — unaffected here), so colour is applied the same way Ruby's
  `lip(color).render(...)` does: wrap the rendered string in
  `"[red]...[/red]"`/`"[yellow]...[/yellow]"`/`"[grey53]...[/grey53]"`
  Rich markup tags rather than introducing Textual CSS classes toggled at
  runtime — simpler, and there's no static/dynamic split to manage since
  the whole line is rebuilt from scratch every tick regardless.
- Status bar gains a `⚠` indicator at ≥ 85%, same threshold.
- `_handle_event` gains a `"compaction"` phase: appends
  `"[context compacted — {} messages dropped to free space]".format(dropped)`
  to the conversation log and sets the dirty flag.
- Ruby's `handle_event` also has `"turn_interrupted"` (from
  `Thread#raise(Interrupt)` actually landing) and `"turn_error"` phases.
  step 11's Python port already established that `Thread#raise(Interrupt)`
  has no safe Python equivalent — Esc is a documented no-op — so
  `"turn_interrupted"` can never actually fire from `_run_turn_worker` in
  this port. Port the branch anyway (a one-line no-op-safe append, matching
  Ruby's shape) with a comment explaining it's unreachable given the
  established Esc resolution, rather than silently dropping a phase Ruby
  handles — cheap to keep, and it documents *why* it's dead instead of
  leaving a mysterious gap next to `"turn_error"` (which Python already
  emits, unchanged since step 11).

### `boukensha/__init__.py` — `context_window=` kwarg, `Config#agent_*`-driven limits

`run`/`start_repl` both gain a `context_window=None` keyword, defaulting
via `context_window = context_window or models.context_window(model)`
(after `model` is resolved, same as Ruby's `context_window ||= Models.context_window(model)`
ordering). `Context(...)` construction adds `context_window=`/
`compaction_threshold=cfg.agent_compaction_threshold()`. `Logger`'s snapshot
and `Agent(...)`/`Repl(...)` construction both switch from
`task_class.max_iterations(task_settings)`/`task_class.max_output_tokens(task_settings)`
to `cfg.agent_max_iterations()`/`cfg.agent_max_turn_tokens()`/
`(max_output_tokens or cfg.agent_max_output_tokens())` — `task_settings` is
no longer threaded into `Agent`/`Repl` at all, matching the `Context`/`Agent`
API changes above.

## Config directory & schema

`.boukensha/settings.yaml`'s resolution order and schema are unchanged from
step 11, plus one new **optional** top-level block, matched exactly to
Ruby's `Config#agent_*` defaults:

```yaml
agent:
  max_iterations: 25          # default when absent
  max_output_tokens: 1024     # default when absent
  max_turn_tokens: 60000      # default when absent
  compaction_threshold: 0.85  # default when absent
```

The repo's real `.boukensha/settings.yaml` has no `agent:` block today —
confirmed safe (falls back to defaults, doesn't raise) during this session's
`12_context_mcp_delta.md` investigation of the Ruby side. Not modified as
part of this port; it's a shared, real fixture.

## Task list

1. Scaffold `python/12_context/` as a full copy of `python/11_tui`'s tree.
2. `boukensha/version.py` → `"0.12.0"`.
3. Write `boukensha/models.py` (new file, per the design mapping above).
4. Rewrite `boukensha/context.py`: drop `task`; add `context_window`,
   mutable `current_tokens`, `turn_tokens`, `compaction_threshold`,
   `update_tokens`, `reset_turn_tokens`, `add_turn_tokens`, `usage_fraction`,
   `usage_pct`, `needs_compaction`, `compact_messages`; update
   `clear_messages`/`__str__`.
5. Extend `boukensha/config.py`: add `agent_max_iterations`/
   `agent_max_output_tokens`/`agent_max_turn_tokens`/`agent_compaction_threshold`,
   and (per the resolved dead-code question) `provider_type`/`model`; update
   `__repr__`.
6. Rewrite `boukensha/agent.py` per the design mapping: drop
   `task_settings`/`_resolve_max_iterations`/`_resolve_max_output_tokens`;
   add `max_turn_tokens`, `_token_limit_reached`, `_record_usage` (with the
   `_normalize_usage` fix), `_compact_if_needed`, `_log_reasoning`; update
   `_handle_tool_calls` for the new `plan` event; `task=None` on every
   `logger.response(...)` call.
7. Extend `boukensha/logger.py`: `compaction`/`reasoning`/`plan` methods;
   `context_window` on `prompt`; `tokens=None` on `turn_end`.
8. Extend all five `boukensha/backends/*.py` per the design mapping —
   reasoning-block normalization for Anthropic/Gemini/Ollama/OllamaCloud;
   full Responses-API rewrite for OpenAI; refreshed `MODELS` tables on all
   five to match Ruby's current content exactly.
9. Extend `boukensha/mcp/client.py`: stderr-diagnostics on EOF (skip the
   Bundler-unbundling equivalent — N/A for Python, per the design mapping).
10. Extend `boukensha/repl.py`: `/compact` command, `max_turn_tokens`
    threading, updated `HELP`/`banner()` text.
11. Extend `boukensha/tui.py`: context usage %/colour coding on the
    progress and status lines, `"compaction"` event handling, a
    documented-unreachable `"turn_interrupted"` branch.
12. Rewrite the relevant parts of `boukensha/__init__.py`: `context_window=`
    kwarg on `run`/`start_repl`, `Config#agent_*`-driven limits replacing
    `task_settings` threading into `Context`/`Agent`/`Repl`/`Logger` snapshot.
13. Update `examples/mcp_mud_demo.py`'s `Context(...)` call site (drop
    `task=`); `examples/example.py` comment-only step-number update.
14. Copy forward unchanged: `tool.py`, `message.py`, `errors.py`,
    `registry.py`, `run_dsl.py`, `client.py`, `tasks/*`, `prompt_builder.py`
    (comment-only change, safe to treat as unchanged), `boukensha_loader.py`,
    `bin/boukensha`.
15. `requirements.txt`/`pyproject.toml`: no new dependency; bump the
    `description` field only.
16. Install editable into the shared root `.venv`; confirm the runner
    script (`week1_baseline/bin/python/12_context`) is executable.
17. Verify offline first: exercise `Context`'s new compaction/usage-pct
    methods and `models.context_window(...)` directly
    (`.venv/bin/python -c "..."`), and the `Mcp::Client`-equivalent stderr
    diagnostics against a deliberately-broken command (e.g. a nonexistent
    binary) before touching anything live. Headless-verify `Tui`'s new
    colour-coding/compaction event via the same `Textual.run_test()` pilot
    pattern step 11 already established, with a fake `Repl`/`Context`
    double driving `usage_pct` past each threshold.
18. Per the live/paid-verification policy: only after the above, ask before
    spending real budget on one live turn (through both the plain REPL and
    the TUI) to confirm reasoning-block round-tripping and real
    token/cost/compaction numbers against the actual Anthropic backend the
    fixture is pinned to. The Gemini/Ollama/OllamaCloud usage-normalization
    fix (task 6) cannot be exercised against the shipped fixture at all
    (it's pinned to Anthropic) — note this as a known verification gap
    rather than silently claiming full coverage; exercising it would need
    either a temporary config override or a mocked HTTP response shaped
    like each provider's real payload.
19. Diff both runners' one-shot (`example.py`/`.rb`) output against the
    same fixture — expect only the established cosmetic-diff classes.
20. Port the README, including a Considerations section documenting: the
    usage-normalization fix (Python is more correct here than the Ruby
    source it's based on), the preserved-but-dead `provider_type`/`model`
    Config methods and the stale README claim about them, the `gum` gem
    flag carried over from the `12_context_mcp_delta.md` delta plan (not
    re-litigated here, just referenced), and the unreachable
    `turn_interrupted` Tui branch.
21. Don't commit.

## Open questions

1. **Usage-key normalization bug in `Agent#record_usage`/`Logger#response`
   (Gemini/Ollama/OllamaCloud silently show 0 context usage and never
   auto-compact).** Resolved: **fix it in Python** — restore a
   `_normalize_usage` helper unifying `"usage"` / `"usageMetadata"` / flat
   `prompt_eval_count`+`eval_count` shapes, matching what steps 10/11's
   Python `Agent` already had before this port would otherwise silently
   lose it by faithfully copying Ruby's regression. Documented in the
   ported README as a case of the port being more correct than the lesson
   it's based on.
2. **`Config#provider_type`/`Config#model` are dead code (never called
   except by `__repr__`), and the README's claim about what they enable
   doesn't match the shipped code.** Resolved: **port them faithfully**
   anyway, matching Ruby line-for-line; note the stale README claim in the
   Python README's Considerations rather than silently dropping unused
   code or silently "fixing" the README's inaccurate claim about the
   Ruby lesson.
