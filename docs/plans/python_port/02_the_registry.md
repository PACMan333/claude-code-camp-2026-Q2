# Python Port Plan — Step 02: The Tool Registry

## Scope

Port `week1_baseline/ruby/02_the_registry` to a new
`week1_baseline/python/02_the_registry`. Same as steps 00/01, this is a
self-contained copy of the `boukensha` package at this point in its history
(mirroring Ruby's per-step-folder duplication), not a diff against
`python/01_struct_skeleton`.

Note: the Ruby source in this step had several files with misplaced/wrong
content and one missing file (`message.rb`) — these were reconstructed
first (see conversation history) before this port. The reference table
below describes the *corrected* Ruby source, which is what's actually on
disk now.

The runner already exists and defines the contract:
`week1_baseline/bin/python/02_the_registry` does

```bash
cd week1_baseline/python/02_the_registry
"$REPO_ROOT/.venv/bin/python" examples/example.py
```

— same shared repo-root `.venv` as steps 00/01 (see
`docs/plans/python_port/00_config` for the settled answers on manifest
format, venv location, Python version floor, and editable-install
packaging — reused unchanged) and same copy-forward-unchanged-files
convention settled in `docs/plans/python_port/01_struct_skeleton` (Q1: yes,
mirror Ruby's per-step duplication exactly).

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `week1_baseline/ruby/02_the_registry/Gemfile` | declares the `dotenv` gem (unchanged) | `week1_baseline/python/02_the_registry/requirements.txt` |
| `week1_baseline/ruby/02_the_registry/lib/boukensha.rb` | top-level require, now also wires in `errors` + `registry` | `week1_baseline/python/02_the_registry/boukensha/__init__.py` |
| `.../lib/boukensha/config.rb` | `Boukensha::Config` — byte-identical to step 01 | `boukensha/config.py` — copy forward from `python/01_struct_skeleton` unchanged |
| `.../lib/boukensha/tasks/base.rb` | `Tasks::Base` — byte-identical to step 01 | `boukensha/tasks/base.py` — copy forward unchanged |
| `.../lib/boukensha/tasks/player.rb` | `Tasks::Player` — byte-identical to step 01 | `boukensha/tasks/player.py` — copy forward unchanged |
| `.../lib/boukensha/tool.rb` | `Tool` struct — byte-identical to step 01 | `boukensha/tool.py` — copy forward unchanged |
| `.../lib/boukensha/message.rb` | `Message` struct — byte-identical to step 01 | `boukensha/message.py` — copy forward unchanged |
| `.../lib/boukensha/context.rb` | `Context` class — byte-identical to step 01 | `boukensha/context.py` — copy forward unchanged |
| `.../lib/boukensha/errors.rb` | **new** — `Boukensha::UnknownToolError < StandardError` | `boukensha/errors.py` — new `UnknownToolError(Exception)` |
| `.../lib/boukensha/registry.rb` | **new** — `Registry`: `.tool(name, description:, parameters:, &block)` registers onto the context; `.dispatch(name, args)` looks up by name, raises `UnknownToolError` if absent, symbolizes string arg keys, calls the tool's block with those as kwargs | `boukensha/registry.py` — new `Registry` class |
| `.../examples/example.rb` | smoke test: builds `Config`/`Context`/`Registry`, registers `move` + `shout` tools, dispatches both, then dispatches an unregistered `flee` to demonstrate the error path | `examples/example.py` |
| `.../README.md` | Registry/error design notes + "Expected Output" (see caveat below) | `README.md` (adapted) |

Runner already in place, no change needed:
`week1_baseline/bin/python/02_the_registry`

**Caveat carried from the Ruby repair**: this step's README's "Expected
Output" block doesn't match the actual `Tool`/`Context` `to_s` format (it
shows quoted, untruncated descriptions and a `budget=` field that doesn't
exist in the real `Context`). The Python port should match the *real*,
working Ruby output (verified by running `./week1_baseline/bin/ruby/02_the_registry`),
not the stale README text — same approach taken for the Ruby fix.

## Target layout

```
week1_baseline/python/02_the_registry/
  requirements.txt
  pyproject.toml              # editable-install metadata, same pattern as steps 00/01
  boukensha/
    __init__.py                # exports Config, Player, Tool, Message, Context, Registry, UnknownToolError
    config.py                  # copied forward from python/01_struct_skeleton
    tool.py                    # copied forward
    message.py                 # copied forward
    context.py                 # copied forward
    errors.py                  # new — UnknownToolError
    registry.py                # new — Registry
    tasks/
      __init__.py
      base.py                  # copied forward
      player.py                # copied forward
  examples/
    example.py
  README.md
```

## Ruby → Python design mapping

- **`Config`, `Tasks::Base`, `Tasks::Player`, `Tool`, `Message`, `Context`
  → copied forward unchanged** from `python/01_struct_skeleton`, since their
  Ruby sources are byte-identical to step 01.
- **`UnknownToolError < StandardError` → `class UnknownToolError(Exception)`.**
  No behavior beyond the name — a plain marker exception, matching Ruby's
  empty subclass body.
- **`Registry#tool(name, description:, parameters:, &block)` → `Registry.tool(name, description, parameters=None, block=None)`.**
  Ruby collects the trailing `do |args| ... end` as an implicit block
  parameter; Python has no implicit block capture, so the call site passes
  the callable explicitly (e.g. `registry.tool("move", description=..., parameters={...}, block=lambda direction: ...)`
  or via a small wrapper — see Open Questions for the call-site ergonomics
  to settle before writing `examples/example.py`).
- **`Registry#dispatch` symbol-conversion → no-op in Python.** Ruby's
  `args.transform_keys(&:to_sym)` exists only because Ruby blocks are called
  with keyword args (`tool.block.call(**symbol_args)`) and JSON/Hash args
  arrive as strings. Python has no symbol/string key distinction — `dispatch`
  can call `tool.block(**args)` directly with the string-keyed dict,
  dropping the conversion step entirely. Document this as an intentional
  simplification (same category as the symbol/string simplification already
  applied to `Config` in step 00).
- **`raise UnknownToolError, "..."` unless found → `raise UnknownToolError("...")` guard clause.**
  Direct translation.
- **Registry still delegates to `Context#tools`/`#register_tool`, not its own table** —
  match this deliberately, per the Ruby README's own "Considerations" note
  that this is a known, not-yet-corrected design wrinkle (tools live on
  `Context`, `Registry` is a thin dispatcher over it). Don't "fix" this in
  the Python port; a later step corrects it in Ruby too and the Python port
  should follow suit then, not now.

## Config directory & schema

Unchanged from steps 00/01 — same `.boukensha/` fixture, same resolution
order, same schema, no `default_prompts_dir` usage (matches step 01).

## Task list

1. Create `week1_baseline/python/02_the_registry/` skeleton (dirs above).
2. Copy forward `config.py`, `tool.py`, `message.py`, `context.py`,
   `tasks/base.py`, `tasks/player.py` verbatim from `python/01_struct_skeleton`.
3. Write `errors.py` (`UnknownToolError`).
4. Write `registry.py` (`Registry.tool`, `Registry.dispatch`).
5. Wire `boukensha/__init__.py` to export `Config`, `Player`, `Tool`,
   `Message`, `Context`, `Registry`, `UnknownToolError`.
6. Port `examples/example.py`: build `Config` → `Context` → `Registry`,
   register `move` + `shout` tools, dispatch `shout` then `move`, then
   dispatch an unregistered `flee` and catch/print `UnknownToolError`.
7. Reuse `requirements.txt` (PyYAML, python-dotenv) and `pyproject.toml`
   (editable-install metadata) from the step 00/01 pattern.
8. Install this step editable into the shared root `.venv`
   (`pip install -e week1_baseline/python/02_the_registry`), repointing
   from step 01.
9. Run `./week1_baseline/bin/python/02_the_registry` and compare against
   `./week1_baseline/bin/ruby/02_the_registry`'s actual (not README-stated)
   output for the same `.boukensha/` fixture — expect the same class of
   cosmetic diffs already accepted in steps 00/01 (`#<...>` vs `<...>`,
   `[:direction]` vs `['direction']`), nothing more.
10. Port `README.md`, correcting the "Expected Output" block to match the
    real output (same caveat as the Ruby fix) rather than propagating the
    stale example forward.

## Open questions

1. **Tool registration call-site ergonomics** — Ruby's
   `registry.tool("move", description: ..., parameters: {...}) do |direction:| ... end`
   reads naturally because Ruby blocks attach to method calls. Python has no
   equivalent trailing-block syntax. Options for `examples/example.py`:
   - **(a)** pass the callable as an explicit last argument/kwarg:
     `registry.tool("move", description=..., parameters={...}, block=lambda direction: ...)`
   - **(b)** use `@registry.tool(...)` as a decorator over a `def move(direction): ...`
     function, closer to how Python frameworks (Flask, Click) register handlers
   Recommend (a) — simplest direct translation, minimal new concepts — but
   flagging since (b) is more idiomatic Python and this course seems to value
   both literal fidelity and learning idiom.
- use option (a).
2. **Keyword-only args in registered tool callables** — Ruby's blocks use
   required keyword args (`|direction:|`, `|message:|`), which is *why*
   `dispatch` needs `**symbol_args`. Should the Python `block` callables
   also require keyword args (`lambda *, direction: ...)`) to preserve that
   shape, or is a plain positional/dict-passing convention (`lambda args: ...`)
   acceptable since Python doesn't have Ruby's keyword-arg-call gotcha in the
   first place?
- yes, require keyword args.
3. **Should `registry.py`'s dropped symbol-conversion step be called out
   in the ported README's "Considerations" section**, the same way the
   Ruby README calls out the string→symbol gotcha as a deliberate teaching
   point? Since Python has no such gotcha, the port either explains why the
   lesson doesn't transfer, or silently omits that section — which do you
   prefer?
- yes, call out this change in the read.me file