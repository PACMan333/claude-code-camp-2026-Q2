# 02 · The Tool Registry (Python port)

Python port of `week1_baseline/ruby/02_the_registry`. Same behaviour, same
`.boukensha/` config directory — see that step's README for the full design
rationale. This file only covers the Python-specific API, setup, and one
behavioral simplification (see Considerations).

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/02_the_registry/requirements.txt
.venv/bin/pip install -e week1_baseline/python/02_the_registry
```

This step is a self-contained copy of the `boukensha` package (mirroring
Ruby's per-step-folder duplication). `config.py`, `tool.py`, `message.py`,
`context.py`, and `tasks/base.py`/`tasks/player.py` are copied forward
unchanged from `python/01_struct_skeleton` — their Ruby sources are
byte-identical at this step too. Installing this step editable repoints
`import boukensha` at this step's copy.

## New Files

| File | Description |
|---|---|
| `boukensha/registry.py` | The `Registry` class — registers tools and dispatches calls |
| `boukensha/errors.py` | `UnknownToolError` |

## How It Works

The agent never calls a tool directly. It emits a structured request (name
+ args) and the `Registry` looks up the tool and runs it.

## `boukensha.Registry`

| Method | Description |
|---|---|
| `tool(name, description, parameters=None, block=None)` | Registers a new tool on the context |
| `dispatch(name, args=None)` | Looks up a tool by name and calls it with the provided args |

```python
registry.tool(
    "move",
    description="Move the player in a direction (north, south, east, west, up, down)",
    parameters={"direction": {"type": "string"}},
    block=lambda *, direction: "You move {} into a torch-lit corridor.".format(direction),
)

registry.dispatch("move", {"direction": "north"})
```

## `boukensha.UnknownToolError`

Raised when `dispatch` is called with a name that has no registered tool.

```
UnknownToolError: No tool registered as 'flee'
```

## Considerations

**Ruby → Python: the string→symbol conversion doesn't carry over, and
that's intentional, not an oversight.** Ruby's `Registry#dispatch` calls
`args.transform_keys(&:to_sym)` before invoking the tool's block, because
Ruby keyword-arg calls (`tool.block.call(**symbol_args)`) require symbol
keys, while args arriving from an API/JSON payload are string-keyed — the
Ruby README calls this out as a deliberate teaching point about a real
production gotcha.

Python has no symbol/string key distinction: a dict with string keys
(`{"direction": "north"}`) unpacks directly into keyword-only parameters
(`**args` matches `def block(*, direction): ...`) with no conversion step.
So `Registry.dispatch` here just calls `tool.block(**(args or {}))` —
the Ruby lesson doesn't transfer because the gotcha it's demonstrating is
Ruby-specific, not a general API-integration concern.

**Registry still delegates to `Context.tools`/`register_tool`, not its own
table** — carried over deliberately from Ruby, which notes this as a known,
not-yet-corrected design wrinkle (tools live on `Context`; `Registry` is a
thin dispatcher over it). A later step corrects this in Ruby, and the
Python port will follow suit then.

**Call-site ergonomics**: Ruby's trailing `do |direction:| ... end` block
syntax has no Python equivalent, so tool callables are passed explicitly as
a `block=` keyword argument (a plain `lambda` or `def`), and — matching
Ruby's keyword-arg blocks — must accept **keyword-only** parameters
(`lambda *, direction: ...`, not `lambda direction: ...`).

## Run Example

```bash
./week1_baseline/bin/python/02_the_registry
```

Expected output (verified against the real, working Ruby output — the
Ruby step's own README "Expected Output" section is stale and doesn't match
its actual `Tool`/`Context` format, so don't use it as a reference):

```
=== BOUKENSHA Step 2: Tool Registry ===

Config:  <Boukensha.Config dir=/home/andrew/Sites/Claude-Code-Camp/.boukensha tasks=player>
Context: <Context task=player turns=0 tools=2>
Tools:
  <Tool name=move description=Move the player in a direction (north, so params=['direction']>
  <Tool name=shout description=Shout a message so everyone in the zone c params=['message']>

Dispatching 'shout' with message='dragon spotted'...
Result: DRAGON SPOTTED

Dispatching 'move' with direction='north'...
Result: You move north into a torch-lit corridor.

UnknownToolError caught: No tool registered as 'flee'
```
