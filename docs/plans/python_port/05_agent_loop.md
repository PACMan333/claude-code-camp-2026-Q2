# Python Port Plan — Step 05: The Agent Loop

## Scope

Port `week1_baseline/ruby/05_agent_loop` to a new
`week1_baseline/python/05_agent_loop`. Same as steps 00–04, this is a
self-contained copy of the `boukensha` package at this point in its
history (mirroring Ruby's per-step-folder duplication), not a diff against
`python/04_api_client`.

The runner already exists and defines the contract:
`week1_baseline/bin/python/05_agent_loop` does

```bash
cd week1_baseline/python/05_agent_loop
"$REPO_ROOT/.venv/bin/python" examples/example.py
```

— same shared repo-root `.venv` as steps 00–04.

**This step adds the core agentic loop** (`Boukensha::Agent`): it calls the
API, checks `stop_reason`, dispatches tool calls back through the
`Registry`, appends results to the `Context`, and repeats until
`end_turn` or an iteration ceiling is hit (followed by one tools-disabled
wind-down call). All five backends (Anthropic, OpenAI, Gemini, Ollama,
Ollama Cloud) gain a `parse_response` method that normalizes their raw
reply into one common `{stop_reason:, content:}` shape, so `Agent` never
has to know which provider it's talking to.

**Like step 04, this step's `Client` makes real, live, billed HTTP calls**
— and now potentially several per turn (up to `max_iterations`, default
25, plus one wind-down call), not just one. Per discussion with the user:
no live run happens during planning (this plan was written from source
reading alone); verification during the execute phase must first exercise
the loop end-to-end against a local mock HTTP server (multi-tool-call
turn, the wind-down/`max_iterations` path, and the exhausted-retries path
carried over from step 04) before spending any of the live budget, and the
one live run that follows should be a single bounded turn, not a repeated
comparison loop.

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `Gemfile` | unchanged from step 04 (`dotenv` only) | `requirements.txt` (unchanged) |
| `lib/boukensha.rb` | **changed** — adds `require_relative "boukensha/agent"` | `boukensha/__init__.py` — adds `Agent` and `LoopError` to exports |
| `lib/boukensha/agent.rb` | **new** — `Boukensha::Agent`: the loop, iteration ceiling, tool dispatch, wind-down call | `boukensha/agent.py` — new `Agent` class |
| `lib/boukensha/errors.rb` | **changed** — adds `LoopError < StandardError` | `boukensha/errors.py` — add `class LoopError(Exception): pass` (see design mapping — defined but never raised, in Ruby too) |
| `lib/boukensha/config.rb` | **changed** — (a) `PROMPTS_DIR` regressed from `"../../prompts"` to `"../../../prompts"`, a genuine off-by-one that now resolves to a nonexistent directory; fixture-masked, see design mapping; (b) four one-line `mud_*` readers rewritten to Ruby 3.x endless-method syntax (`def mud_host = ...`), purely cosmetic, no Ruby behavior change | `boukensha/config.py` — **no change** (see design mapping: Python's `PROMPTS_DIR` was never computed the way Ruby's is, so it was never subject to this regression) |
| `lib/boukensha/tasks/base.rb` | **changed** — adds `DEFAULT_MAX_ITERATIONS = 25`, `DEFAULT_MAX_OUTPUT_TOKENS = 1024`, `self.max_iterations(settings)`, `self.max_output_tokens(settings)`, and a private `integer_setting` helper | `boukensha/tasks/base.py` — add the same two class constants, two classmethods, and a private `_integer_setting` helper |
| `lib/boukensha/tasks/player.rb` | byte-identical to step 04 (`diff` confirmed) | copy forward unchanged from `python/04_api_client` |
| `lib/boukensha/client.rb` | **changed** — `call` gains a `tools:` keyword, threaded into `to_api_payload` | `boukensha/client.py` — add `tools=None` keyword to `call`, threaded into `to_api_payload` |
| `lib/boukensha/prompt_builder.rb` | **changed** — `to_api_payload` gains `tools:`; adds `parse_response(response)` delegating to the backend | `boukensha/prompt_builder.py` — same two changes |
| `lib/boukensha/backends/base.rb` | byte-identical to step 04 (`diff` confirmed) | copy forward unchanged from `python/04_api_client` |
| `lib/boukensha/backends/anthropic.rb` | **changed** — `to_payload` accepts `tools:` (used verbatim if non-nil, else computed); adds `parse_response` | `boukensha/backends/anthropic.py` — same two changes |
| `lib/boukensha/backends/gemini.rb` | **changed** — same `tools:`/`parse_response` additions as anthropic, plus `to_messages`' existing `:assistant` branch now calls a new private `assistant_parts` (was inline `[{text: msg.content}]`) | `boukensha/backends/gemini.py` — same, plus a new `_assistant_parts` helper |
| `lib/boukensha/backends/ollama.rb` | **changed** — same `tools:`/`parse_response` additions, plus a new `:assistant` branch in `to_messages` (didn't have one before — fell through to the generic `else`) calling a new private `assistant_message` | `boukensha/backends/ollama.py` — same, plus a new `_assistant_message` helper |
| `lib/boukensha/backends/ollama_cloud.rb` | **changed** — identical shape of change to `ollama.rb` | `boukensha/backends/ollama_cloud.py` — same |
| `lib/boukensha/backends/openai.rb` | **changed** — same shape of change as `ollama.rb`, plus `require "json"` (used by `parse_response`'s `JSON.parse` and `assistant_message`'s `.to_json`) | `boukensha/backends/openai.py` — same, plus `import json` |
| `lib/boukensha/context.rb`, `tool.rb`, `message.rb`, `registry.rb` | byte-identical to step 04 (`diff` confirmed) — the Ruby README's own "Updated Files" table claims `context.rb` changed this step ("carries the active task object..."), but `Context` has held `task` since step 04; that table entry is stale, same pattern as prior steps' stale doc tables | copy forward unchanged from `python/04_api_client` |
| `prompts/system.md` | byte-identical to step 04 (`diff` confirmed) | copy forward unchanged |
| `examples/example.rb` | Builds `Config` → `Context` → `Registry` → backend → `PromptBuilder` → `Client` → `Agent`; registers `read_file`/`list_directory` tools resolved against a `base_dir` (new — step 04 resolved tool paths against cwd, step 05 resolves against the step folder explicitly); asks the agent to read and summarize `README.md`; prints config/provider/model/max_iterations/max_output_tokens; calls `agent.run` and prints the final response | `examples/example.py` — same shape |
| `README.md` | New Files / Updated Files tables (some entries stale — see design mapping), loop diagram, normalized-response-shape explainer, task configuration table, Considerations | `README.md` — adapted, with the stale-table issue not propagated |

Runner already in place, no change needed: `week1_baseline/bin/python/05_agent_loop`
(verify it's executable; `chmod +x` if not — missing at least twice before,
steps 03 and possibly others).

## Target layout

```
week1_baseline/python/05_agent_loop/
  requirements.txt
  pyproject.toml
  prompts/
    system.md                      # copied forward unchanged
  boukensha/
    __init__.py                    # adds Agent, LoopError to exports
    config.py                      # copied forward unchanged
    tool.py                        # copied forward unchanged
    message.py                     # copied forward unchanged
    context.py                     # copied forward unchanged
    errors.py                      # adds LoopError
    registry.py                    # copied forward unchanged
    prompt_builder.py               # adds tools=None, parse_response
    client.py                      # adds tools=None
    agent.py                       # new
    tasks/
      __init__.py
      base.py                      # adds max_iterations/max_output_tokens
      player.py                    # copied forward unchanged
    backends/
      __init__.py
      base.py                      # copied forward unchanged
      anthropic.py                 # adds tools param, parse_response
      ollama.py                    # adds tools param, parse_response, _assistant_message
      ollama_cloud.py               # same as ollama.py
      openai.py                    # same as ollama.py (+ json import)
      gemini.py                    # adds tools param, parse_response, _assistant_parts
  examples/
    example.py
  README.md
```

## Ruby → Python design mapping

- **`Boukensha::Agent` → a plain `Agent` class, not a dataclass.** It's a
  stateful controller (mutable `@iteration` counter across calls to
  `run`), matching Ruby's plain `class` with instance state — same
  treatment `Client` already got in step 04 (per that step's design
  mapping: "known wrinkle, mirror it, don't make it stateless"). Public
  surface is just `__init__` and `run`; every Ruby `private` method
  becomes a leading-underscore method (`_resolve_max_iterations`,
  `_resolve_max_output_tokens`, `_iteration_limit_reached`, `_call_opts`,
  `_wrap_up`, `_fallback_message`, `_extract_text`, `_handle_tool_calls`).
  Constructor keywords match Ruby's keyword-only args exactly:
  `Agent(*, context, registry, builder, client, task_settings=None, max_iterations=None, max_output_tokens=None)`.

- **Two independent "25" constants, not a naming collision.**
  `Agent.MAX_ITERATIONS = 25` (this step) and
  `Tasks.Base.DEFAULT_MAX_ITERATIONS = 25` (also this step) are separate
  constants on separate classes that happen to share a value. In the
  shipped example, `Agent` is always constructed with `task_settings=player_settings`
  and `Player` always responds to `max_iterations`, so
  `Agent.MAX_ITERATIONS` is a standalone fallback for the case where
  `Agent` is built *without* `task_settings` — not the value actually in
  effect when the example runs (that's `Tasks.Base.DEFAULT_MAX_ITERATIONS`,
  since `.boukensha/settings.yaml` doesn't set `max_iterations` either).
  Keep both constants distinct, matching Ruby; don't consolidate them.

- **`respond_to?(:max_iterations)` → `hasattr(task, "max_iterations")`.**
  Ruby's `@context.task.respond_to?(:max_iterations)` is a runtime duck-type
  check (a task class might not define it); Python's `hasattr` is the
  direct equivalent, used in both `_resolve_max_iterations` and
  `_resolve_max_output_tokens`.

- **`explicit.to_i` → `int(explicit)`.** Ruby coerces the constructor's
  `max_iterations:` arg to an integer even when explicitly passed (in case
  a caller passes a string or float); Python does the same with `int()`.
  `max_output_tokens:` has no such coercion in Ruby (passed through as-is
  when explicit), so neither does the Python port.

- **`@builder.parse_response(response)` → `self._builder.parse_response(response)`,
  delegating straight to `self._backend.parse_response(response)`** — a
  one-line passthrough added to `PromptBuilder`/`prompt_builder.py`,
  mirroring the existing `headers`/`url` passthrough pattern already there.

- **`tools:` threads through three layers unchanged in shape**:
  `Client.call(tools=None)` → `PromptBuilder.to_api_payload(tools=None)` →
  `Backend.to_payload(context, tools=None)`. Every backend's `to_payload`
  uses the explicit value when given, else computes its own:
  `tools if tools is not None else self.to_tools(context.tools)` (Ruby:
  `tools.nil? ? to_tools(context.tools) : tools`). This is what lets
  `Agent._wrap_up` pass `tools=[]` to disable tool use for the wind-down
  call without needing a different code path.

- **Every backend gains `parse_response(self, response)`, converting its
  raw reply into one shared normalized shape**:
  `{"stop_reason": "tool_use" | "end_turn", "content": [...]}`, where each
  content block is either `{"type": "text", "text": ...}` or
  `{"type": "tool_use", "id": ..., "name": ..., "input": {...}}`. This is
  a direct per-backend translation of the Ruby methods, using the same
  `dict.get(...)` / safe-navigation idioms already used elsewhere in each
  backend file (`response.dig("candidates", 0, ...)` → guard against an
  empty list before indexing `[0]`, since Python has no `dig` that
  short-circuits on a missing index the way Ruby's does):
  - **Anthropic**: `stop_reason = "tool_use" if response.get("stop_reason") == "tool_use" else "end_turn"`;
    `content = response.get("content") or []`. No reverse conversion needed
    — Anthropic's `content` array already doubles as the wire format (see
    below).
  - **OpenAI**: `choices = response.get("choices") or []`;
    `message = choices[0].get("message", {}) if choices else {}`;
    `tool_calls = message.get("tool_calls") or []`; text block appended
    only if `message.get("content")` is truthy; each tool call becomes
    `{"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"], "input": json.loads(tc["function"].get("arguments") or "{}")}`.
  - **Gemini**: `candidates = response.get("candidates") or []`;
    `parts = candidates[0].get("content", {}).get("parts", []) if candidates else []`;
    walk `parts`, appending a text block for `part.get("text")` and a
    tool_use block for `part.get("functionCall")` (reusing the function
    `name` as `id`, since Gemini doesn't assign call ids).
  - **Ollama / Ollama Cloud**: `message = response.get("message") or {}`;
    `tool_calls = message.get("tool_calls") or []`; text block appended
    only if `message.get("content")` is non-empty; each tool call becomes
    `{"type": "tool_use", "id": fn["name"], "name": fn["name"], "input": fn.get("arguments") or {}}`
    (same call-id-reuse-by-name situation as Gemini).

- **The reverse conversion (`assistant_message`/`assistant_parts`) is
  needed by every backend except Anthropic**, because when the
  conversation history is replayed on the next request, each backend must
  rebuild its own wire-format assistant message from the normalized
  `content` blocks stored in `Context`. Ported as a private method on each
  backend, taking `content` (either a plain string, for a simple text-only
  history entry, or the list of normalized blocks):
  - **OpenAI / Ollama / Ollama Cloud** (`_assistant_message`): split blocks
    into text vs. tool_use; join text blocks' `"text"` into one string for
    the message `content`; if there are tool_use blocks, attach a
    `tool_calls` list rebuilt into each provider's own shape (OpenAI needs
    `arguments` re-serialized with `json.dumps`; Ollama/Ollama Cloud keep
    `arguments` as a dict, no re-serialization).
  - **Gemini** (`_assistant_parts`): map each block back to a `parts` entry
    — `{"functionCall": {"name": ..., "args": ...}}` for tool_use,
    `{"text": ...}` for text.
  - **Anthropic needs no such method.** Its normalized `content` shape
    *is* the wire format already (Anthropic's Messages API natively
    accepts `content: [{"type": "tool_use", ...}, {"type": "text", ...}]`
    for assistant turns), so `to_messages`' existing
    `{"role": str(msg.role), "content": msg.content}` passthrough already
    round-trips correctly with no change.

- **`to_messages`' per-backend `:assistant` handling changes shape
  differently per backend, matching Ruby exactly — don't normalize this
  away**: Gemini already had an explicit `:assistant` branch (it had to,
  Gemini's wire format nests text in `parts`) and this step only swaps its
  body from an inline literal to a call to `_assistant_parts`. Ollama,
  Ollama Cloud, and OpenAI did *not* have an explicit `:assistant` branch
  before (assistant messages fell through their generic `else`), and this
  step adds one that calls `_assistant_message`. This asymmetry exists
  because before this step no backend needed to round-trip a *structured*
  (list-of-blocks) assistant message — every assistant message in steps
  00–04 was plain text.

- **`PROMPTS_DIR`'s off-by-one regression does not carry into Python —
  resolved with the user rather than assumed.** Ruby's `config.rb` computes
  `PROMPTS_DIR` via string-relative arithmetic
  (`File.expand_path("../../prompts", __dir__)` in step 04, now
  `"../../../prompts"` in step 05), and the extra `../` now points one
  directory too high — a real regression, though invisible in practice
  because `.boukensha/settings.yaml` sets `prompt_override.system: true`,
  so `Tasks::Base.prompt` always resolves the system prompt from
  `read_user_prompt` (the `.boukensha/prompts/player/system.md` override)
  and never falls through to `read_default_prompt` (the path that would
  actually dereference the broken `PROMPTS_DIR`). This is the same
  "latent, fixture-masked bug" shape as step 03's `to_messages` arity bug.
  The difference from that precedent: Python's `config.py` computes
  `PROMPTS_DIR` via `Path(__file__).resolve().parent.parent / "prompts"` —
  a `pathlib` parent-chain, not a count of `../` segments — and has done
  so since step 00. It was never expressed the way Ruby's is, so it was
  never subject to this particular regression in the first place. Per the
  user's explicit choice: leave `config.py` exactly as it's been since
  step 04 (still correct), and document in the ported README that Ruby's
  step-05 source has this fixture-masked regression while Python's
  independent implementation does not share it. This is not "silently
  fixing a ported bug" — nothing was ported that needed fixing.

- **`LoopError` is ported even though nothing raises it, matching Ruby.**
  Ruby's `errors.rb` adds `class LoopError < StandardError; end` this
  step, and the Ruby README's own "Updated Files" table describes it as
  being "for runaway agents" — but `Agent#run`'s iteration ceiling is
  handled entirely by `wrap_up`, which returns a message rather than
  raising anything; grepping the whole `05_agent_loop` tree confirms
  `LoopError` is referenced nowhere outside its own definition and that one
  README line. Port `class LoopError(Exception): pass` into `errors.py`
  faithfully (and export it from `__init__.py`, matching `lib/boukensha.rb`
  requiring it in) since it costs nothing to keep and might be wired up in
  a later step, but call out in the README's Considerations section that
  it's currently unused dead code, not a documentation error to silently
  drop.

- **`tasks/base.rb`'s `Integer(value)` → Python `int(value)`.** Ruby's
  `Integer()` kernel method raises `ArgumentError`/`TypeError` on a
  non-numeric string, matching Python's `int()` raising `ValueError`/
  `TypeError` — a direct translation, no `.get()`-style fallback needed
  (same "fetch raises on bad input" precedent as `Hash#fetch`/`dict[key]`
  in `references/conventions.md`).

- **`base_dir` in `examples/example.py` mirrors Ruby's new explicit
  resolution.** Step 04's Python example read tool paths relative to the
  process's cwd (`Path(path).read_text()`, `os.listdir(path)`); Ruby's
  step-05 `example.rb` now resolves both tool paths against
  `base_dir = File.expand_path("..", __dir__)` (the step folder itself,
  one level above `examples/`) via `File.expand_path(path, base_dir)`.
  Python: `base_dir = Path(__file__).resolve().parent.parent`, and each
  tool does `(base_dir / path)` — `pathlib`'s `/` operator already matches
  `File.expand_path`'s behavior of ignoring `base_dir` when `path` is
  absolute, so no extra branching is needed for that case.
  `list_directory`'s join separator also changed from `"\n"` (step 04) to
  `", "` (step 05) — carry that forward too.

- **The example's tool-call/tool-result console logging
  (`puts "  tool call → ...(#{args})"`) will print Python's dict repr
  (`{'path': 'README.md'}`) where Ruby prints its Hash repr
  (`{"path" => "README.md"}` in current Ruby hash-inspect style, since
  these are string-keyed, not symbol-keyed, hashes).** This is a new
  instance of the same accepted cosmetic-repr-diff class already
  documented in `references/conventions.md` (Ruby `Struct#to_s` vs Python
  `dataclass.__str__`) — not a new category to litigate.

## Config directory & schema

Unchanged from steps 00–04 — same `.boukensha/` fixture, same resolution
order. `.boukensha/settings.yaml`'s `tasks.player` block doesn't set
`max_iterations` or `max_output_tokens`, so both fall back to
`Tasks.Base`'s defaults (25 and 1024) when the example runs — this is
expected, not a fixture gap.

## Task list

1. Create `week1_baseline/python/05_agent_loop/` skeleton (dirs above).
2. Copy forward unchanged from `python/04_api_client`: `config.py`,
   `tool.py`, `message.py`, `context.py`, `registry.py`,
   `tasks/player.py`, `backends/base.py`, `prompts/system.md`.
3. Update `errors.py`: add `class LoopError(Exception): pass`.
4. Update `tasks/base.py`: add `DEFAULT_MAX_ITERATIONS = 25`,
   `DEFAULT_MAX_OUTPUT_TOKENS = 1024` class attributes; add
   `max_iterations`/`max_output_tokens` classmethods and a private
   `_integer_setting(cls, settings, key, default)` helper, per the design
   mapping.
5. Update `client.py`: add `tools=None` keyword to `call`, threaded into
   `to_api_payload(tools=tools)`.
6. Update `prompt_builder.py`: add `tools=None` to `to_api_payload`,
   threaded to `self._backend.to_payload(..., tools=tools)`; add
   `parse_response(self, response)` delegating to
   `self._backend.parse_response(response)`.
7. Update each backend (`anthropic.py`, `openai.py`, `gemini.py`,
   `ollama.py`, `ollama_cloud.py`):
   - `to_payload` gains `tools=None`, using it verbatim when not `None`.
   - Add `parse_response` per the per-backend design above.
   - OpenAI/Ollama/Ollama Cloud: add a private `_assistant_message` helper
     and route `to_messages`'s `assistant` case through it.
   - Gemini: add a private `_assistant_parts` helper and route the
     existing `assistant` case in `to_messages` through it instead of the
     inline literal.
   - OpenAI: add `import json` (needed by `parse_response` and
     `_assistant_message`).
8. Write `boukensha/agent.py`: `Agent` class per the design mapping above
   (`__init__`, `run`, and the eight private helpers).
9. Wire `boukensha/__init__.py`: add `Agent` and `LoopError` to the
   existing step-04 export list.
10. Port `examples/example.py`: same provider/model resolution chain as
    step 04, build `PromptBuilder` + `Client` + `Agent`
    (`task_settings=player_settings`), register `read_file`/
    `list_directory` against `base_dir` (per design mapping), add the new
    user message ("Read the README.md file and summarise..."), print
    config/provider/model/max_iterations/max_output_tokens, call
    `agent.run()`, print the final response under a
    `=== FINAL RESPONSE ===` banner.
11. Reuse `requirements.txt` (unchanged — no new dependency; `Agent` needs
    nothing beyond stdlib) and `pyproject.toml` from the step 04 pattern,
    bumping `description` to reference Step 5.
12. Install this step editable into the shared root `.venv`
    (`pip install -e week1_baseline/python/05_agent_loop`), repointing
    from step 04.
13. Verify the runner (`week1_baseline/bin/python/05_agent_loop`) is
    executable; `chmod +x` if not.
14. **Before any live spend**: stand up a throwaway local
    `http.server.HTTPServer` (background thread) returning canned
    Anthropic-shaped responses, and exercise against it: (a) a two-turn
    tool-calling exchange (tool_use → tool_result → end_turn, matching the
    README's own worked example), (b) the `max_iterations` wind-down path
    (canned responses that always request a tool, until the ceiling
    trips and the tools-disabled wrap-up call fires), (c) the
    exhausted-retries → `ApiError` → `_wrap_up`'s `rescue ApiError` →
    fallback message path. Only proceed once all three are confirmed.
15. Run `./week1_baseline/bin/python/05_agent_loop` **once** against the
    real fixture and compare against a single live run of
    `week1_baseline/bin/ruby/05_agent_loop`, per the user's earlier
    agreement to bound the live budget to one comparison run for this
    step (not repeated cosmetic diffing).
16. Exercise the non-Anthropic backends' `parse_response`/
    `_assistant_message` paths directly (`.venv/bin/python -c "..."`)
    since the shipped fixture only selects the `anthropic` provider —
    same category of gap as step 03's untested backend branches.
17. Port `README.md`: New/Updated Files tables (correcting the stale
    `context.rb` entry rather than propagating it), the loop diagram, the
    normalized-response-shape explainer, the task configuration table,
    and a Considerations section covering: the `PROMPTS_DIR` divergence
    from Ruby (fixture-masked bug in Ruby, never present in Python), the
    unused `LoopError`, the two independent `25` constants, and the
    dict-repr cosmetic diff in tool-call console logging.

## Open questions

Resolved during planning:

1. **Whether to replicate Ruby's `PROMPTS_DIR` off-by-one regression in
   Python** — **resolved: no.** Python's `config.py` was never computed
   the way Ruby's is (pathlib parent-chain vs. `../`-counting), so it was
   never subject to this regression; keep it unchanged and correct, and
   document the divergence in the README rather than deliberately
   breaking working Python code to match a Ruby-idiom-specific bug.
2. **Whether to run the Ruby example live during planning** given this
   step's loop can make several billed calls per turn (not just one, like
   step 04) — **resolved: no.** The plan was written from source reading
   alone; live verification is deferred to the execute phase, and even
   then only after a local mock server confirms the loop/retry/wind-down
   logic, per the user's explicit answer.

Decided without asking (precedent already answers these; noted here for
visibility, not as open forks):

3. **`LoopError` ported but left unused** — the discovered-bug/dead-code
   policy from steps 02/03/04 (preserve + document, don't silently drop)
   already settles this; it costs nothing to keep and Ruby's own source
   defines it the same way.
4. **Stale `context.rb` entry in the Ruby README's "Updated Files"
   table** — same stale-doc-table pattern already found and corrected in
   steps 02 and 04; the ported README describes the real, `diff`-verified
   change, not the Ruby table's claim.
