# 08 · The REPL Loop (Python port)

Python port of `week1_baseline/ruby/08_the_repl_loop`. This step adds
`Repl`: an interactive session loop that wraps the same primitives as
`boukensha.run`, but stays alive — reading a task from stdin, running the
agent, printing the reply, and looping back — instead of running once.
`Context` is shared across every turn so conversation history accumulates
naturally.

**Like steps 04–07, this step's example makes real, billed HTTP requests
to a live LLM API**, once per turn — inherited from `Client`/`Agent`, not
new here.

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/08_the_repl_loop/requirements.txt
.venv/bin/pip install -e week1_baseline/python/08_the_repl_loop
```

This step is a self-contained copy of the `boukensha` package (mirroring
Ruby's per-step-folder duplication). `tool.py`, `message.py`, `errors.py`,
`registry.py`, `prompt_builder.py`, `logger.py`, `run_dsl.py`,
`tasks/player.py`, `tasks/base.py`, `backends/base.py`, all five backends,
and `prompts/system.md` are copied forward unchanged from
`python/07_the_run_dsl` — their Ruby sources are byte-identical at this
step too. Installing this step editable repoints `import boukensha` at
this step's copy.

## New Files

| File | Description |
|---|---|
| `boukensha/repl.py` | `Repl` — the interactive session loop, built-in commands, banner |
| `boukensha/version.py` | `VERSION = "0.8.0"` |

## Updated Files

| File | Change |
|---|---|
| `boukensha/__init__.py` | Adds `start_repl()`, the interactive entry point (see Considerations for the name) |
| `boukensha/agent.py` | All three return paths now persist the final reply into `Context` via `add_message("assistant", ...)` |
| `boukensha/client.py` | A 401 response now raises a specific "authentication failed" `ApiError` instead of a generic status message |
| `boukensha/config.py` | `_resolve_dir` gains a middle tier: a `.boukensha/` in the current working directory, checked before the `~/.boukensha` default |
| `boukensha/context.py` | Adds `clear_messages()` — wipes history, keeps tools/system prompt |

## `boukensha.start_repl`

```python
def register(dsl):
    dsl.tool(
        "read_file",
        description="Read a file from disk",
        parameters={"path": {"type": "string", "description": "File path"}},
        block=lambda *, path: open(path).read(),
    )

boukensha.start_repl(model="claude-haiku-4-5", register_tools=register)
```

Same options as `boukensha.run`, minus `task` (the user supplies tasks
interactively). Registers tools once, then loops: reads a line from
stdin, runs the agent, prints the reply, and prompts again — until `/exit`,
`/quit`, or EOF (Ctrl-D).

### Built-in commands

| Command | Effect |
|---|---|
| `/help` | Print the command list |
| `/quiet` | Suppress detailed logging (see Considerations — this doesn't actually gate anything today) |
| `/loud` | Re-enable logging (same caveat) |
| `/clear` | Wipe conversation history (tools stay registered) |
| `/exit` / `/quit` | Leave the REPL |
| Ctrl-D | EOF — leave the REPL |
| Ctrl-C | Interrupt — leave gracefully with `"Interrupted."` |

### The banner

`Repl.start()` prints a status banner showing the version, resolved
config directory (and whether it exists), the active provider/model, and
whether an API key is set — this is the real rendered output, not the
Ruby README's fabricated sample (see Considerations):

```
╔════════════════════════════════════════╗
║  BOUKENSHA MUD Assistant (v0.8.0)      ║
╚════════════════════════════════════════╝
  config:    /home/user/.boukensha
  provider:  anthropic (claude-haiku-4-5)  ✓ API key set

  /quiet or /loud   toggle logging
  /clear           reset conversation history
  /exit or /quit    leave the REPL
```

## Task Configuration

Unchanged from steps 05–07:

```yaml
tasks:
  player:
    provider: anthropic
    model: claude-haiku-4-5
    prompt_override:
      system: true
```

## Considerations

**`start_repl()`, not `repl()`.** `boukensha/repl.py` is a submodule
containing `Repl`, imported via `from .repl import Repl` — the same shape
of collision step 06 resolved for `config()`/`config.py` (the import
binds the `boukensha.repl` attribute to the submodule; a `def repl():`
in `__init__.py` would reassign/shadow it). Lower practical risk than the
`config` case, since nothing in this codebase does
`from boukensha.repl import Repl` or `boukensha.repl.Repl(...)` anywhere
— `Repl` is only ever constructed internally by the entry-point function
— but resolved the same way regardless, rather than relying on "nothing
needs the submodule attribute today" holding forever.

**`Agent` now persists its final reply into `Context` on all three exit
paths** (the normal `end_turn` return, `_wrap_up`'s successful wind-down,
and `_wrap_up`'s `except ApiError` fallback) via
`self._context.add_message("assistant", text)` immediately before
returning. This is what lets a REPL's next turn see what the agent said
last turn — a one-shot `boukensha.run`/`start_repl` caller's `Context`
was always discarded right after, so this never mattered before this
step.

**`start_repl()`'s `try` wraps the entire function body, not just the
`Repl(...).start()` call — wider than `run()`'s scope in step 07.**
Step 07's `run()` only needed a `try/finally` (no `except`), so where the
`try` started didn't matter behaviorally — `logger.close()` in `finally`
is a safe no-op if `logger` is still `None`, regardless of how early an
exception fired. This step adds a real `except KeyboardInterrupt`
alongside it, and that needs to actually catch a Ctrl-C from anywhere in
the function — including during config/context/backend construction,
before `Logger`/`Repl` even exist — to match Ruby's real whole-method
`rescue Interrupt`/`ensure` (no explicit `begin`, so it spans everything).

**`example.py` sets `BOUKENSHA_DIR` even though `example.rb` doesn't —
same root cause as step 07's off-by-one finding, different shape.**
Ruby's `example.rb` sets no `BOUKENSHA_DIR` this step; it doesn't need
to, because `week1_baseline/bin/ruby/08_the_repl_loop` (the real entry
point) exports the correct value before invoking `ruby`. The **Python
runner never has** — every prior Python `example.py` (steps 05–07) has
carried its own `os.environ.setdefault("BOUKENSHA_DIR", ...)` fallback to
compensate, and this step is no exception, using the same 5-`.parent()`
resolution.

**The Ruby README for this step is unusually unreliable, in several
independent ways — worth citing specifically.** It's titled "Step 7"
(off by one, the same mistake step 07's own README made about itself);
its "Running it" section says `cd 07_the_repl_loop` and
`ruby examples/step7.rb` — neither the directory nor the file exists
(the real ones are `08_the_repl_loop` and `examples/example.rb`); its
sample banner output (`║  BOUKENSHA REPL — MUD assistant ║`) doesn't
match what the real `banner` method renders at all — confirmed by
reading `repl.rb` directly (the real one shows a version number, config
path, and provider status). Its "Changes from step 6" section credits
`Logger#turn` to this step ("New method that prints a `╔══ turn N ══╗`
header") — but `diff` confirms `logger.rb` is byte-identical to step 07,
where `turn` was already added (documented then as forward-looking,
unused scaffolding), and `turn` has never printed anything to the
console in either step — it only writes a JSONL log line. This port
documents only what's real and source-verified.

**Two things the Ruby README's own "Technical Considerations" section
already flagged, preserved here rather than re-discovered or silently
fixed.** First: *"We need to determine [if] quiet and loud are legacy
logging or if they actually provided[d] detail[ed] logs"* — confirmed by
`grep`: `Boukensha.quiet?`/`is_quiet` is checked nowhere in
`logger.rb`/`agent.rb`; only `Boukensha.debug?` gates anything
(`Logger.raw`). `/quiet`/`/loud` are genuinely no-ops today, by the Ruby
authors' own admission — `boukensha.quiet()`/`loud()` still get called,
still do nothing observable. Second: *"It looks like [the] REPL loop we
initialize on every turn an agent... it seems like we should initialize
only once"* — confirmed: `Repl._run_turn` really does construct a fresh
`Agent(...)` every turn while reusing `context`/`registry`/`builder`/
`client`/`logger` across turns. Both are self-acknowledged, not-yet-fixed
warts in the Ruby source (same "preserve + document, don't silently fix"
policy as step 04's stateful-`Client` wrinkle) — the Python `Repl`
mirrors both exactly.

**`Repl.start`'s input loop uses `input(PROMPT)` + `except EOFError`, not
a manual print/flush/readline sequence.** Ruby's `print PROMPT; $stdout.flush; input = $stdin.gets`
is three steps because `gets` takes no prompt argument and returns `nil`
at EOF. Python's `input(PROMPT)` handles the prompt-print-and-flush in
one call and raises `EOFError` instead of returning `None`, so the loop
becomes `try: line = input(PROMPT) except EOFError: break`.

**`Repl._run_turn`'s Ruby method-level `rescue LoopError`/`rescue ApiError`
wraps the whole method, not just the `agent.run()` call** — the Python
translation wraps the entire `_run_turn` body in one `try` with two
`except` clauses, so a `LoopError`/`ApiError` raised anywhere in the turn
(constructing `Agent`, adding the user message, or running it) is caught
alike, matching Ruby's implicit per-method rescue.

## Run Example

```bash
./week1_baseline/bin/python/08_the_repl_loop
```

Starts an interactive session against the configured provider. Each line
you type becomes a turn; type `/help` for commands, `/exit` or Ctrl-D to
leave. Every phase of every turn is written to
`.boukensha/sessions/<session-id>.jsonl`.
