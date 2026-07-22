# 00 · Configuration (Python port)

Python port of `week1_baseline/ruby/00_config`. Same behaviour, same
`.boukensha/` config directory, same `settings.yaml` schema — see that
step's README for the full design rationale. This file only covers the
Python-specific API and setup.

## Setup

This step runs from a single **shared venv at the repo root**, since every
future python step (`01_struct_skeleton`, `02_the_registry`, ...) will reuse
it rather than each getting its own virtualenv:

```bash
# from the repo root, once:
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install -r week1_baseline/python/00_config/requirements.txt
#.venv/bin/pip install -e week1_baseline/python/00_config
```

The last line installs this step's `boukensha` package in editable mode so
`import boukensha` resolves from anywhere using `.venv`. Each step is a
self-contained copy of the `boukensha` package (mirroring the Ruby
`ruby/<step>/lib` layout) — switching which step is "active" means
re-running `pip install -e week1_baseline/python/<step>` to repoint the
editable install.

## Code Changes

| File | Purpose |
|------|---------|
| `boukensha/config.py` | `Config` class |
| `boukensha/tasks/base.py` | abstract `Base` (provider/model + prompt resolution) |
| `boukensha/tasks/player.py` | concrete `Player` (the main loop) |
| `boukensha/__init__.py` | top-level package exports |
| `prompts/system.md` | default system prompt shipped with the package |
| `examples/example.py` | runnable smoke-test |

## Config directory resolution

Same as Ruby — resolved in this order:

1. **`BOUKENSHA_DIR` env var** — set this to point at any directory you like.
2. **`~/.boukensha`** — the default location for a real install.

## Config directory structure

```
.boukensha/
  .env                 # stores credentials eg. LLMs APIs (never committed to repo)
  settings.yaml        # all non-secret settings
  prompts/
    <task>/
      system.md        # per-task override for the default system prompt (optional)
```

## Tasks

`boukensha.tasks.Base` is a stateless class — all behaviour is expressed as
`classmethod`s that accept a `settings: dict`. Concrete subclasses define
`task_name()`. For now only `Player` exists.

```python
from boukensha import Config, Player, PROMPTS_DIR

config = Config()
player_settings = config.tasks("player")

Player.provider(player_settings)
Player.system_prompt(
    player_settings,
    user_prompts_dir=config.user_prompts_dir,
    default_prompts_dir=PROMPTS_DIR,
)
```

Note: Ruby's `dig`/`tasks` accept both `:player` symbols and `"player"`
strings. Python has no symbol type, so `Config.tasks(name)` and `Config.dig(*keys)`
take plain `str` only.

## System prompt resolution

Same order as Ruby:

1. **`.boukensha/prompts/<task>/system.md`** — used when the task's
   `prompt_override.system` is `True` and the file exists.
2. **`prompts/system.md`** — the default system prompt shipped with the package.

## Configuration Schema

Unchanged from the Ruby step — see `ruby/00_config/README.md` for the full
schema description and `settings.yaml` example.

## Run Example

```bash
./week1_baseline/bin/python/00_config
```

Expected output matches the Ruby step's (same `.boukensha/` fixture, same
section-by-section print), e.g.:

```
=== Boukensha Step 0: Configuration ===

Config dir:     /home/andrew/Sites/Claude-Code-Camp/.boukensha
Tasks:          player

-- player task --
Provider:       anthropic
Model:          claude-haiku-4-5
Prompt override?True
System prompt:  You are a MUD player assistant. Use the tools available to y...

MUD host:       localhost:4000
MUD user:       dummy

API key set?    True

<Boukensha.Config dir=/home/andrew/Sites/Claude-Code-Camp/.boukensha tasks=player>
```

## Considerations

Same open considerations as the Ruby step (carried forward deliberately —
future steps address these, not this one):
- Default prompt is `prompts/system.md`, not yet scoped per task like the
  override path is.
- Settings file only accepts `.yaml`, not `.yml`.
- No graceful handling of a missing `settings.yaml` — resolving a config dir
  with no file just yields empty settings, no explicit error.
