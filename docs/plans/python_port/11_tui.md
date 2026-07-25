# Python Port Plan — Step 11: A Terminal UI

## Scope

Port `week1_baseline/ruby/11_tui` to a new
`week1_baseline/python/11_tui`. Same as steps 00–10, this is a
self-contained copy of the `boukensha` package at this point in its
history, not a diff against `python/10_standard_tool_library`.

**This step wraps `Repl` in a full terminal UI.** Ruby builds it on
`charm` (bubbletea + lipgloss + bubbles — an actively-maintained,
integrated TUI ecosystem, itself a third-party FFI binding to Go
libraries; Ruby didn't build this from scratch either). Python has no
bindings to that specific ecosystem, so — per the user's explicit
choice — this port adopts **Textual**, a modern, reactive, async-native
Python TUI framework with direct equivalents for every piece this step
needs (see design mapping). This is the first step in the port to add a
genuinely new third-party runtime dependency beyond `PyYAML`/
`python-dotenv`.

`Repl` itself gets refactored the same way Ruby's did: `on_output`,
`handle_command`, `banner`, and a few readers become part of its public
surface so `Tui` can drive it without duplicating REPL logic, exactly
mirroring `repl.rb`'s change.

**No MUD-specific code changes are needed** (same as step 10) — the
agent's tools still come entirely from `mcp_servers:`, and this step's
`mud-manager` daemon is unchanged.

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `Gemfile`/`Gemfile.lock` | **changed** — adds `gem "charm"` | `requirements.txt` — adds `textual` |
| `boukensha.gemspec` | **changed** — adds `spec.add_dependency "charm"` | `pyproject.toml` — adds `textual` to `dependencies` |
| `lib/boukensha/version.rb` | **changed** — `"0.10.0"` → `"0.11.1"` | `boukensha/version.py` — `VERSION = "0.11.1"` |
| `lib/boukensha/tui.rb` | **new** — `Tui`: wraps `Repl`, four-zone bubbletea/lipgloss/bubbles display | `boukensha/tui.py` — new `Tui`/`BoukenshaApp` built on Textual |
| `lib/boukensha/repl.rb` | **changed** — `on_output`, public `handle_command`/`banner`, `logger`/`context`/`model`/`version` readers; `start`/`run_turn` route through `output()` | `boukensha/repl.py` — same refactor |
| `lib/boukensha.rb` | **changed** — `repl` gains `tui: true`, wraps the built `Repl` in `Tui.new(repl).start` when enabled | `boukensha/__init__.py` — `start_repl` gains `tui=True`, same wrapping |
| `lib/boukensha_loader.rb` | **changed** — adds `--no-tui` CLI flag, `Boukensha.repl(tui: !no_tui)` | `boukensha_loader.py` — adds `--no-tui` handling, `boukensha.start_repl(tui=not no_tui)` |
| `bin/boukensha` | byte-identical to step 10 (`diff` confirmed) | copy forward unchanged from `python/10_standard_tool_library` |
| `examples/example.rb` | **cosmetic only** — "Step 10" → "Step 11" comment, a note that this file is the one-shot demo and doesn't exercise the TUI | `examples/example.py` — same comment update, no functional change |
| `lib/boukensha/mcp/client.rb`, `tools/mcp.rb`, `config.rb`, `context.rb`, `registry.rb`, `run_dsl.rb`, `agent.rb`, `client.rb`, `logger.rb`, `errors.rb`, `tool.rb`, `message.rb`, `prompt_builder.rb`, `tasks/*.rb`, `backends/*.rb` | byte-identical to step 10 (`diff` confirmed) | copy forward unchanged from `python/10_standard_tool_library` |
| `prompts/system.md` | byte-identical to step 10 (`diff` confirmed) | copy forward unchanged |
| `test/*.rb`, `Rakefile`, `patches/`, `Gemfile.lock` native-extension pins | Ruby/native-gem-specific tooling — `patches/bubbletea/*` fixes a bug in the Ruby `bubbletea` gem's C extension specifically | no Python equivalent needed; not part of this port (same "no committed test suite" precedent as step 10) |
| `README.md` | Build/install, `Tui`/`Repl` docs, keyboard shortcuts, Technical Considerations | `README.md` — adapted; see design mapping for one stale-doc item found |

Runner already in place, no change needed: `week1_baseline/bin/python/11_tui`
(verify it's executable; `chmod +x` if not).

## Target layout

```
week1_baseline/python/11_tui/
  requirements.txt                 # adds textual
  pyproject.toml                   # adds textual to dependencies
  boukensha_loader.py               # adds --no-tui handling
  bin/
    boukensha                      # copied forward unchanged
  prompts/
    system.md                      # copied forward unchanged
  boukensha/
    __init__.py                    # start_repl gains tui=True
    version.py                     # "0.11.1"
    tui.py                         # new — Tui / BoukenshaApp (Textual)
    repl.py                        # on_output, handle_command, public banner/readers
    config.py                      # copied forward unchanged
    tool.py                        # copied forward unchanged
    message.py                     # copied forward unchanged
    context.py                     # copied forward unchanged
    errors.py                      # copied forward unchanged
    registry.py                    # copied forward unchanged
    prompt_builder.py               # copied forward unchanged
    client.py                      # copied forward unchanged
    logger.py                      # copied forward unchanged
    agent.py                       # copied forward unchanged
    run_dsl.py                     # copied forward unchanged
    mcp/
      __init__.py
      client.py                    # copied forward unchanged
    tools/
      __init__.py
      mcp.py                       # copied forward unchanged
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

- **Textual, not bubbletea/lipgloss/bubbles** (resolved with the user).
  Direct component mapping:

  | Ruby (charm) | Python (Textual) |
  |---|---|
  | `Bubbletea::Model` (`init`/`update`/`view`) | `textual.app.App` (`compose()`, reactive attributes, message handlers) |
  | `Bubbles::Viewport` (scrollable conversation) | `textual.widgets.RichLog` |
  | `Bubbles::TextArea` (single-line input) | `textual.widgets.Input` |
  | `Lipgloss::Style` (fg/bg/bold) | Textual CSS (`DEFAULT_CSS` class attribute) or Rich markup strings |
  | `Bubbletea.tick(...)` (spinner/elapsed re-render) | `self.set_interval(TICK_SECONDS, self._on_tick)` |
  | `Bubbletea::Runner.new(..., alt_screen:, input_timeout:, fps:).run` | `BoukenshaApp().run()` — Textual manages the alt-screen and its own render throttling internally; there's no direct knob to set, and none is needed |
  | `Thread.new { @repl.run_turn(input) }` | `self.run_worker(self._run_turn_worker, thread=True)` — Textual's explicit mechanism for running blocking sync code (this step's `Agent.run()`/`Client.call()` use `urllib`, not `asyncio`) off the event loop without freezing the UI |
  | `@events = Queue.new` + `logger.subscribe { |e| @events << e }`, drained on tick | `self._events = queue.Queue()`, `self._logger.subscribe(self._events.put)`, drained via non-blocking `get_nowait()` loop in the tick callback |

- **Esc does not interrupt an in-flight turn** (resolved with the user).
  Ruby's `@turn_thread.raise(Interrupt)` asynchronously injects an
  exception into the running turn's thread — Python's threading model has
  no safe equivalent for aborting an arbitrary running thread (there is
  no way to safely interrupt a blocking `urllib.request.urlopen()` call
  from outside the thread running it). Esc is accepted as a keypress but
  is a no-op while a turn is actively running; this is documented as a
  known, deliberate Python limitation in the ported README, not silently
  dropped or worked around with a fragile cooperative-cancellation
  scheme that still couldn't abort a request already in flight.

- **`Repl`'s refactor mirrors Ruby's exactly**: `on_output(callback)`
  replaces `puts`/`print` with routing through the callback when set (a
  private `_output(text)` helper checks `self._output_cb`, matching
  Ruby's `output(str)`); `handle_command(input)` becomes a public method
  returning `"quit"`, `"command"`, or `None` (Ruby's `:quit`/`:command`/
  `nil` — symbols become strings, matching this port's established
  convention; `None` for "not a recognized `/command`" matches Ruby's
  `case` falling through with no `else`, letting the caller send the text
  to the agent instead); `banner()` and read-only `logger`/`context`/
  `model`/`version` properties move from private/absent to public, since
  `Tui` needs to call `repl.banner()` directly and inspect the other four
  without going through the output-routing path at all.

- **`Boukensha.repl`'s `tui:` keyword and `defined?(Tui)` guard → `start_repl`'s
  `tui=True` and a plain `Tui is not None` check — but this doesn't
  provide real graceful degradation in either language, and the ported
  README should say so rather than imply otherwise.** Ruby's
  `require_relative "boukensha/tui"` at the bottom of `boukensha.rb` is
  unconditional — if `bubbletea`/`lipgloss`/`bubbles` aren't installed,
  that require raises immediately and `require "boukensha"` fails
  entirely (confirmed directly: this is exactly what happened earlier
  this session before those gems were installed). `defined?(Tui)` reads
  as if it enables a fallback path, but in the actual current code there
  is no scenario where `tui.rb`'s own top-level requires fail *without*
  taking down the whole module load first. The Python port mirrors this
  faithfully: `from .tui import Tui` is unconditional in
  `boukensha/__init__.py`, so a missing `textual` install fails the
  entire `import boukensha`, matching Ruby's real (not aspirational)
  behavior — not inventing a nicer optional-dependency story Ruby
  doesn't actually have.

- **`boukensha_loader.py`'s `--no-tui` handling is a direct translation**:
  `no_tui = "--no-tui" in sys.argv` (Ruby's `ARGV.delete("--no-tui")` also
  removes the flag from argv; Python can do the same via
  `sys.argv.remove("--no-tui")` inside the `if`, though nothing downstream
  re-parses `sys.argv` so removing it is cosmetic-only, matching Ruby),
  then `boukensha.start_repl(tui=not no_tui)`.

- **Ruby README stale-doc item found — and, per the user's explicit
  request, fixed as part of this plan rather than merely flagged.** The
  "Technical Considerations" section claims `MudManager::Session#login`
  now recognizes CircleMUD's `"You take over your own body, already in
  use!"` message the same way it recognizes `"Reconnecting."`, fixing the
  duplicate-session case. `grep` against the actual
  `week0_explore/mud_manager/lib/mud_manager/session.rb` shows no such
  pattern anywhere — `login` only ever matches
  `/Welcome|Reconnecting|Wrong password/i`. This is the same
  stale-README pattern found repeatedly in earlier steps (02, 04, 05, 06,
  07, 08), just this time describing a fix that was never actually made
  rather than a feature that was never actually added.

  This is a gap in the *shared*, path-referenced `week0_explore/mud_manager`
  library, not per-step code — both the Ruby and Python ports of step 11
  spawn the same external `mud-manager` daemon, so fixing it once here
  benefits both languages identically, the same way this session's
  earlier `Session#login` drain-race fix and the `look`/`target: "room"`
  daemon fix already did for step 10. The fix: add the `"already in use"`
  pattern to `login`'s status check and treat it exactly like
  `"Reconnecting"` (already in-world, skip the main menu, just
  `drain_settled`) rather than falling through to the `Welcome` branch
  (which would wrongly try to navigate a main menu that was never shown):
  ```ruby
  output = self.read_until(/Welcome|Reconnecting|already in use|Wrong password/i)
  if output =~ /Reconnecting|already in use/i
    drain_settled
  elsif output =~ /Welcome/i
    ...
  ```
  This is a `week0_explore/mud_manager` change (task 0 below), applied
  once, ahead of the actual Python porting work — not a per-language
  duplication, and not something the Python port's own code needs to
  know or care about (the Python side never reimplements MUD session
  logic at all, per step 10's design).

## Config directory & schema

Unchanged from step 10 — same `.boukensha/` fixture, same `mcp_servers:`
resolution.

## Task list

0. **Fix the shared `MudManager::Session#login`** (`week0_explore/mud_manager/lib/mud_manager/session.rb`)
   to actually recognize `"already in use"` alongside `"Reconnecting"`,
   per the design mapping above — this makes the Ruby step-11 README's
   existing claim true instead of stale, and benefits both the Ruby and
   Python ports identically since both spawn the same daemon. Verify by
   deliberately triggering a duplicate login (open one session, then log
   in again with the same credentials while the first is still open) and
   confirming the second connection proceeds straight into the game
   instead of stalling until the login timeout. This is a prerequisite,
   not a step-11-Python-specific task — do it once, ahead of task 1.
1. Create `week1_baseline/python/11_tui/` skeleton (dirs above).
2. Copy forward unchanged from `python/10_standard_tool_library`:
   `config.py`, `tool.py`, `message.py`, `context.py`, `errors.py`,
   `registry.py`, `prompt_builder.py`, `client.py`, `logger.py`,
   `agent.py`, `run_dsl.py`, `mcp/client.py`, `tools/mcp.py`,
   `tasks/player.py`, `tasks/base.py`, `backends/base.py`, all 5
   `backends/*.py`, `prompts/system.md`, `bin/boukensha`.
3. Update `version.py`: `VERSION = "0.11.1"`.
4. Update `repl.py` per the design mapping: add `_output_cb`/`on_output`,
   make `banner` public (`banner(self)`, no leading underscore), add
   public `handle_command(self, input_text)` returning `"quit"`/
   `"command"`/`None`, add read-only `logger`/`context`/`model`/`version`
   properties, route `start()`/`_run_turn` (rename to match Ruby's now
   -public `run_turn`, since `Tui` calls it directly) through
   `_output()`.
5. Write `boukensha/tui.py`: `Tui` class wrapping a `Textual` `App`
   subclass (or a single class serving both roles, whichever reads
   cleaner in Python — decide during execute) per the design mapping:
   `compose()` yielding the conversation `RichLog`, a progress `Static`,
   the prompt `Input`, and a status `Static`; `on_mount` registers
   `repl.on_output(...)`, `logger.subscribe(...)`, and the tick interval;
   key handling for `ctrl+c`/`ctrl+d` (quit), `escape` (no-op during a
   turn, per the resolved fork), `ctrl+l` (clear), `pageup`/`pagedown`
   (scroll the RichLog), `enter` (submit, via `Input.Submitted`);
   `run_worker(..., thread=True)` for turns; the same token/spinner/
   elapsed-time bookkeeping as Ruby's `@live` hash (as instance attributes
   or a small dataclass).
6. Update `boukensha/__init__.py`: `start_repl` gains `tui=True`; after
   building `Repl`, wrap it in `Tui(repl).start()` when `tui` is true
   (and `Tui` is available — see design mapping on why this check doesn't
   provide real degradation, mirroring Ruby faithfully anyway), else call
   `repl.start()` directly.
7. Update `boukensha_loader.py`: add `--no-tui` argv handling, pass
   `tui=not no_tui` to `boukensha.start_repl(...)`.
8. Port `examples/example.py`: update the "Step 10" → "Step 11" comment
   and the note that this file doesn't exercise the TUI; no functional
   change.
9. Update `requirements.txt`: add `textual`. Update `pyproject.toml`:
   bump `description` to reference Step 11; add `textual` to
   `dependencies` (this step's `[project.scripts]`/`py-modules` entries
   for `boukensha_loader` carry forward unchanged from step 10).
10. Install this step editable into the shared root `.venv`
    (`pip install -e week1_baseline/python/11_tui`), repointing from
    step 10 — this also pulls in `textual` per `dependencies`.
11. Verify the runner (`week1_baseline/bin/python/11_tui`) and
    `bin/boukensha` are executable; `chmod +x` if not.
12. **Before any live spend**: verify the TUI's non-agent behavior first
    (no API key, no live MUD needed) — launching, rendering the four
    zones, `ctrl+c`/`ctrl+d` quitting cleanly, `ctrl+l` clearing, the
    status line showing correct version/model/tool-count, `/help`
    /`/quiet`/`/loud` routing through `on_output` correctly. Textual
    ships a headless test/pilot mode (`App.run_test()`) that can drive
    keypresses and inspect widget state without a real terminal — use it
    to check this mechanically rather than only by eye.
13. Exercise one real turn through the TUI (this is the same live-budget
    category as steps 05–10: a real Anthropic API call, same MCP
    daemon/MUD connection as step 10) — confirm the progress line updates
    from `Logger` events in real time, the conversation log shows the
    final response, and the status line's context-token count updates
    after. Ask before spending this, same as every prior step.
14. Confirm `--no-tui` still produces the identical plain-REPL behavior
    step 10 had (this is the easy regression to check: the refactored
    `Repl` must behave byte-for-byte the same when driven by its own
    `start()` loop as it did before the `on_output`/`handle_command`
    refactor).
15. Port `README.md`: `Tui` overview and the four-zone diagram, the
    keyboard shortcut table, the `tui=True`/`--no-tui` option, the
    `Repl` refactor's new public surface, and a Considerations section
    covering: the Textual-vs-charm framework choice, the Esc-interrupt
    limitation, the `defined?(Tui)`-doesn't-really-degrade point, and the
    stale README claim about `Session#login`'s "already in use" handling
    (documented as still-not-actually-fixed, out of scope for this port).

## Open questions

Resolved during planning:

1. **Which Python TUI framework replaces bubbletea/lipgloss/bubbles**,
   since Python has no bindings to that specific ecosystem — **resolved:
   Textual**, for its direct equivalents to every piece this step needs
   (RichLog, Input, CSS styling, thread-based workers, set_interval) and
   its architectural closeness to bubbletea's reactive model/update/view
   loop.
2. **How Esc should behave, given Python's threading model can't safely
   interrupt an arbitrary running thread the way Ruby's `Thread#raise`
   can** — **resolved: best-effort no-op during an active turn**,
   documented as a known Python limitation rather than built around with
   a cooperative-cancellation mechanism that still couldn't abort an
   in-flight blocking HTTP call.

Decided without asking (precedent already answers these; noted here for
visibility, not as open forks):

3. **`Repl`'s `on_output`/public `handle_command`/`banner` refactor** —
   a direct, unambiguous translation of Ruby's own refactor; no
   alternative shape under consideration.
4. **The stale `Session#login` "already in use" README claim** — per the
   user's explicit follow-up request, this is now an actual fix (task 0)
   rather than just a flagged-and-left gap. It's still a
   `week0_explore/mud_manager` change, not Python-port-specific code, but
   it's in scope for this plan to *do*, not merely note, since both
   language ports depend on the same shared daemon.
