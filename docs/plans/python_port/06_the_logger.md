# Python Port Plan — Step 06: The Logger

## Scope

Port `week1_baseline/ruby/06_the_logger` to a new
`week1_baseline/python/06_the_logger`. Same as steps 00–05, this is a
self-contained copy of the `boukensha` package at this point in its
history (mirroring Ruby's per-step-folder duplication), not a diff against
`python/05_agent_loop`.

The runner already exists and defines the contract:
`week1_baseline/bin/python/06_the_logger` does

```bash
cd week1_baseline/python/06_the_logger
"$REPO_ROOT/.venv/bin/python" examples/example.py
```

— same shared repo-root `.venv` as steps 00–05.

**This step adds `Boukensha::Logger`**: a file logger that writes one
structured JSONL event per phase of an agent turn
(`session_start`/`iteration`/`prompt`/`tool_call`/`tool_result`/`response`/
`turn_end`/`raw`, plus normalized token usage and estimated cost) to
`.boukensha/sessions/<session-id>.jsonl`. `Agent` is threaded with a
`logger:` and calls it at each phase; it also gains resilience this step —
a tool call that raises is now caught and turned into an `ok: false` log
entry plus an `"ERROR: ..."` tool_result message, instead of crashing the
whole turn. A small `Boukensha` module-level singleton (`config`,
`quiet!`/`quiet?`, `debug!`/`debug?`) is introduced to back the logger's
default session directory and its debug-gated `raw` event.

**This step's `Client` still makes real, live, billed HTTP calls**
(inherited from steps 04–05, not new this step). A real session log
already exists at `.boukensha/sessions/20260723T195204Z-e0d3c74d.jsonl`
from an earlier live run — this plan was written using that captured,
real output directly (see below), so no new live spend was needed during
planning. Per the precedent set in step 05: execute-phase verification
should still exercise the new tool-error-handling and logging behavior
against a mock first, and treat any live comparison run as the same
bounded, one-shot budget as before.

## Real captured output (from `.boukensha/sessions/20260723T195204Z-e0d3c74d.jsonl`)

This is an actual, verified log from a prior live run of the Ruby
example, used to ground the design below instead of the Ruby README's own
(incomplete) illustrative snippet:

```json
{"phase": "session_start", "session_id": "20260723T195204Z-e0d3c74d", "at": "2026-07-23T15:52:04-04:00"}
{"phase": "iteration", "n": 1, "max": 25, "session_id": "...", "at": "..."}
{"phase": "prompt", "message_count": 1, "messages": [{"role": "user", "content": "..."}], "tool_count": 2, "tools": ["read_file", "list_directory"], "session_id": "...", "at": "..."}
{"phase": "response", "text": "(tool use — 1 call)", "usage": {"input_tokens": 704, "...": "..."}, "stop_reason": "tool_use", "task": "player", "provider": "anthropic", "model": "claude-haiku-4-5", "usage_unit": "tokens", "input_tokens": 704, "output_tokens": 56, "cost_usd": 0.000984, "session_id": "...", "at": "..."}
{"phase": "tool_call", "name": "read_file", "args": {"path": "README.md"}, "session_id": "...", "at": "..."}
{"phase": "tool_result", "name": "read_file", "result": "...", "ok": true, "error": null, "session_id": "...", "at": "..."}
{"phase": "iteration", "n": 2, "max": 25, "session_id": "...", "at": "..."}
{"phase": "prompt", "message_count": 3, "messages": [...], "tool_count": 2, "tools": [...], "session_id": "...", "at": "..."}
{"phase": "response", "text": "This README excerpt describes...", "usage": {...}, "stop_reason": "end_turn", "task": "player", "provider": "anthropic", "model": "claude-haiku-4-5", "usage_unit": "tokens", "input_tokens": 1582, "output_tokens": 361, "cost_usd": 0.003387, "session_id": "...", "at": "..."}
{"phase": "turn_end", "reason": "completed", "iterations": 2, "tokens": null, "session_id": "...", "at": "..."}
```

Confirms: the real Anthropic API response's `content` blocks carry extra
fields beyond what `parse_response` reads (e.g. a `"caller": {"type":
"direct"}` key on the `tool_use` block) — these pass through untouched
since Anthropic's `content` array is stored and replayed verbatim; the
real `usage` object has many more fields than just token counts (cache
fields, `service_tier`, `inference_geo`) — also passed through verbatim;
`at` timestamps are local time with UTC offset at second precision; the
`response` phase's `text` field for a tool-use turn is the
`"(tool use — N call(s))"` placeholder, confirmed with correct singular
pluralization (`1 call`, no trailing `s`).

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `Gemfile` | unchanged from step 05 | `requirements.txt` (unchanged) |
| `lib/boukensha.rb` | **changed** — adds a `Boukensha` module-level singleton (`self.config`, `self.quiet!`/`quiet?`, `self.loud!`, `self.debug!`/`debug?`); reorders/adds requires (`boukensha/logger`, explicit `boukensha/backends/base`) | `boukensha/__init__.py` — adds the singleton (renamed per resolved forks — see design mapping), adds `Logger` export, drops `LoopError` |
| `lib/boukensha/logger.rb` | **new** — `Boukensha::Logger`: writes one JSONL event per phase to `.boukensha/sessions/<session-id>.jsonl` | `boukensha/logger.py` — new `Logger` class |
| `lib/boukensha/errors.rb` | **changed** — removes `LoopError` (dead code deleted; validates that it was indeed unused, as this port's own step-05 README already noted) | `boukensha/errors.py` — remove `LoopError` |
| `lib/boukensha/config.rb` | **changed** — removes `mud_host`/`mud_port`/`mud_username`/`mud_password` (dead code — confirmed via repo-wide grep, referenced nowhere); cosmetic whitespace realignment only otherwise | `boukensha/config.py` — remove the four `mud_*` methods |
| `lib/boukensha/context.rb` | **cosmetic only** — instance-variable-assignment whitespace realignment, no behavior change (`diff` confirmed) | `boukensha/context.py` — copy forward unchanged (nothing to port, Python has no equivalent whitespace-alignment convention) |
| `lib/boukensha/prompt_builder.rb` | **changed** — adds `attr_reader :backend` (so `Logger` can pull `backend.model`/`usage_unit`/`estimate_cost` for cost logging); trailing-newline fix | `boukensha/prompt_builder.py` — add a `backend()` accessor method (plain method, matching this class's existing `headers()`/`url()` style — not `@property`) |
| `lib/boukensha/agent.rb` | **changed** — threads a `logger:` kwarg (default `Logger.new`) through; logs `iteration`/`prompt`/`raw`/`response`/`turn_end`/`limit_reached`; wraps tool dispatch in a rescue that turns a raised error into an `ok: false` log entry and an `"ERROR: ..."` tool_result instead of crashing | `boukensha/agent.py` — same, with `logger=None` + lazy default (see design mapping) |
| `lib/boukensha/client.rb`, `backends/*.rb` (all 5 + `base.rb`), `tasks/base.rb`, `tasks/player.rb`, `tool.rb`, `message.rb`, `registry.rb` | byte-identical to step 05 (`diff` confirmed) | copy forward unchanged from `python/05_agent_loop` |
| `prompts/system.md` | byte-identical to step 05 (`diff` confirmed) | copy forward unchanged |
| `examples/example.rb` | Builds `Logger.new`, passes `logger:` into `Agent.new`; banner text updated to Step 6; otherwise same shape as step 05 (provider/model resolution, `read_file`/`list_directory` tools, README-summary prompt) | `examples/example.py` — same shape |
| `README.md` | Session log format, Logger API table (Ruby's own table is **stale/incomplete** — see design mapping), task configuration, debug events, run example | `README.md` — adapted, with the stale table corrected rather than propagated, using the real captured session log above as the worked example |

Runner already in place, no change needed: `week1_baseline/bin/python/06_the_logger`
(verify it's executable; `chmod +x` if not).

## Target layout

```
week1_baseline/python/06_the_logger/
  requirements.txt
  pyproject.toml
  prompts/
    system.md                      # copied forward unchanged
  boukensha/
    __init__.py                    # adds Logger + singleton, drops LoopError
    config.py                      # drops mud_host/mud_port/mud_username/mud_password
    tool.py                        # copied forward unchanged
    message.py                     # copied forward unchanged
    context.py                     # copied forward unchanged
    errors.py                      # drops LoopError
    registry.py                    # copied forward unchanged
    prompt_builder.py               # adds backend() accessor
    client.py                      # copied forward unchanged
    logger.py                      # new
    agent.py                       # threads logger, tool-error handling, response/turn_end logging
    tasks/
      __init__.py
      base.py                      # copied forward unchanged
      player.py                    # copied forward unchanged
    backends/
      __init__.py
      base.py                      # copied forward unchanged
      anthropic.py                 # copied forward unchanged
      ollama.py                    # copied forward unchanged
      ollama_cloud.py               # copied forward unchanged
      openai.py                    # copied forward unchanged
      gemini.py                    # copied forward unchanged
  examples/
    example.py
  README.md
```

## Ruby → Python design mapping

- **The `Boukensha` module-level singleton lives directly in
  `boukensha/__init__.py`**, mirroring Ruby's `module Boukensha ... end`
  block living in the top-level `lib/boukensha.rb` (not a separate
  submodule) — plain module globals plus module-level functions:
  `_quiet = False`, `_debug = False`, `_config = None`.

- **`self.config` → `current_config()`, not `config()`** (resolved with
  the user). `boukensha/config.py` is already an importable submodule
  (`from boukensha.config import PROMPTS_DIR`, used by every step's
  `example.py`); a module-level function also named `config` inside
  `boukensha/__init__.py` would reassign the `boukensha.config` attribute
  and shadow the submodule for any future attribute-style access, even
  though today's `from boukensha.config import X` style would keep
  resolving correctly via `sys.modules`. Renaming avoids relying on that
  import-system subtlety entirely:
  ```python
  def current_config():
      global _config
      if _config is None:
          _config = Config()
      return _config
  ```

- **`self.quiet!`/`self.quiet?` → `quiet()`/`is_quiet()`; `self.debug!`/
  `self.debug?` → `debug()`/`is_debug()`** (resolved with the user).
  Dropping bang/query punctuation per the established convention would
  collapse each pair onto one identical Python name — Ruby's separate
  method tables allow the collision, Python's single namespace doesn't
  (same shape as step 03's `model_info` collision). Setter keeps the bare
  verb name, getter gets an `is_`-prefixed boolean name:
  ```python
  def quiet():
      global _quiet
      _quiet = True

  def is_quiet() -> bool:
      return _quiet

  def debug():
      global _debug
      _debug = True

  def is_debug() -> bool:
      return _debug
  ```
  `self.loud!` → `loud()` (no collision, only one method with that root).
  Note: only `is_debug()` is actually exercised by the shipped fixture
  (via `Logger.raw`'s guard); `quiet()`/`is_quiet()`/`loud()` are unused
  this step too (dead code, like `LoopError` was in step 05 — which Ruby
  has since deleted; document but don't omit, they're real public API).

- **`logger.py` reaches the singleton via a deferred `import boukensha`,
  not `from . import current_config`.** `Logger._default_dir` and
  `Logger.raw` need `current_config()`/`is_debug()` at *call* time, not at
  `logger.py`'s *import* time — `boukensha/__init__.py` imports `.logger`
  partway through its own execution (to export `Logger`), so a top-level
  `from . import current_config` inside `logger.py` would depend on exact
  statement ordering in `__init__.py` to avoid a circular-import failure.
  A plain `import boukensha` at the top of `logger.py`, with the actual
  attribute access deferred into method bodies (`boukensha.current_config()`,
  `boukensha.is_debug()`), sidesteps the ordering question entirely —
  `import boukensha` just binds a reference to the (possibly still-
  initializing) module object, and by the time those methods are actually
  *called* at runtime, `__init__.py` has long since finished executing.
  (For fidelity, the singleton definitions in `__init__.py` are still
  placed before `from .logger import Logger`, matching Ruby's real file
  order — just not load-bearing for correctness given the deferred-access
  design.)

- **Two instances of the same Ruby→Python default-argument translation
  rule this step** — Ruby method-parameter default *expressions*
  (`logger: Logger.new`, `snapshot: {}`) are evaluated **fresh on every
  call**; Python default *values* are evaluated **once, at function-
  definition time**, and then reused (and, for mutable objects, shared)
  across every call that doesn't override them. Both instances need a
  `None` sentinel plus a body-level default, not a literal translation:
  - `Agent.__init__(..., logger=None, ...)` → `self._logger = logger if logger is not None else Logger()`.
    A literal `logger=Logger()` would construct exactly **one** `Logger`
    (one file, one session id) shared by every `Agent` built without an
    explicit `logger=`, for the lifetime of the Python process — a real
    behavior change from Ruby's per-call-fresh instance, not just a style
    nit.
  - `Logger.__init__(..., snapshot=None, ...)` → `snapshot = snapshot or {}` inside the body.

- **`Agent`'s new tool-dispatch error handling**: Ruby's
  `rescue StandardError => e` → Python `except Exception as e:`. `Exception`
  and `StandardError` both exclude their language's "shouldn't normally be
  caught generically" signals (`SystemExit`/`KeyboardInterrupt`/
  `GeneratorExit` in Python; `NoMemoryError`/`SignalException`/etc. in
  Ruby), so this is a direct, uncontroversial translation — including that
  `UnknownToolError`/`ApiError` (both plain `Exception` subclasses) get
  caught by it just like their Ruby counterparts (both `StandardError`
  subclasses) do. The one cosmetic difference: Ruby's fallback string
  interpolates `e.class` (e.g. `Boukensha::UnknownToolError`, fully
  qualified); Python's `type(e).__name__` gives just `UnknownToolError`
  (no module prefix) — same class of cosmetic repr difference already
  accepted for `Struct#to_s`/hash-repr in earlier steps, not a new
  category.

- **`Logger#first_integer`'s Ruby `rescue` is attached to the whole
  method, not per-iteration — the Python translation must preserve that,
  not "improve" it into a per-key try/except.** Ruby:
  ```ruby
  def first_integer(hash, *keys)
    keys.each do |key|
      value = hash[key] || hash[key.to_sym]
      return Integer(value) unless value.nil?
    end
    nil
  rescue ArgumentError, TypeError
    nil
  end
  ```
  The `rescue` wraps the *entire* method body (Ruby's implicit
  method-level `begin`/`rescue`), so if the **first** matching key's value
  fails to parse as an integer, the whole call returns `nil` immediately —
  it does **not** fall through and try the next key. A Python translation
  using a `try/except` *inside* the loop (continue-on-failure) would
  silently change this behavior. Correct translation wraps the whole loop
  in one `try`:
  ```python
  def _first_integer(self, usage, *keys):
      try:
          for key in keys:
              value = usage.get(key)
              if value is not None:
                  return int(value)
          return None
      except (ValueError, TypeError):
          return None
  ```
  In practice this only matters for malformed usage data the real APIs
  don't send, but the translation should still be exact.

- **`Logger#provider_name`'s CamelCase→snake_case regex, with an explicit
  `"OpenAI"` override** (resolved with the user, discovered-bug policy).
  The regex (`re.sub(r'([a-z\d])([A-Z])', r'\1_\2', name).lower()`) gets
  `OllamaCloud`→`ollama_cloud`, `Anthropic`→`anthropic`, `Gemini`→`gemini`,
  and `Ollama`→`ollama` all correct, but `OpenAI`→`open_ai` — mismatching
  the real provider key (`"openai"`, used everywhere in
  `settings.yaml`/config). Fixture-masked (the shipped fixture uses
  `provider: anthropic`), same shape as step 03's `to_messages` bug and
  step 05's `PROMPTS_DIR` regression — but here, unlike those two,
  resolved in favor of **normalizing**, not preserving, since it's a
  purely internal log-metadata helper (not user-facing Ruby-lesson
  content) and correctness of the logged `provider` field is more useful
  than faithfully reproducing an incidental regex quirk:
  ```python
  _PROVIDER_NAME_OVERRIDES = {"OpenAI": "openai"}

  def _provider_name(self, backend):
      if backend is None:
          return None
      name = type(backend).__name__
      return self._PROVIDER_NAME_OVERRIDES.get(
          name, re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name).lower()
      )
  ```

- **`SecureRandom.hex(4)` → `secrets.token_hex(4)`** — both produce 4
  random bytes rendered as 8 lowercase hex characters; direct equivalent.

- **`Time.now.iso8601` → `datetime.now().astimezone().isoformat(timespec="seconds")`.**
  Confirmed against the real captured log above
  (`"2026-07-23T15:52:04-04:00"` — local time, UTC offset, second
  precision, no fractional seconds). Ruby's `iso8601` with no argument
  defaults to second precision; Python's `isoformat()` defaults to
  microsecond precision unless `timespec="seconds"` is passed explicitly.

- **`event.merge(session_id:, at:)` → `{**event, "session_id": ..., "at": ...}`.**
  Ruby's `Hash#merge` appends new keys (not already in `event`) at the
  end while preserving original key order for anything already present;
  Python dict literals with `**event` unpacking followed by explicit keys
  behave identically (later keys win on conflict, insertion order
  otherwise preserved) — direct translation, confirmed by the real log's
  field ordering (`phase` first, `session_id`/`at` last on every line).

- **`hash.compact` → drop `None`-valued keys with a dict comprehension**:
  `{k: v for k, v in metadata.items() if v is not None}`, used in
  `_execution_metadata`.

- **`FileUtils.mkdir_p(File.dirname(path))` → `Path(path).parent.mkdir(parents=True, exist_ok=True)`.**

- **`backend&.respond_to?(:estimate_cost)` → `hasattr(backend, "estimate_cost")`** (same `respond_to?`→`hasattr` translation already established in step 05 for `Agent`'s task duck-typing checks).

## Config directory & schema

Unchanged from steps 00–05 — same `.boukensha/` fixture. `Logger`'s
default session directory (`.boukensha/sessions/`) already exists in the
fixture (confirmed: it already contains one real session log from an
earlier live run, used above), so no new directory needs to be created by
hand — `Logger`'s own `mkdir_p`/`Path.mkdir(parents=True, exist_ok=True)`
handles it idempotently regardless.

## Task list

1. Create `week1_baseline/python/06_the_logger/` skeleton (dirs above).
2. Copy forward unchanged from `python/05_agent_loop`: `tool.py`,
   `message.py`, `context.py`, `registry.py`, `client.py`,
   `tasks/player.py`, `tasks/base.py`, `backends/base.py`, all 5
   `backends/*.py`, `prompts/system.md`.
3. Update `config.py`: remove `mud_host`, `mud_port`, `mud_username`,
   `mud_password`.
4. Update `errors.py`: remove `LoopError`.
5. Update `prompt_builder.py`: add `backend(self)` accessor method
   (returns `self._backend`).
6. Write `boukensha/logger.py`: `Logger` class per the design mapping
   above — constructor, all eight public phase methods, `close`, and the
   private helpers (`_default_dir`, `_write_log`, `_generate_session_id`,
   `_serialize_message`, `_execution_metadata`, `_task_name`,
   `_provider_name`, `_usage_tokens`, `_first_integer`, `_estimate_cost`,
   `_iso_now`).
7. Update `agent.py`: add `logger=None` param with lazy `Logger()`
   default; log `iteration`/`prompt` at the top of each loop pass; log
   `raw` right after the API call; log `limit_reached` right before
   `_wrap_up` fires; `_handle_tool_calls` gains a `response` parameter,
   logs a `response` phase (reasoning text or the `"(tool use — N
   call(s))"` placeholder) before adding the assistant message, and wraps
   each tool dispatch in `try/except Exception` logging `ok=True`/
   `ok=False` accordingly; `_wrap_up` logs `response` + `turn_end` on the
   success path, and `turn_end` only (no `response`) on the `ApiError`
   path, matching Ruby's asymmetry exactly; add `_log_response` and
   `_normalized_usage` private helpers.
8. Update `__init__.py`: add the `Boukensha` singleton block
   (`current_config`/`quiet`/`is_quiet`/`loud`/`debug`/`is_debug`,
   placed before `from .logger import Logger`); add `Logger` to the
   import line and `__all__`; remove `LoopError` from both.
9. Port `examples/example.py`: instantiate `logger = Logger()`, pass
   `logger=logger` into `Agent(...)`, update the banner to
   `"=== BOUKENSHA Step 6: The Logger ==="`, keep the comment about
   `boukensha.debug()` enabling raw-response logging (naming per the
   resolved fork).
10. Reuse `requirements.txt` (unchanged — `Logger` needs nothing beyond
    stdlib) and `pyproject.toml` from the step 05 pattern, bumping
    `description` to reference Step 6.
11. Install this step editable into the shared root `.venv`
    (`pip install -e week1_baseline/python/06_the_logger`), repointing
    from step 05.
12. Verify the runner (`week1_baseline/bin/python/06_the_logger`) is
    executable; `chmod +x` if not.
13. **Before any live spend**: exercise the new logging/error-handling
    logic against a mock server (reusing the step-05 mock harness
    pattern), confirming: (a) a normal tool-call turn produces the
    expected JSONL sequence (`session_start`→`iteration`→`prompt`→
    `response`→`tool_call`→`tool_result` ok=true→`iteration`→...→
    `turn_end`); (b) a tool that raises (e.g. dispatching an unregistered
    tool name, or a tool block that itself raises) gets caught, logged
    with `ok=false`/`error=...`, and the loop continues rather than
    crashing; (c) the `max_iterations` wind-down path still logs
    `limit_reached` then a final `response`+`turn_end`; (d) the
    exhausted-retries path still logs `turn_end` but *no* `response` line
    on the wrap-up call's `ApiError`, matching Ruby's asymmetry.
14. Run `./week1_baseline/bin/python/06_the_logger` **once** against the
    real fixture and compare against a single live run of
    `week1_baseline/bin/ruby/06_the_logger`, per the same bounded-budget
    agreement as step 05 — diff both the console output and the two
    resulting `.jsonl` session logs (field-for-field structure, not exact
    values, since timestamps/token counts/text will differ run to run).
15. Exercise `Boukensha.debug()`/`is_debug()` and the non-Anthropic
    backends' interaction with `_provider_name` directly
    (`.venv/bin/python -c "..."`), since the shipped fixture only selects
    the `anthropic` provider and never calls `Boukensha.debug()`.
16. Port `README.md`: session log format (using the real captured JSONL
    above as the worked example, not Ruby's abbreviated snippet), a
    **corrected** Logger API table (Ruby's own table is missing `max`,
    `ok`/`error`, `stop_reason`, `limit_reached`, `turn_end`, and `close`,
    and lists a `budget:` parameter that doesn't exist in the real code at
    all — confirmed by direct comparison against `logger.rb`), task
    configuration, debug events (`boukensha.debug()`), and a
    Considerations section covering the three resolved forks plus the two
    mutable-default-argument translations.

## Open questions

Resolved during planning:

1. **Naming the `Boukensha.config` singleton accessor in Python**, given
   `boukensha/config.py` is already an importable submodule — **resolved:
   `current_config()`**, not `config()`, to avoid shadowing the submodule
   attribute.
2. **Naming the `quiet!`/`quiet?` and `debug!`/`debug?` bang/query pairs**,
   which collapse onto identical Python names once punctuation is
   dropped — **resolved: setter keeps the bare name (`quiet()`,
   `debug()`), getter gets an `is_` prefix (`is_quiet()`, `is_debug()`)**.
3. **Whether to preserve or normalize `_provider_name`'s `"OpenAI"` →
   `"open_ai"` mismatch** (fixture-masked, real key is `"openai"`) —
   **resolved: normalize**, via an explicit override table, since this is
   an internal log-metadata helper rather than user-facing Ruby-lesson
   content, unlike the step 03/05 precedents which were preserved.

Decided without asking (precedent already answers these; noted here for
visibility, not as open forks):

4. **`Agent`'s `logger=None` + lazy default, and `Logger`'s
   `snapshot=None` + lazy default** — both are direct instances of the
   general "Ruby fresh-per-call parameter defaults need a `None` sentinel
   in Python" rule; there's one correct translation, not a style choice.
5. **`rescue StandardError` → `except Exception`** — direct,
   uncontroversial translation (see design mapping); the only difference
   (qualified vs. unqualified exception class name in the fallback
   string) is the same class of cosmetic repr difference already accepted
   since step 00.
6. **Whether to run the Ruby example live during planning** — moot this
   time: a real session log from an earlier live run already existed at
   `.boukensha/sessions/20260723T195204Z-e0d3c74d.jsonl` and was used
   directly to ground this plan, so no new live spend was needed.
