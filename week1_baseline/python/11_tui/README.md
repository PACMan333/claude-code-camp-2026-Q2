# 11 · A Terminal UI (Python port)

Python port of `week1_baseline/ruby/11_tui`. Boukensha now ships a full
terminal UI (TUI) built on [Textual](https://textual.textualize.io/). The
plain REPL is still there and can be selected with `tui=False` (or the
`--no-tui` CLI flag).

The standard tool library is still **MCP** — boukensha ships no tools of
its own. Every tool the agent can call comes from an MCP server declared
in `settings.yaml`; swapping what the agent can do is a config edit, not
a code change. Everything from step 10 (`boukensha.mcp.Client`,
`boukensha.tools.mcp`, `mcp_servers:` config) is unchanged here — see
`python/10_standard_tool_library/README.md` for that material. This
README covers only what step 11 adds.

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/11_tui/requirements.txt
.venv/bin/pip install -e week1_baseline/python/11_tui
```

`requirements.txt`/`pyproject.toml` add one new dependency: `textual`. It
is the only genuinely new third-party runtime dependency this port has
needed — every prior step's dependencies (`PyYAML`, `python-dotenv`) were
thin config-loading libraries; Textual is a full TUI framework.

This step is a self-contained copy of the `boukensha` package.
Everything except `version.py`, `repl.py`, `tui.py` (new),
`__init__.py`, `boukensha_loader.py`, and the packaging files is copied
forward unchanged from `python/10_standard_tool_library`.

## What's new

### `boukensha.tui.Tui`

Wraps a `Repl` instance and replaces its raw `print()`/`input()` I/O with
a structured four-zone display:

```
┌──────────────────────────────────────────────┐
│  conversation viewport (scrollable)           │
├──────────────────────────────────────────────┤
│  ⟳ live progress line (hidden when idle)     │
├──────────────────────────────────────────────┤
│  boukensha> input box                         │
├──────────────────────────────────────────────┤
│  status line (always-on)                      │
└──────────────────────────────────────────────┘
```

The **progress line** shows a spinner, current action, iteration counter
(`n/MAX`), elapsed seconds, token counts (↑ in / ↓ out), and tool call
count while the agent is running. When idle it shows context usage and
turn count.

The **status line** always shows: version · model · context tokens used
· registered tool count · wall-clock time.

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `Enter` | Submit input or slash command |
| `Esc` | No-op — see Considerations below |
| `Ctrl+L` | Clear conversation history |
| `PgUp` / `PgDn` | Scroll conversation viewport |
| `Ctrl+C` / `Ctrl+D` | Quit |

The agent runs on a background worker thread (`App.run_worker(...,
thread=True)`) so the UI stays responsive during long turns.

### `boukensha.start_repl` — new `tui=` keyword

```python
boukensha.start_repl(tui=True)    # default -- launches the Textual TUI
boukensha.start_repl(tui=False)   # falls back to the plain terminal REPL
```

The `--no-tui` CLI flag (handled by `boukensha_loader.py`) sets
`tui=False` from the command line.

### `Repl` refactored for composability

`Repl` no longer hard-codes `print()`/`input()`. Three methods are now
public so `Tui` (or any other front-end) can drive it:

| Method | Purpose |
|--------|---------|
| `on_output(callback)` | Route all REPL output through a callback instead of stdout |
| `handle_command(input_text)` | Process a slash command; returns `"quit"`, `"command"`, or `None` |
| `run_turn(input_text)` | Run one agent turn and route the result through `on_output` |

`banner()`, and read-only `logger`/`context`/`model`/`version`
properties, are also part of the public surface `Tui` uses.

### `Logger.subscribe`

```python
logger.subscribe(lambda event: ...)
```

Every structured log event (`iteration`, `tool_call`, `tool_result`,
`response`, etc.) is now broadcast to all registered subscribers as well
as being written to the JSONL file. `Tui` uses this to update the live
progress line in real time without polling — it drains a `queue.Queue`
on every `set_interval` tick.

## Run the demo

The TUI is interactive, so it's run via the global `boukensha` console
script rather than `examples/example.py` (that file is the one-shot
`boukensha.run` demo, carried over unchanged — it doesn't exercise the
TUI).

```bash
# Offline, no API key, no live MUD -- uses the daemon's built-in fake MUD:
python examples/mcp_mud_demo.py --dry

# launches the Textual TUI:
BOUKENSHA_DIR=/path/to/.boukensha BOUKENSHA_PATH=~/Sites/boukensha/week1_baseline/python/11_tui .venv/bin/boukensha

# plain REPL (no textual rendering, just print()/input()):
BOUKENSHA_PATH=~/Sites/boukensha/week1_baseline/python/11_tui .venv/bin/boukensha --no-tui
```

```bash
./week1_baseline/bin/python/11_tui --no-tui
```

## Considerations

**Esc cannot interrupt a running turn — a deliberate, documented gap, not
a silent one.** Ruby's Esc handler does `@turn_thread.raise(Interrupt)`,
asynchronously injecting an exception into the turn's thread to abort it
mid-flight, including mid-HTTP-call. Python's threading model has no safe
equivalent of `Thread#raise` for interrupting an arbitrary running
thread — there is no way to safely abort a blocking `urllib` call from
outside the thread running it, short of a fragile cooperative-cancellation
scheme that still couldn't abort a request already in flight. Esc is
accepted as a keypress but is a no-op while a turn is active; this is
called out in the TUI's own module docstring, not just here.

**A real Textual footgun found and fixed during headless verification:
never name an instance attribute `_context`.** The first draft of `Tui`
did `self._context = repl.context` in `__init__`. `textual.app.App`
already defines a `_context()` contextmanager method used throughout its
own core event/message-processing loop; assigning a plain attribute of
the same name silently shadows it — no exception, no warning, the app
just hangs forever on the very first `run_test()`/mount, because
Textual's internal calls to `self._context()` are now calling a
`Context` instance instead of the real method. Cost about half an hour to
isolate (via a bisection: trivial `App` subclass with identical
CSS+`compose()` mounted fine; only adding the real `Tui.__init__` back in
reproduced the hang). Fixed by renaming to `self._ctx`. Worth knowing if
you ever add attributes to a Textual `App`/`Widget` subclass: check the
base class doesn't already use the name for something internal — Textual
doesn't guard against this the way Python's own `__slots__` would.

**A second bug found the same way: don't reuse the Logger's own event
phase names for your own synthetic events.** `Tui`'s worker-thread
completion signal was first named `{"phase": "turn_end"}` — but
`boukensha.logger.Logger` already emits a *real* `turn_end` event (from
`Agent.run()`, once per turn, via `logger.turn_end(reason=..., ...)`).
Since both events land in the same subscriber queue and get the same
name, `Tui._handle_event` treated them as the same signal and
double-counted every turn (`turn_count` came out as 2 for one real turn,
confirmed live against the real MUD before the fix). Ruby's own
`tui.rb` already avoids this by naming its equivalent signal
`turn_complete`, not `turn_end` — this port had the naming collision
available to avoid from the start and initially missed it in
translation. Renamed to `turn_complete` to match Ruby's naming and fixed
the double-count.

**Verified against the real MUD, not just a fake `Repl` double.** Headless
verification happened in two layers: first a fully mocked `Repl`/`Logger`
double driven through Textual's `run_test()` pilot (banner render,
`/help`, `Ctrl+L` clear, Esc no-op, a fake agent turn with a controllable
completion event, a synthetic `tool_call` logger event, PgUp/PgDn,
Ctrl+C quit) to confirm the widget/event wiring itself; then one real
turn ("look around") through the actual `Repl`/`Agent`/Anthropic backend
and the real `mud-manager --mcp` daemon connected to the live MUD, driven
the same way via the pilot (since the TUI takes over the whole terminal,
there's no way to smoke-test a real turn without either a real terminal
or this same headless-pilot approach). The real run correctly returned
the actual room description (Entrance Hall of the Grunting Boar Inn) and
correct token accounting after the `turn_complete` fix above.

**No committed Python test suite, consistent with every prior step's
policy** (see `python/10_standard_tool_library/README.md`'s
Considerations for the established precedent). The headless Textual
pilot script and the one live-turn script used above were exploratory,
not committed — the same scenarios they exercise (mount, slash commands,
key bindings, background-thread turn completion, live event bookkeeping)
would be straightforward to formalize into a real `pytest` suite using
`App.run_test()`, if a later step decides to start one.
