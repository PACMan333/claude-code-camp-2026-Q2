# Python Port Plan — Step 01: The Struct Skeleton

## Scope

Port `week1_baseline/ruby/01_struct_skeleton` to a new
`week1_baseline/python/01_struct_skeleton`. Like step 00, this is a
self-contained copy of the `boukensha` package at this point in its history
(mirroring Ruby's per-step-folder duplication), not a diff against
`python/00_config`.

The runner already exists and defines the contract:
`week1_baseline/bin/python/01_struct_skeleton` does

```bash
cd week1_baseline/python/01_struct_skeleton
"$REPO_ROOT/.venv/bin/python" examples/example.py
```

— same shared repo-root `.venv` as step 00 (see
`docs/plans/python_port/00_config` for the settled answers on manifest
format, venv location, Python version floor, and editable-install packaging;
this step reuses all of those decisions unchanged).

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `week1_baseline/ruby/01_struct_skeleton/Gemfile` | declares the `dotenv` gem (unchanged from step 00) | `week1_baseline/python/01_struct_skeleton/requirements.txt` |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha.rb` | top-level require, now also wires in `Tool`, `Message`, `Context` | `week1_baseline/python/01_struct_skeleton/boukensha/__init__.py` |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/config.rb` | `Boukensha::Config` — **identical to step 00's**, except the `PROMPTS_DIR` constant was dropped (this step's `example.rb` no longer passes `default_prompts_dir`) | `week1_baseline/python/01_struct_skeleton/boukensha/config.py` |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/tasks/base.rb` | abstract `Tasks::Base` — byte-identical to step 00 | `week1_baseline/python/01_struct_skeleton/boukensha/tasks/base.py` |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/tasks/player.rb` | concrete `Tasks::Player` — byte-identical to step 00 | `week1_baseline/python/01_struct_skeleton/boukensha/tasks/player.py` |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/tool.rb` | **new** — `Tool` struct: `name`, `description`, `parameters`, `block`; custom `to_s` | `week1_baseline/python/01_struct_skeleton/boukensha/tool.py` |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/message.rb` | **new** — `Message` struct: `role`, `content`, `tool_use_id`; custom `to_s` | `week1_baseline/python/01_struct_skeleton/boukensha/message.py` |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/context.rb` | **new** — `Context` class: holds `task`, `system`, `messages`, `tools`; `register_tool`, `add_message`, `tool_count`, `turn_count`, custom `to_s` | `week1_baseline/python/01_struct_skeleton/boukensha/context.py` |
| `week1_baseline/ruby/01_struct_skeleton/examples/example.rb` | smoke test: builds a `Context`, registers a `move` tool, adds two messages, prints all three struct types | `week1_baseline/python/01_struct_skeleton/examples/example.py` |
| `week1_baseline/ruby/01_struct_skeleton/README.md` | struct field tables + example `to_s` output | `week1_baseline/python/01_struct_skeleton/README.md` (adapted) |

Note: **no `prompts/` directory exists in this Ruby step** (it shipped one in
step 00, then dropped it here) — don't carry `prompts/system.md` forward.

Runner already in place, no change needed:
`week1_baseline/bin/python/01_struct_skeleton`

## Target layout

```
week1_baseline/python/01_struct_skeleton/
  requirements.txt
  pyproject.toml              # editable-install metadata, same as step 00
  boukensha/
    __init__.py                # exports Config, Player, Tool, Message, Context
    config.py                  # Config class (no PROMPTS_DIR this step)
    tool.py                    # Tool
    message.py                 # Message
    context.py                 # Context
    tasks/
      __init__.py
      base.py
      player.py
  examples/
    example.py
  README.md
```

## Ruby → Python design mapping

- **`Config`, `Tasks::Base`, `Tasks::Player` → copy forward from step 00's
  port**, dropping `PROMPTS_DIR` from `config.py` to match this step's
  `config.rb` (which no longer defines it). Everything else in these three
  files is unchanged from `python/00_config`.
- **`Struct.new(...) do ... end` → `@dataclass`.** Both `Tool` and `Message`
  are plain Ruby `Struct`s with one overridden method (`to_s`). A Python
  `@dataclass` gives the same "lightweight positional/keyword data
  container" feel; override `__str__` to match Ruby's custom `to_s` (dataclass's
  auto-generated `__repr__` can stay default — Ruby never overrides `inspect`
  either, only `to_s`).
- **`Context` stays a plain class**, not a dataclass — matches Ruby, which
  defines it with `class` (not `Struct.new`) because it owns mutable state
  (`@messages`, `@tools`) and behavior (`register_tool`, `add_message`).
  `attr_reader :task, :system, :messages, :tools` → Python `@property`s (or
  plain public attributes — Ruby only exposes readers, no writers, so
  `@property`-only, no setter, is the closer match).
- **String slicing in `to_s`** — Ruby's `description.to_s[0..40]` is an
  *inclusive* range (41 chars); `content.to_s[0..60]` is 61 chars. Python
  slicing is exclusive at the end, so these become `description[:41]` and
  `content[:61]` respectively — same substring length, different syntax.
- **Symbol keys in `parameters` / roles → plain strings.** Ruby's example
  builds `parameters` as `{ direction: {...} }` (symbol key) and calls
  `ctx.add_message(:user, ...)` (symbol role). Python has no symbol type, so
  these become string keys/roles (`{"direction": {...}}`, `"user"`). This is
  cosmetic and already the norm established in step 00's port.
- **Printed key format is an accepted cosmetic diff.** Ruby's
  `Tool#to_s` prints `params=#{parameters.keys}` → `params=[:direction]`
  (symbol array repr). Python's `list(parameters.keys())` prints
  `['direction']`. Same information, different literal repr — same class of
  difference already noted for step 00 (`true`/`True`,
  `#<Boukensha::Config...>`/`<Boukensha.Config...>`); don't try to force
  byte-identical output here, match structure/content instead.
- **`block` field is a `Callable`.** Ruby's `->(direction) { ... }` lambda
  becomes a Python `lambda direction: ...` assigned to `Tool.block`.
- **`Context#task` holds the class itself, not an instance** — Ruby passes
  `Boukensha::Tasks::Player` (the class) as `task:`, and `to_s` calls
  `task&.task_name` (safe-navigation, since Ruby classmethod). Python:
  `Context.task` holds the `Player` class object; `__str__` calls
  `self.task.task_name() if self.task else None`.

## Config directory & schema

Unchanged from step 00 — same `.boukensha/` fixture, same resolution order,
same schema. This step's `example.py` only reads `tasks.player` and calls
`system_prompt(..., user_prompts_dir=...)` with **no** `default_prompts_dir`
(matching the Ruby example, which dropped that argument along with
`PROMPTS_DIR`).

## Task list

1. Create `week1_baseline/python/01_struct_skeleton/` skeleton (dirs above).
2. Copy forward `config.py`, `tasks/base.py`, `tasks/player.py` from
   `python/00_config`, removing `PROMPTS_DIR` from `config.py`.
3. Write `tool.py` (`Tool` dataclass + `__str__`).
4. Write `message.py` (`Message` dataclass + `__str__`).
5. Write `context.py` (`Context` class: `register_tool`, `add_message`,
   `tool_count`, `turn_count`, `__str__`).
6. Wire `boukensha/__init__.py` to export `Config`, `Player`, `Tool`,
   `Message`, `Context`.
7. Port `examples/example.py`, matching the Ruby example's construction
   order and print sections.
8. Reuse `requirements.txt` (PyYAML, python-dotenv — unchanged) and
   `pyproject.toml` (editable-install metadata) from step 00's pattern.
9. Install this step editable into the shared root `.venv`
   (`pip install -e week1_baseline/python/01_struct_skeleton`), repointing
   from whichever step was previously installed.
10. Run `./week1_baseline/bin/python/01_struct_skeleton` and compare against
    `./week1_baseline/bin/ruby/01_struct_skeleton`'s output for the same
    `.boukensha/` fixture — expect the cosmetic diffs called out above, not
    a byte-identical match.
11. Port `README.md`, adapting the struct field tables and `to_s` example
    blocks to their Python equivalents (dataclass `__str__` output).

## Open questions

1. **Copy-forward vs. shared module for `Config`/`Tasks::Base`/`Tasks::Player`** —
   Ruby duplicates these files verbatim into every step folder (by design,
   per `ITERATIONS.md`). Do you want the Python port to do the same
   (duplicate `config.py`/`tasks/*.py` into every `python/<step>/boukensha/`),
   or would you rather the Python port factor shared, unchanged code into one
   place and only duplicate what actually changes per step? Mirroring Ruby
   exactly is simpler to reason about 1:1 but means hand-syncing any future
   bugfix across every step's copy.
- yes, mirror ruby code exactly
2. **`Tool`/`Message` as `@dataclass` vs. plain `Struct`-like `NamedTuple`** —
   dataclasses are mutable (matches Ruby `Struct`'s mutable fields) and
   support a custom `__str__` cleanly; `NamedTuple` would be immutable and
   slightly more restrictive. Confirm `@dataclass` is the right call, or if
   immutability is actually preferred here (Ruby's `Struct` instances *are*
   mutable, so `@dataclass` is the closer match, but flagging in case you
   want the port to be more idiomatic-Python than literal).
- `@dataclass` is the right call.
3. **Are steps 02+ Ruby sources already written**, or should this plan file
   be the last one until more Ruby steps land? (Same caveat as step 00's
   plan — only plan what has real Ruby source to port against.)
- wait until the next ruby step is asked to be ported.
