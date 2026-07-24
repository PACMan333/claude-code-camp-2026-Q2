# Python Port Plan — Step 07: The Run DSL

## Scope

Port `week1_baseline/ruby/07_the_run_dsl` to a new
`week1_baseline/python/07_the_run_dsl`. Same as steps 00–06, this is a
self-contained copy of the `boukensha` package at this point in its
history (mirroring Ruby's per-step-folder duplication), not a diff against
`python/06_the_logger`.

The runner already exists and defines the contract:
`week1_baseline/bin/python/07_the_run_dsl` does

```bash
cd week1_baseline/python/07_the_run_dsl
"$REPO_ROOT/.venv/bin/python" examples/example.py
```

— same shared repo-root `.venv` as steps 00–06.

**This step adds a single top-level entry point, `Boukensha.run`**, plus a
small `RunDSL` host object that a block can call `tool` against. Every
previous step required manually constructing and wiring `Context`,
`Registry`, a backend, `PromptBuilder`, `Client`, `Logger`, and `Agent`;
`Boukensha.run(task: "...") do ... end` now hides all of that behind one
call. This is also the step where two previously-removed pieces of dead
code quietly come back (`Config#mud_host`/`mud_port`/`mud_username`/
`mud_password`, deleted in step 06, and `LoopError`, also deleted in step
06) — confirmed via `diff` as a real, deliberate re-addition in the Ruby
source, not a porting artifact to second-guess. `Logger` also grows two
more forward-looking, currently-unused methods (`turn`, `subscribe`) —
see the design mapping below for what they're scaffolding.

**This step's `Client`/`Agent` still make real, live, billed HTTP calls**
(inherited from steps 04–06, not new here). Per the precedent from steps
05–06: mock-first verification during execute, and treat any live
comparison run as the same bounded, one-shot budget as before (ask before
spending it).

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `Gemfile` | unchanged from step 06 (`diff` confirmed) | `requirements.txt` (unchanged) |
| `lib/boukensha.rb` | **changed** — adds `self.run(task:, system:, model:, backend:, api_key:, ollama_host:, log:, max_output_tokens:, &block)`, the top-level DSL entry point; requires `boukensha/run_dsl` | `boukensha/__init__.py` — adds `run()` (see design mapping for exact placement/why) |
| `lib/boukensha/run_dsl.rb` | **new** — `Boukensha::RunDSL`: the object `self` becomes inside a `Boukensha.run` block via `instance_eval`; exposes only `tool` | `boukensha/run_dsl.py` — new `RunDSL` class |
| `lib/boukensha/config.rb` | **changed** — **re-adds** `mud_host`/`mud_port`/`mud_username`/`mud_password` (deleted in step 06); cosmetic `load_env` one-liner→multi-line `if` | `boukensha/config.py` — re-add the four `mud_*` methods (same bodies as their original step-05 Python form, before step 06 deleted them) |
| `lib/boukensha/errors.rb` | **changed** — **re-adds** `LoopError` (deleted in step 06) | `boukensha/errors.py` — re-add `LoopError` |
| `lib/boukensha/logger.rb` | **changed** — adds `turn(n:)` (new `turn` phase) and `subscribe(&block)` (registers a callback invoked with every event as it's written) | `boukensha/logger.py` — add `turn(self, *, n)` and `subscribe(self, callback)`, plus broadcasting in `_write_log` |
| `lib/boukensha/context.rb` | **cosmetic only** — whitespace realignment, missing trailing newline (`diff` confirmed, no behavior change) | `boukensha/context.py` — copy forward unchanged |
| `lib/boukensha/agent.rb`, `prompt_builder.rb`, `client.rb`, `registry.rb`, `tool.rb`, `message.rb`, `backends/*.rb` (all 5 + `base.rb`), `tasks/base.rb`, `tasks/player.rb` | byte-identical to step 06 (`diff` confirmed) | copy forward unchanged from `python/06_the_logger` |
| `prompts/system.md` | byte-identical to step 06 (`diff` confirmed) | copy forward unchanged |
| `examples/example.rb` | **rewritten** — replaces ~50 lines of manual wiring with one `Boukensha.run(task: "...") do ... tool "..." ... end` call | `examples/example.py` — same shape, using `register_tools=` (see design mapping) |
| `README.md` | Options table, before/after comparison, run example — **unreliable**, see design mapping | `README.md` — rewritten from the real source, not adapted from Ruby's table |

Runner already in place, no change needed: `week1_baseline/bin/python/07_the_run_dsl`
(verify it's executable; `chmod +x` if not).

## Target layout

```
week1_baseline/python/07_the_run_dsl/
  requirements.txt
  pyproject.toml
  prompts/
    system.md                      # copied forward unchanged
  boukensha/
    __init__.py                    # adds run(), RunDSL export
    config.py                      # re-adds mud_host/mud_port/mud_username/mud_password
    tool.py                        # copied forward unchanged
    message.py                     # copied forward unchanged
    context.py                     # copied forward unchanged
    errors.py                      # re-adds LoopError
    registry.py                    # copied forward unchanged
    prompt_builder.py               # copied forward unchanged
    client.py                      # copied forward unchanged
    logger.py                      # adds turn(), subscribe()
    agent.py                       # copied forward unchanged
    run_dsl.py                     # new — RunDSL
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

- **`instance_eval(&block)` → an explicit `register_tools=` callable
  taking the `RunDSL` instance as its one argument** (resolved with the
  user). Ruby's block runs with `self` implicitly rebound to the
  `RunDSL` instance, so bare `tool "name", ...` calls resolve against it
  with no explicit receiver — Python has no way to rebind a plain
  function's implicit `self`, so the natural translation makes the
  receiver explicit instead of trying to fake Ruby's metaprogramming:
  ```python
  def register(dsl):
      dsl.tool(
          "read_file",
          description="Read a file",
          parameters={"path": {"type": "string"}},
          block=lambda *, path: open(path).read(),
      )

  result = boukensha.run(task="...", register_tools=register)
  ```
  `register_tools` is called (if provided) once, right after `Context`/
  `Registry` are built and before the backend/logger/agent are
  constructed — matching Ruby's real ordering exactly (tools must exist
  before the agent starts its first iteration, but the DSL doesn't need
  the backend/logger/agent to already exist).

- **`RunDSL#tool` is a thin pass-through to `Registry#tool`, matching that
  method's existing Python signature shape exactly** — not Ruby's
  keyword-required `description:`. `registry.py`'s own `tool` (established
  since step 02) already made `description` a plain positional-or-keyword
  parameter, not keyword-only, even though Ruby requires it as a keyword.
  `RunDSL.tool` should mirror that established precedent rather than
  independently re-deriving a "more faithful" keyword-only signature:
  ```python
  class RunDSL:
      def __init__(self, registry) -> None:
          self._registry = registry

      def tool(self, name, description, parameters=None, block=None):
          return self._registry.tool(name, description, parameters, block)
  ```

- **`RunDSL` lives in its own `boukensha/run_dsl.py`; `run()` lives
  directly in `boukensha/__init__.py`** — mirroring Ruby's real file
  split exactly: `lib/boukensha/run_dsl.rb` contains *only* the `RunDSL`
  class, while `self.run` is defined inside the `module Boukensha ... end`
  block in `lib/boukensha.rb` itself, alongside `config`/`quiet!`/
  `debug!` from step 06. `run()` needs `RunDSL`, `Context`, `Registry`,
  all five backends, `PromptBuilder`, `Client`, `Logger`, and `Agent` —
  all of which `__init__.py` already imports for re-export — so placing
  `run()` there and adding it *after* those imports needs no deferred-
  import trick (unlike step 06's `current_config`/`is_debug`, which had
  to solve a real circular-import problem because `logger.py`, a leaf
  submodule, needed to reach back up into the package; `run()` isn't in
  that position, it's in the package's own `__init__.py`).

- **Ruby's `||=`/`||` default-filling only treats `nil`/`false` as
  "unset"; Python's `or`/truthiness treats `0`, `""`, `[]`, `{}` as
  "unset" too — every default-fill in `run()` must use an explicit
  `is not None` check, not `or`.** This matters concretely for
  `max_output_tokens`: Ruby's `max_output_tokens || task_class.max_output_tokens(task_settings)`
  keeps an explicit `max_output_tokens: 0` from a caller (0 is truthy in
  Ruby), but Python's `max_output_tokens or task_class.max_output_tokens(...)`
  would silently discard that same `0` and substitute the task default (0
  is falsy in Python) — a real behavior divergence, not just a style
  choice. Apply `is not None` consistently to all five default-fills:
  `system`, `model`, `backend`, `api_key`, `max_output_tokens`.

- **The 5-way backend dispatch and the 4-way API-key-env-var lookup are
  direct translations of the same shape already used in every prior
  step's `example.py`** (if/elif chain for the backend, since `Ollama`
  has a different constructor shape than the other four; a dict lookup
  for the API key, matching Ruby's `case` having no `:ollama` branch —
  Ollama needs no API key, and a Python dict lookup with `.get(backend)`
  naturally returns `None` for a key that isn't present, same as Ruby's
  `case` falling through with no matching `when`):
  ```python
  if api_key is None:
      api_key = {
          "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
          "openai": os.environ.get("OPENAI_API_KEY"),
          "gemini": os.environ.get("GEMINI_API_KEY"),
          "ollama_cloud": os.environ.get("OLLAMA_API_KEY"),
      }.get(backend)
  ```
  Note this uses `ENV["KEY"]`/`os.environ.get(...)` (returns `None` if
  missing), not `ENV.fetch`/`os.environ[...]` (raises) — deliberately more
  lenient than `example.py`'s own historical `ENV.fetch` usage, since
  `:ollama` legitimately needs no key at all and `run()` defers any
  missing-key failure to whenever the HTTP call actually needs it.

- **`backend` stays a plain string throughout (`"anthropic"`, not a
  symbol)** — same established symbol→string convention as every prior
  step. Ruby's `task_class.provider(task_settings).to_sym` becomes just
  `task_class.provider(task_settings)` in Python (already a string, no
  `.to_sym`-equivalent needed), and the `case backend when :anthropic`
  dispatch becomes `if backend == "anthropic"` /
  a dict lookup keyed by plain strings.

- **`ensure logger&.close` → `try/finally` with a `logger = None`
  sentinel set before the `try`, checked with `is not None` in the
  `finally`.** If `register_tools` itself raises (before `Logger` is ever
  constructed, matching Ruby's real ordering — the DSL block runs before
  `Logger.new`), `logger` stays `None` and the `finally` is correctly a
  no-op, mirroring Ruby's safe-navigation (`logger&.close`) exactly rather
  than raising a second, unrelated `AttributeError` on `None.close()`.

- **`Config#mud_host`/`mud_port`/`mud_username`/`mud_password` are
  re-added, not newly invented** — deleted in step 06, back in step 07
  with identical bodies to their original step-05 Python form. Still
  referenced nowhere in the shipped `lib/`/`examples/` (confirmed via
  repo-wide `grep`), so still dead code today — but per
  `week1_baseline/ruby/ITERATIONS.md`'s step-10 entry ("MUD gameplay
  comes from the `mud-manager --mcp` daemon, the same `mud_manager` gem
  the old `Tools::Mud` wrapped"), these are scaffolding for a future
  MUD-connection tool, not an oversight. Port them back faithfully; don't
  omit them because they're currently unused.

- **`LoopError` is also re-added, still unused.** Same situation as the
  `mud_*` methods: deleted in step 06 (this port's own README there
  documented it as dead code), now back, and still referenced nowhere in
  `lib/`/`examples/`. `ITERATIONS.md`'s step-5 entry mentions it in the
  same breath as `Boukensha.run` ("Adds `Boukensha::Errors` (`LoopError`,
  `ApiError`) and wires everything together in `Boukensha.run`"),
  suggesting it's meant for a future error path within `Agent`/`run()`
  that hasn't landed yet. Port it back faithfully; the Considerations
  section should note it's still dead code, not silently drop it because
  it was dead code once before.

- **`Logger#turn(n:)` is new, forward-looking, and unused this step.**
  Nothing in `lib/`/`examples/` calls it (`Agent` is byte-identical to
  step 06 and still only calls `iteration`). Likely scaffolding for step
  08's REPL, per `ITERATIONS.md` ("A single `Context` is shared across
  all turns so the agent sees full conversation history") — a `turn`
  phase distinct from the existing per-API-call `iteration` phase would
  make sense once a REPL wraps multiple agent turns in one session. Port
  faithfully as `def turn(self, *, n): self._write_log({"phase": "turn", "n": n})`.

- **`Logger#subscribe(&block)` is new, forward-looking, and unused this
  step** — a plain observer/pub-sub addition, not another instance of the
  `instance_eval` DSL problem. `@subscribers << block` appends a plain
  Ruby block (a zero-metaprogramming callable, unlike `RunDSL`'s
  `instance_eval` case); `write_log` calls `s.call(event)` for each
  subscriber after writing/flushing. Direct translation:
  `self._subscribers = []` in `__init__`; `subscribe(self, callback)`
  appends; `_write_log` does `for s in self._subscribers: s(event)` after
  flushing. Confirmed via `ITERATIONS.md`'s step-11 entry this is
  scaffolding for a future TUI's live progress line ("every structured
  log event is now broadcast to subscribers... which is how `Tui` updates
  its progress line in real time without polling") — not dead code to
  second-guess, just not wired to anything yet.

- **The Ruby README for this step is unusually unreliable — worth
  flagging explicitly, not just "adapting."** It's titled "Step 6" (off
  by one), and its options table lists `token_budget:` (default `8192`)
  and `max_tokens:` (default `1024`) — neither of which exists anywhere
  in the real `lib/boukensha.rb` signature (the real param is
  `max_output_tokens:`, with no hardcoded numeric default at all — it
  falls through to `task_class.max_output_tokens(task_settings)`).
  Cross-checked against `ITERATIONS.md`'s step-11 entry: *"`Boukensha.run`
  / `.repl` — `context_window:` keyword replaces `token_budget:`"* —
  confirming `token_budget:` is a **future** (step 11) rename target the
  README is describing prematurely, not this step's actual signature.
  Similarly, `backend:` is documented as "`:anthropic` or `:ollama`" only,
  though the real code supports all five backends from step 03 onward.
  The ported README must describe only the real, source-verified
  signature (`task`, `system`, `model`, `backend`, `api_key`,
  `ollama_host`, `log`, `max_output_tokens`, `register_tools`) — this is
  a stronger case of the stale-README pattern already seen in steps 02/
  04/05/06, not something to soften.

## Config directory & schema

Unchanged from steps 00–06 — same `.boukensha/` fixture.

## Task list

1. Create `week1_baseline/python/07_the_run_dsl/` skeleton (dirs above).
2. Copy forward unchanged from `python/06_the_logger`: `tool.py`,
   `message.py`, `context.py`, `registry.py`, `client.py`, `agent.py`,
   `prompt_builder.py`, `tasks/player.py`, `tasks/base.py`,
   `backends/base.py`, all 5 `backends/*.py`, `prompts/system.md`.
3. Update `config.py`: re-add `mud_host`, `mud_port`, `mud_username`,
   `mud_password` (same bodies as their step-05 Python form).
4. Update `errors.py`: re-add `LoopError`.
5. Update `logger.py`: add `turn(self, *, n)`; add
   `self._subscribers = []` in `__init__`, `subscribe(self, callback)`,
   and broadcast to subscribers at the end of `_write_log`.
6. Write `boukensha/run_dsl.py`: `RunDSL` class per the design mapping
   above.
7. Update `__init__.py`: import `RunDSL` from `.run_dsl`; add `run()`
   per the design mapping (resolve `system`/`model`/`backend`/`api_key`/
   `max_output_tokens` with `is not None` checks; build `Context` +
   `Registry`; call `register_tools(dsl)` if given; construct the
   backend via the 5-way dispatch; build `PromptBuilder` + `Client`;
   compute `effective_max_iterations`/`effective_max_output_tokens` from
   `Player.max_iterations`/`max_output_tokens`; construct `Logger` with a
   `snapshot=` of `task`/`max_iterations`/`max_output_tokens`/`model`/
   `provider`; construct `Agent`; add the user message; call
   `agent.run()` inside a `try`/`finally` that closes the logger if it
   was constructed); add `RunDSL` to `__all__`.
8. Port `examples/example.py`: print the config banner, call
   `boukensha.run(task="...", register_tools=register)` where `register`
   registers `read_file`/`list_directory` against `base_dir` (same
   resolution as step 05/06's example), print the final response.
9. Reuse `requirements.txt` (unchanged) and `pyproject.toml` from the
   step 06 pattern, bumping `description` to reference Step 7.
10. Install this step editable into the shared root `.venv`
    (`pip install -e week1_baseline/python/07_the_run_dsl`), repointing
    from step 06.
11. Verify the runner (`week1_baseline/bin/python/07_the_run_dsl`) is
    executable; `chmod +x` if not.
12. **Before any live spend**: mock-server verification reusing the step
    06 harness, adapted to call `boukensha.run(...)` as the entry point
    instead of constructing `Agent` directly — confirm: (a) a normal
    tool-call turn produces the same JSONL phase sequence as step 06; (b)
    `register_tools` raising *before* `Logger` is constructed doesn't
    crash on `logger.close()` in the `finally` (mirrors Ruby's
    `logger&.close` safe-navigation); (c) `Logger.subscribe` receives a
    copy of every event as it's written; (d) `Logger.turn` and the
    re-added `mud_*`/`LoopError` are present and callable even though
    unused by the shipped example.
13. Run `./week1_baseline/bin/python/07_the_run_dsl` **once** against the
    real fixture and compare against a single live run of
    `week1_baseline/bin/ruby/07_the_run_dsl`, per the same bounded-budget
    agreement as steps 05–06 — ask before spending this, same as before.
14. Exercise the non-Anthropic backends' dispatch through `run()` and the
    re-added `mud_*`/`LoopError`/`turn`/`subscribe` directly
    (`.venv/bin/python -c "..."`), since the shipped fixture only selects
    `anthropic` and never exercises any of these.
15. Port `README.md`: the real `Boukensha.run` signature (not Ruby's
    stale table), a before/after comparison (step 06's manual wiring vs.
    this step's one call), the `register_tools=` mechanism, and a
    Considerations section covering: the `instance_eval` translation
    choice, the re-added `mud_*`/`LoopError` (with `ITERATIONS.md`
    citations for what they're scaffolding), `turn`/`subscribe` as
    forward-looking dead code, the Ruby `||`/`||=` falsy-coercion
    translation care, and the Ruby README's own unreliability (wrong step
    number, fabricated `token_budget:`/`max_tokens:` params confirmed via
    `ITERATIONS.md` to be a future step's planned rename, not this step's
    reality).

## Open questions

Resolved during planning:

1. **How to translate `instance_eval(&block)`**, since Python has no way
   to rebind a plain callable's implicit `self` — **resolved:
   `register_tools=` keyword argument, a callable taking the `RunDSL`
   instance as its one explicit argument** (`register_tools=lambda dsl: dsl.tool(...)`),
   rather than a bare `block=` (to keep it distinct from `Registry.tool`'s
   own `block=` for the tool body itself, which means something
   different).

Decided without asking (precedent already answers these; noted here for
visibility, not as open forks):

2. **`RunDSL.tool`'s signature mirrors `Registry.tool`'s existing Python
   shape** (positional `description`, not keyword-only) — there's only
   one consistent choice once `Registry.tool`'s own established
   translation is taken as given.
3. **Re-adding `mud_host`/`mud_port`/`mud_username`/`mud_password` and
   `LoopError`** — not a preserve-vs-fix judgment call the way steps 03/
   05's discovered bugs were; the Ruby source genuinely re-added this
   dead code, `diff`-confirmed, and the port's whole methodology is to
   mirror the real diff, not editorialize about churn in the lesson's own
   history.
4. **`is not None` instead of `or`/truthiness for `run()`'s five
   default-fills** — direct consequence of Ruby's narrower falsy
   definition (`nil`/`false` only) vs. Python's broader one; there's one
   correct translation, not a style choice.
5. **Placement: `RunDSL` in `run_dsl.py`, `run()` in `__init__.py`** —
   mirrors Ruby's real file split (`lib/boukensha/run_dsl.rb` has only
   the class; `self.run` lives in `lib/boukensha.rb` itself) exactly, and
   sidesteps the circular-import question step 06 had to solve for
   `current_config`/`is_debug` (which lived in a leaf submodule reaching
   back up; `run()` doesn't).
