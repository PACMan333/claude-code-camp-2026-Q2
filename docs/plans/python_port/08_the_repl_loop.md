# Python Port Plan — Step 08: The REPL Loop

## Scope

Port `week1_baseline/ruby/08_the_repl_loop` to a new
`week1_baseline/python/08_the_repl_loop`. Same as steps 00–07, this is a
self-contained copy of the `boukensha` package at this point in its
history (mirroring Ruby's per-step-folder duplication), not a diff
against `python/07_the_run_dsl`.

The runner already exists and defines the contract:
`week1_baseline/bin/python/08_the_repl_loop` does

```bash
cd week1_baseline/python/08_the_repl_loop
"$REPO_ROOT/.venv/bin/python" examples/example.py
```

— same shared repo-root `.venv` as steps 00–07.

**This step adds `Boukensha::Repl`**: an interactive session loop that
wraps the same primitives as `Boukensha.run`, but stays alive — reading a
task from stdin, running the agent, printing the reply, and looping back
— instead of running once. `Context` is shared across every turn so
conversation history accumulates naturally. Supporting changes: `Agent`
now persists its final reply back into `Context` (needed so a REPL's next
turn sees what the agent said last turn — a one-shot `Boukensha.run`
never needed this, since its `Context` is discarded immediately after);
`Config` gains a third directory-resolution tier (a `.boukensha/` in the
current working directory, checked before the `~/.boukensha` default);
`Client` gives 401 responses a friendlier error message; `Context` gains
`clear_messages()` for the REPL's `/clear` command; a new `VERSION`
constant.

**This step's `Client`/`Agent` still make real, live, billed HTTP calls**
per turn (inherited, not new). Per the precedent from steps 05–07:
mock-first verification during execute, and ask before spending the live
budget on any comparison run — a REPL is inherently multi-turn/
open-ended, so "one bounded live run" here means one short, scripted
multi-turn session, not an actual open-ended interactive session.

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `Gemfile` | unchanged from step 07 (`diff` confirmed) | `requirements.txt` (unchanged) |
| `lib/boukensha.rb` | **changed** — requires `boukensha/version`; adds `self.repl(...)`, the interactive entry point; requires `boukensha/repl` | `boukensha/__init__.py` — adds `start_repl()` (see design mapping for the naming fork), imports `VERSION` |
| `lib/boukensha/version.rb` | **new** — `Boukensha::VERSION = "0.8.0"` | `boukensha/version.py` — new, `VERSION = "0.8.0"` |
| `lib/boukensha/repl.rb` | **new** — `Boukensha::Repl`: the interactive loop, built-in commands, banner, per-turn `Agent` construction | `boukensha/repl.py` — new `Repl` class |
| `lib/boukensha/agent.rb` | **changed** — all three return paths (`run`'s normal end_turn, `_wrap_up`'s success path, `_wrap_up`'s `rescue ApiError` path) now call `@context.add_message(:assistant, text)` before returning | `boukensha/agent.py` — same three call sites gain `self._context.add_message("assistant", text)` |
| `lib/boukensha/client.rb` | **changed** — a 401 response now raises a specific `"authentication failed (401) — check your API key"` `ApiError` instead of falling through to the generic status/body message | `boukensha/client.py` — same special case added to the `HTTPError` handler |
| `lib/boukensha/config.rb` | **changed** — `resolve_dir` becomes 3-tier: (1) `BOUKENSHA_DIR` env var, (2) `.boukensha/` in the current working directory (**new**), (3) `~/.boukensha` default | `boukensha/config.py` — `_resolve_dir` gains the same middle tier |
| `lib/boukensha/context.rb` | **changed** — adds `clear_messages!` (wipes `@messages`, keeps tools/system); trailing-newline fix | `boukensha/context.py` — adds `clear_messages(self)` |
| `lib/boukensha/errors.rb`, `logger.rb`, `run_dsl.rb`, `registry.rb`, `tool.rb`, `message.rb`, `prompt_builder.rb`, `backends/*.rb` (all 5 + `base.rb`), `tasks/base.rb`, `tasks/player.rb` | byte-identical to step 07 (`diff` confirmed) — note `logger.rb`'s `turn` method already exists since step 07 (this step's own README claims it's new "this step" and that it "prints a `╔══ turn N ══╗` header," neither of which is true — see design mapping) | copy forward unchanged from `python/07_the_run_dsl` |
| `prompts/system.md` | byte-identical to step 07 (`diff` confirmed) | copy forward unchanged |
| `examples/example.rb` | Prints config; registers `read_file`/`list_directory` against `base_dir` (the sibling `07_the_run_dsl` step folder, "a good playground since it already has source files to read"); calls `Boukensha.repl do ... end` — notably does **not** set `BOUKENSHA_DIR` itself (see design mapping) | `examples/example.py` — same shape, **does** set `BOUKENSHA_DIR` (see design mapping for why) |
| `README.md` | Comparison table, built-in commands, banner example, "Running it" instructions, Technical Considerations | `README.md` — rewritten from the real source; the Ruby README here is unusually unreliable (see design mapping) |

Runner already in place, no change needed: `week1_baseline/bin/python/08_the_repl_loop`
(verify it's executable; `chmod +x` if not).

## Target layout

```
week1_baseline/python/08_the_repl_loop/
  requirements.txt
  pyproject.toml
  prompts/
    system.md                      # copied forward unchanged
  boukensha/
    __init__.py                    # adds start_repl(), VERSION
    version.py                     # new
    config.py                      # 3-tier _resolve_dir
    tool.py                        # copied forward unchanged
    message.py                     # copied forward unchanged
    context.py                     # adds clear_messages()
    errors.py                      # copied forward unchanged
    registry.py                    # copied forward unchanged
    prompt_builder.py               # copied forward unchanged
    client.py                      # adds 401 special case
    logger.py                      # copied forward unchanged
    agent.py                       # persists final reply to Context
    run_dsl.py                     # copied forward unchanged
    repl.py                        # new — Repl
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

- **`self.repl` → `start_repl()`, not `repl()`** (resolved with the user).
  `boukensha/repl.py` is a submodule containing `Repl`, imported via
  `from .repl import Repl` — the same shape of collision step 06 resolved
  for `config()`/`config.py` (the import binds the `boukensha.repl`
  attribute to the submodule; a later `def repl():` would reassign/shadow
  it). Lower practical risk than the `config` case (nothing in this
  codebase does `from boukensha.repl import Repl` or
  `boukensha.repl.Repl(...)` — `Repl` is only ever constructed internally
  by the entry-point function), but resolved the same way regardless:
  don't rely on "nothing needs it today" holding forever.

- **`Repl#start`'s input loop: `input(PROMPT)` + `except EOFError`, not
  `print`+flush+`sys.stdin.readline()`.** Ruby's `print PROMPT; $stdout.flush; input = $stdin.gets; break unless input`
  is three steps because `gets` takes no prompt argument and returns
  `nil` at EOF. Python's `input(PROMPT)` does the prompt-print-and-flush
  in one call (standard library behavior) and raises `EOFError` instead
  of returning `None` — so the loop becomes
  `try: line = input(PROMPT) except EOFError: break`. Ruby's
  `input.chomp.strip` becomes just `.strip()`, since `input()` already
  excludes the trailing newline `gets` would have included.

- **`Repl._run_turn`'s Ruby method-level `rescue LoopError`/`rescue ApiError`
  must wrap the entire method body in Python, not just the `agent.run()`
  call** — same "whole-method rescue" precision already required for
  step 06's `Logger#first_integer`. Ruby's implicit per-method
  begin/rescue means a `LoopError`/`ApiError` raised by
  `Agent.new(...)`, `context.add_message(...)`, or `agent.run()` are all
  caught alike; the Python translation wraps the whole `_run_turn` body in
  one `try`/`except (LoopError, ApiError)` pair (two `except` clauses, to
  print the two different messages Ruby's two `rescue` clauses print).

- **`self.repl`'s Ruby method-level `rescue Interrupt`/`ensure` also spans
  the *entire* method, wider than `self.run`'s existing `ensure`-only
  scope needed in step 07.** Step 07's `run()` only needed a
  `try/finally` (no `except`), so where the `try` started didn't matter
  behaviorally — `logger.close()` in `finally` is a safe no-op if
  `logger` is still `None`, regardless of how early an exception fired.
  This step adds an actual `except KeyboardInterrupt` (Python's
  `Interrupt` equivalent) alongside it, and *that* needs to actually catch
  a Ctrl-C from anywhere in the method — including during config/context/
  backend construction, before `Logger`/`Repl` exist — to match Ruby's
  real behavior (a whole-method `rescue`/`ensure` with no explicit
  `begin`). So `start_repl()`'s `try` must start at the top of the
  function body (right after the `logger = None` sentinel), not partway
  through like `run()`'s did:
  ```python
  def start_repl(...):
      logger = None
      try:
          cfg = current_config()
          ...  # everything: settings resolution, Context/Registry/backend
               # construction, register_tools, Logger construction, Repl
               # construction and .start()
      except KeyboardInterrupt:
          print("\nInterrupted.")
      finally:
          if logger is not None:
              logger.close()
  ```

- **`Agent` persists its final reply into `Context` on all three exit
  paths, not just the happy path** — `run()`'s normal `end_turn` return,
  `_wrap_up`'s successful wind-down, and `_wrap_up`'s `except ApiError`
  fallback message all now call `self._context.add_message("assistant", text)`
  (or the fallback `msg`) immediately before returning. This is what lets
  a REPL's next turn see what the agent said last turn — a one-shot
  `Boukensha.run`/`start_repl` caller's `Context` was always discarded
  right after, so this never mattered before this step.

- **`Client`'s 401 special case is a straightforward addition to the
  existing `except urllib.error.HTTPError` handler, positioned before the
  generic raise** — 401 isn't in `RETRYABLE_STATUS_CODES` either language
  ever had, so it already falls straight through to the final raise on
  the first attempt; this just gives that specific code a clearer
  message:
  ```python
  except urllib.error.HTTPError as e:
      if e.code in RETRYABLE_STATUS_CODES and attempts <= MAX_RETRIES:
          time.sleep(self._retry_delay(attempts))
          continue

      if e.code == 401:
          raise ApiError("authentication failed (401) — check your API key") from e

      body = e.read().decode("utf-8", errors="replace")
      raise ApiError(...) from e
  ```

- **`Config._resolve_dir` gains a middle tier, `Path.cwd() / ".boukensha"`,
  checked before the `~/.boukensha` default** — direct translation of
  Ruby's `Dir.pwd`/`Pathname#directory?` to `Path.cwd()`/`Path.is_dir()`.
  This is what lets a future `boukensha` CLI (foreshadowed for step 09 in
  `ITERATIONS.md`) pick up a project-local `.boukensha/` when run from
  inside that project, without needing `BOUKENSHA_DIR` set explicitly.
  The existing top/bottom tiers keep their established Python idiom
  (plain truthiness via `os.environ.get(...)`/`or`, matching how
  `_resolve_dir` already worked before this step — not switched to
  `is not None`, since this function's existing style already predates
  and isn't part of step 07's `run()`/`repl()` default-fill precision
  concern).

- **`Context.clear_messages!` → `clear_messages(self)`** — drops the
  bang per the established convention, direct translation
  (`self._messages = []`).

- **`VERSION` lives in its own `boukensha/version.py`, matching Ruby's
  separate `lib/boukensha/version.rb`** — `VERSION = "0.8.0"`, imported
  into `__init__.py` and re-exported, kept as the literal all-caps
  constant name (not `__version__`) for fidelity, matching this port's
  general bias toward Ruby's literal names where nothing else forces a
  change.

- **`example.py` needs an explicit `BOUKENSHA_DIR` fallback that
  `example.rb` doesn't have — because the two runner scripts mask path
  resolution asymmetrically, same root cause as step 07's off-by-one
  finding, different shape.** Ruby's `example.rb` sets no `BOUKENSHA_DIR`
  at all this step; it doesn't need to, because
  `week1_baseline/bin/ruby/08_the_repl_loop` (the real entry point)
  `export`s the correct value before invoking `ruby`. The **Python
  runner, `week1_baseline/bin/python/08_the_repl_loop`, does not export
  it** — it never has, in any step — so every prior Python `example.py`
  (steps 05–07) has carried its own `os.environ.setdefault("BOUKENSHA_DIR", ...)`
  line to compensate. A literal translation of step 08's `example.rb`
  (which has no such line) would leave the Python example unable to find
  `settings.yaml`/`.env`, falling through `Config`'s new tier 2 (no
  `.boukensha/` inside `python/08_the_repl_loop`) to tier 3
  (`~/.boukensha`, which doesn't exist on this machine). Keep the same
  5-`.parent()` resolution steps 05–07 already used correctly.

- **The Ruby README for this step is, again, unusually unreliable —
  worth citing specifically, not just noting in passing.** It's titled
  "Step 7" (off by one, same mistake as step 07's own README made about
  itself); its "Running it" section says `cd 07_the_repl_loop` and
  `ruby examples/step7.rb` — neither directory nor file exists (the real
  ones are `08_the_repl_loop` and `examples/example.rb`); its sample
  banner output
  (`║  BOUKENSHA REPL  —  MUD assistant    ║`) doesn't match what the
  real `banner` method actually renders at all (the real one shows a
  version number, config path, and provider status, not that text) —
  confirmed by reading `repl.rb`'s `banner` method directly. Its "Changes
  from step 6" section credits `Logger#turn` to this step ("New method
  that prints a `╔══ turn N ══╗` header") — but `diff` confirms
  `logger.rb` is byte-identical to step 07, where `turn` was already
  added (this port's own step-07 plan documented it then as
  forward-looking, unused scaffolding) — and `turn` only ever writes a
  JSONL log line, it has never printed anything to the console in either
  step. The ported README documents only what's real and source-verified.

- **The Ruby README's own "Technical Considerations" section flags two
  things worth preserving verbatim as Python Considerations, not
  re-discovering independently.** First: *"We need to determine [if]
  quiet and loud are legacy logging or if they actually provided[d]
  detail[ed] logs"* — confirmed by `grep`: `Boukensha.quiet?`/`is_quiet`
  is checked nowhere in `logger.rb`/`agent.rb`; only `Boukensha.debug?`
  gates anything (`Logger#raw`). The REPL's `/quiet`/`/loud` commands are
  genuinely no-ops today, by the Ruby authors' own admission — preserve
  faithfully (`boukensha.quiet()`/`loud()` still get called, still do
  nothing observable), don't silently wire them up to something real.
  Second: *"It looks like [the] REPL loop we initialize on every turn an
  agent... it seems like we should initialize only once"* — confirmed:
  `Repl#run_turn` really does construct a fresh `Agent.new(...)` every
  turn while reusing `context`/`registry`/`builder`/`client`/`logger`
  across turns. This is a self-acknowledged, not-yet-fixed wart in the
  Ruby source (same "preserve + document, don't silently fix" policy as
  step 04's stateful-`Client` wrinkle) — the Python `Repl._run_turn`
  builds a fresh `Agent(...)` every call too, matching exactly.

## Config directory & schema

**Changed this step**: `Config._resolve_dir` gains the cwd-`.boukensha`
middle tier described above. The shipped fixture and example never
exercise it directly (the example always resolves `BOUKENSHA_DIR`
explicitly, tier 1), so this needs a manual check during execute
(constructing a `Config` from a cwd that has its own `.boukensha/` with
no `BOUKENSHA_DIR` env var set, confirming tier 2 wins over tier 3).

## Task list

1. Create `week1_baseline/python/08_the_repl_loop/` skeleton (dirs above).
2. Copy forward unchanged from `python/07_the_run_dsl`: `tool.py`,
   `message.py`, `errors.py`, `registry.py`, `prompt_builder.py`,
   `logger.py`, `run_dsl.py`, `tasks/player.py`, `tasks/base.py`,
   `backends/base.py`, all 5 `backends/*.py`, `prompts/system.md`.
3. Write `boukensha/version.py`: `VERSION = "0.8.0"`.
4. Update `config.py`: rewrite `_resolve_dir` to the 3-tier form (env var
   → cwd `.boukensha/` → `~/.boukensha`), keeping the existing
   truthiness-based style (not `is not None`) since that's this
   function's own pre-existing idiom.
5. Update `context.py`: add `clear_messages(self)`.
6. Update `client.py`: add the 401 special case to the `HTTPError`
   handler, before the generic raise.
7. Update `agent.py`: add `self._context.add_message("assistant", text)`
   (or the fallback message) immediately before each of the three
   `return` statements in `run()`/`_wrap_up`.
8. Write `boukensha/repl.py`: `Repl` class — `PROMPT`, `HELP`,
   `__init__` (same kwargs as Ruby, `self._turn = 0`), `start` (banner,
   `input(PROMPT)`/`EOFError` loop, `/exit`/`/quit`/`/help`/`/quiet`/
   `/loud`/`/clear` dispatch, else `_run_turn`), `_banner` (exact ASCII
   box + padding formula), `_run_turn` (whole-body
   `try/except (LoopError, ApiError)`, fresh `Agent(...)` per turn).
9. Update `__init__.py`: import `VERSION` from `.version` and `Repl` from
   `.repl`; add `start_repl()` per the design mapping (whole-body
   `try/except KeyboardInterrupt/finally`); add `VERSION` and
   `start_repl` to `__all__`.
10. Port `examples/example.py`: add the `os.environ.setdefault("BOUKENSHA_DIR", ...)`
    fallback (per design mapping — needed even though `example.rb`
    doesn't have one); print the config banner; `base_dir` pointing at
    the sibling `python/07_the_run_dsl` folder; `register_tools=`
    registering `read_file`/`list_directory` (note: `list_directory`'s
    result is `sorted(...)` this step, matching Ruby's new `.sort` call —
    confirm this against the real source when writing it); call
    `boukensha.start_repl(register_tools=register)`.
11. Reuse `requirements.txt` (unchanged) and `pyproject.toml` from the
    step 07 pattern, bumping `description` to reference Step 8.
12. Install this step editable into the shared root `.venv`
    (`pip install -e week1_baseline/python/08_the_repl_loop`), repointing
    from step 07.
13. Verify the runner (`week1_baseline/bin/python/08_the_repl_loop`) is
    executable; `chmod +x` if not.
14. **Before any live spend**: mock-server verification, scripting stdin
    input (e.g. feeding a sequence of lines via a pipe or by monkeypatching
    `builtins.input`) to exercise, against a mock HTTP server: (a) a
    multi-turn conversation where the second turn's prompt sent to the
    API includes the first turn's assistant reply (proving the
    `Context.add_message("assistant", ...)` persistence works); (b)
    `/clear` actually wipes history (a turn after `/clear` doesn't include
    pre-clear messages); (c) `/quiet`/`/loud` don't change what gets
    logged (confirming the Ruby authors' own observation); (d) `/help`,
    `/exit`, `/quit`, and EOF (simulated) all behave as expected without
    invoking the agent; (e) a 401 mock response produces the friendlier
    "authentication failed" message; (f) `Config`'s new cwd-tier
    resolution picks a local `.boukensha/` over `~/.boukensha` when no
    `BOUKENSHA_DIR` env var is set.
15. Run `./week1_baseline/bin/python/08_the_repl_loop` **once**, scripted
    with a short, predetermined multi-turn input sequence (not an
    open-ended manual session), and compare against one similarly
    scripted live run of `week1_baseline/bin/ruby/08_the_repl_loop`, per
    the same bounded-budget agreement as steps 05–07 — ask before
    spending this.
16. Exercise the non-Anthropic backends' dispatch through `start_repl()`
    and the `/quiet`/`/loud` no-op confirmation directly
    (`.venv/bin/python -c "..."`), since the shipped fixture only selects
    `anthropic` and the example never toggles quiet mode.
17. Port `README.md`: the real `Boukensha.repl`/`start_repl` signature and
    built-in commands (not the Ruby README's mistitled/mislabeled
    version), the real banner shape (from `repl.py`'s actual `_banner`
    method, not the README's fabricated sample), and a Considerations
    section covering: the `start_repl`/submodule naming fork, the
    whole-method `except`/`finally` scope precision, the `example.py`
    `BOUKENSHA_DIR` asymmetry (grouped with step 07's related finding),
    the Ruby README's specific unreliability (wrong step number, wrong
    paths, fabricated banner text, misattributed `Logger#turn`), and the
    two carried-forward Ruby-authors'-own "Technical Considerations"
    (dead `quiet`/`loud`, per-turn `Agent` reconstruction).

## Open questions

Resolved during planning:

1. **Naming the `Boukensha.repl` entry point in Python**, given
   `boukensha/repl.py` is already an importable submodule (same shape as
   step 06's `config()`/`config.py` fork, though lower practical risk
   since nothing here does attribute-style access to the submodule) —
   **resolved: `start_repl()`**, not `repl()`, consistent with not
   relying on "nothing needs the submodule attribute today" holding
   forever.

Decided without asking (precedent already answers these; noted here for
visibility, not as open forks):

2. **`input(PROMPT)` + `except EOFError`** instead of a manual
   print/flush/readline sequence — there's one clearly better Python
   idiom here, not a stylistic fork.
3. **Widening `start_repl()`'s `try` to the whole function body**, unlike
   `run()`'s narrower placement in step 07 — a direct consequence of this
   step adding an actual `except KeyboardInterrupt` clause (placement
   matters for `except`, unlike the placement-insensitive `finally`-only
   case `run()` had).
4. **Preserving the two Ruby-authors'-acknowledged quirks (`quiet`/`loud`
   as dead flags; a fresh `Agent` built every REPL turn)** — the Ruby
   README's own "Technical Considerations" section already settles
   preserve-vs-fix here explicitly ("We are not fixing these now... just
   making note of things we observed that might need fixing"), so this
   isn't a fresh judgment call the way steps 02/03/05's discovered bugs
   were — the source itself already decided.
