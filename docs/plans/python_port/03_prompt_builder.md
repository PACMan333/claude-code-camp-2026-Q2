# Python Port Plan — Step 03: The Prompt Builder

## Scope

Port `week1_baseline/ruby/03_prompt_builder` to a new
`week1_baseline/python/03_prompt_builder`. Same as steps 00–02, this is a
self-contained copy of the `boukensha` package at this point in its history
(mirroring Ruby's per-step-folder duplication), not a diff against
`python/02_the_registry`.

The runner already exists and defines the contract:
`week1_baseline/bin/python/03_prompt_builder` does

```bash
cd week1_baseline/python/03_prompt_builder
"$REPO_ROOT/.venv/bin/python" examples/example.py
```

— same shared repo-root `.venv` as steps 00–02 (see
`docs/plans/python_port/00_config` for the settled answers on manifest
format, venv location, Python version floor, and editable-install
packaging — reused unchanged) and same copy-forward-unchanged-files
convention settled in `docs/plans/python_port/01_struct_skeleton` (Q1: yes,
mirror Ruby's per-step duplication exactly). The target directory
currently exists but is empty — this step is a from-scratch build, not an
edit of partial scaffolding.

Ruby steps 04+ do not exist on disk yet, so this plan only covers 03.

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `Gemfile` (`dotenv` only) | unchanged | `requirements.txt` (PyYAML, python-dotenv — unchanged from step 02) |
| `lib/boukensha.rb` | top-level require list, now also wires in `prompt_builder` + all five `backends/*` | `boukensha/__init__.py` |
| `lib/boukensha/config.rb` | **changed from step 02** — re-adds the `PROMPTS_DIR` constant (present in step 00, dropped in 01/02, back here) | `boukensha/config.py` — copy forward from `python/02_the_registry`, re-add the `PROMPTS_DIR` module constant (already written once, verbatim, in `python/00_config/boukensha/config.py` — reuse that exact line) |
| `lib/boukensha/errors.rb` | **changed** — adds `UnsupportedModelError < StandardError` alongside `UnknownToolError` | `boukensha/errors.py` — add `class UnsupportedModelError(Exception): pass` |
| `lib/boukensha/registry.rb` | **changed slightly** — `.tool` now returns the created `Tool`; both `.tool` and `.dispatch` explicitly call `name.to_s` before touching `@context.tools` | `boukensha/registry.py` — `.tool()` returns the `Tool` instance; the `.to_s` calls are Ruby-only no-ops in Python (names are already `str`), so no behavior to add there beyond the return value |
| `lib/boukensha/context.rb` | cosmetic only (stray comment line removed, trailing newline added) — no functional change from step 02 | `boukensha/context.py` — copy forward unchanged |
| `lib/boukensha/tool.rb`, `lib/boukensha/message.rb` | byte-identical to step 02 | `boukensha/tool.py`, `boukensha/message.py` — copy forward unchanged |
| `lib/boukensha/tasks/base.rb`, `lib/boukensha/tasks/player.rb` | byte-identical to step 02 | `boukensha/tasks/base.py`, `boukensha/tasks/player.py` — copy forward unchanged |
| `lib/boukensha/prompt_builder.rb` | **new** — `PromptBuilder`: thin delegator (`to_messages`, `to_tools`, `to_api_payload`, `headers`, `url`) over whatever backend it's constructed with | `boukensha/prompt_builder.py` — new `PromptBuilder` class |
| `lib/boukensha/backends/base.rb` | **new** — abstract backend contract: `MODELS` table, `.models`, `.model_info(model)`, `.validate_model!(model)`, instance `context_window`, `input_token_cost_per_million`, `output_token_cost_per_million`, `usage_unit`, `usage_level`, `estimate_cost` | `boukensha/backends/base.py` — new `Base` class (see naming-collision note below) |
| `lib/boukensha/backends/anthropic.rb` | **new** — Anthropic Messages API serialization + `MODELS` table (4 models) | `boukensha/backends/anthropic.py` |
| `lib/boukensha/backends/ollama.rb` | **new** — local Ollama `/api/chat` serialization + `MODELS` table (9 models, all `$0`, `local_compute`) | `boukensha/backends/ollama.py` |
| `lib/boukensha/backends/ollama_cloud.rb` | **new** — Ollama Cloud serialization + `MODELS` table (3 models, `cost_per_million: nil`, `ollama_cloud_usage`) | `boukensha/backends/ollama_cloud.py` |
| `lib/boukensha/backends/openai.rb` | **new** — OpenAI Chat Completions serialization + `MODELS` table (3 models) | `boukensha/backends/openai.py` |
| `lib/boukensha/backends/gemini.rb` | **new** — Gemini `generateContent` serialization + `MODELS` table (5 models) | `boukensha/backends/gemini.py` |
| `prompts/system.md` | default system prompt (unused by the shipped `.boukensha/` fixture, which sets `prompt_override.system: true` and supplies its own `prompts/player/system.md`) | `prompts/system.md` — copy forward verbatim |
| `examples/example.rb` | builds `Config` → `Context` → `Registry`, registers `look`/`move`, adds 3 messages, picks a backend by `provider` from settings, builds a `PromptBuilder`, prints the full API payload as pretty JSON | `examples/example.py` |
| `README.md` | backend contract, per-API format tables (system prompt, tool results, tool defs, roles), Considerations | `README.md` (adapted) |

Runner already in place, no change needed:
`week1_baseline/bin/python/03_prompt_builder`

## Target layout

```
week1_baseline/python/03_prompt_builder/
  requirements.txt
  pyproject.toml                  # editable-install metadata, same pattern as 00-02
  prompts/
    system.md
  boukensha/
    __init__.py                    # exports Config, Player, Tool, Message, Context,
                                    # Registry, UnknownToolError, UnsupportedModelError,
                                    # PromptBuilder, and all five backend classes
    config.py                      # copied forward from 02, PROMPTS_DIR re-added
    tool.py                        # copied forward
    message.py                     # copied forward
    context.py                     # copied forward
    errors.py                      # UnknownToolError + new UnsupportedModelError
    registry.py                    # .tool() now returns the Tool
    prompt_builder.py              # new
    tasks/
      __init__.py
      base.py                      # copied forward
      player.py                    # copied forward
    backends/
      __init__.py
      base.py                      # new
      anthropic.py                 # new
      ollama.py                    # new
      ollama_cloud.py               # new
      openai.py                    # new
      gemini.py                    # new
  examples/
    example.py
  README.md
```

## Ruby → Python design mapping

- **`Config`, `Tool`, `Message`, `Context`, `Tasks::Base`, `Tasks::Player`
  → copied forward unchanged** from `python/02_the_registry`, except
  `config.py` re-gains the `PROMPTS_DIR` module constant (Ruby re-added it
  this step; it already exists verbatim in `python/00_config/boukensha/config.py`
  from before it was dropped in step 01 — reuse that line rather than
  re-deriving it).
- **`errors.py` gains `UnsupportedModelError(Exception)`** — same
  plain-marker-exception treatment as `UnknownToolError`.
- **`Registry.tool()` now returns the `Tool` it registers.** The Ruby
  `.to_s` calls on `name` in both `tool` and `dispatch` are no-ops in
  Python (names are already `str` at the call site), so the only real
  change to carry forward is the return value.
- **`PromptBuilder` is a straightforward 1:1 port** — a thin class holding
  `(context, backend)` and delegating every method to the backend, with
  `to_api_payload(max_output_tokens=1024)` as the one method that also
  passes `context` through.
- **`Backends::Base`'s class-method/instance-method name collision on
  `model_info` doesn't survive translation as-is** — Ruby's singleton-class
  method table lets `self.model_info(model)` (lookup by name) and
  `model_info` (zero-arg instance reader) coexist under one name; Python
  has one namespace per class body, so the second definition would
  silently clobber the first. **Resolved: keep `model_info` as the
  classmethod lookup** (`Base.model_info(model)` / `Anthropic.model_info("claude-haiku-4-5")`),
  matching the Ruby name most closely since it's the more "public-facing"
  form conceptually. **Rename the instance accessor to `current_model_info`**
  (a `@property` reading `self._model_info`, set once in `configure_model`).
  Downstream instance methods (`context_window`, `input_token_cost_per_million`,
  `output_token_cost_per_million`, `usage_unit`, `usage_level`) read from
  `self.current_model_info` instead of the zero-arg `model_info`. Neither
  name is referenced externally today (not in `examples/example.rb`, not in
  the README), so this rename has no visible behavior change.
- **`.validate_model!` → `.validate_model`** (classmethod, drops the bang —
  established convention already used for `prompt_override?` → `prompt_override`
  in step 01/02). Raises `UnsupportedModelError` with the same message
  shape (`"{cls} does not support model {model!r}. Supported models: ..."`).
- **`.models` classmethod → checks for a `MODELS` class attribute** rather
  than Ruby's `const_get(:MODELS)` + rescue `NameError`. Python:
  `getattr(cls, "MODELS", None)`, raise `NotImplementedError` if absent.
- **`MODELS` tables → class-level `dict` literals**, symbol keys become
  string keys (`:context_window` → `"context_window"`, etc.) per the
  symbol→string convention established since step 00. Port all five
  tables verbatim (same model names, prices, context windows, usage
  units/levels) — these are static tutorial data as of the Ruby README's
  stated date (2026-06-16) and shouldn't be "corrected" or updated as part
  of this port.
- **`estimate_cost(input_tokens:, output_tokens:)` → keyword-only Python
  method** (`def estimate_cost(self, *, input_tokens, output_tokens)`),
  returns `None` when either cost-per-million is `None` (Ollama Cloud),
  same division-by-1,000,000 formula otherwise.
- **Role dispatch (`case msg.role when :tool_result ... when :assistant ...`)
  → plain string comparison** (`if msg.role == "tool_result"`, etc.) — no
  symbols in Python, matching the convention already used for `Message.role`
  since step 01 (messages are constructed with string roles, e.g.
  `ctx.add_message("user", ...)`).
- **Per-backend `to_messages` signatures are ported exactly as Ruby has
  them, not normalized** — `anthropic.py`/`gemini.py` define
  `to_messages(self, messages)` (one arg: system is a separate top-level
  payload field for these two APIs); `ollama.py`/`ollama_cloud.py`/`openai.py`
  define `to_messages(self, system, messages)` (two args: these three APIs
  inline the system prompt as a `role: system` message). **This preserves
  a latent Ruby bug**: `PromptBuilder.to_messages()` calls
  `self._backend.to_messages(self._context.messages)` — one argument,
  unconditionally — which raises a `TypeError` for the Ollama-family
  backends if called directly (rather than via `to_api_payload`, whose
  `to_payload` on each backend calls its own `to_messages` internally with
  the correct arity and never goes through `PromptBuilder.to_messages`).
  The shipped `.boukensha/settings.yaml` fixture uses `provider: anthropic`,
  so `example.py`'s call to `builder.to_api_payload()` never exercises this
  path — the bug is real but undemonstrated by the example. Document it in
  the README's Considerations section as an inherited wrinkle, same
  treatment as the string→symbol note in step 02's README — don't silently
  fix it.
- **`JSON.pretty_generate(payload)` → `json.dumps(payload, indent=2)`.**
  Expect the same class of cosmetic diff already accepted since step 00
  (Ruby's pretty-printer formats empty arrays/objects across multiple
  lines; Python's `json.dumps` compacts them onto one line) — not a
  byte-identical match, match structure/content instead.
- **`ENV.fetch("ANTHROPIC_API_KEY")` (and the other three provider key
  vars) → `os.environ["ANTHROPIC_API_KEY"]`** — both raise on a missing
  var (`KeyError` in Python, `KeyError` in Ruby too, since `Hash#fetch`
  without a default raises), so this is a direct translation.
- **The `provider → backend class` dispatch in `example.rb`'s
  `case ... when "anthropic" ... else raise ArgumentError` → Python
  `if/elif` chain ending in `raise ValueError(...)`.** Direct translation,
  no dict-based dispatch table needed for five cases matching the Ruby
  structure.

## Config directory & schema

Unchanged from steps 00–02 — same `.boukensha/` fixture
(`tasks.player.provider: anthropic`, `tasks.player.model: claude-haiku-4-5`,
`tasks.player.prompt_override.system: true`, plus `mud.*` and a real
`prompts/player/system.md` override). This step's `example.py` reads
`config.tasks("player")`, resolves `provider`/`model` via
`Player.provider(...)`/`Player.model(...)`, and builds the system prompt via
`Player.system_prompt(settings, user_prompts_dir=..., default_prompts_dir=Config.PROMPTS_DIR)`
— note `default_prompts_dir` is passed again this step (it was omitted in
01/02 since `PROMPTS_DIR` didn't exist then).

## Task list

1. Create `week1_baseline/python/03_prompt_builder/` skeleton (dirs above).
2. Copy forward `tool.py`, `message.py`, `context.py`, `tasks/base.py`,
   `tasks/player.py` verbatim from `python/02_the_registry`.
3. Copy forward `config.py` from `python/02_the_registry`, re-adding the
   `PROMPTS_DIR` module constant (reuse the line from `python/00_config`).
4. Update `errors.py`: add `UnsupportedModelError(Exception)`.
5. Update `registry.py`: make `.tool()` return the registered `Tool`.
6. Write `boukensha/backends/base.py`: `MODELS`-presence check, `model_info`
   classmethod, `validate_model` classmethod, `current_model_info` property,
   `context_window`, `input_token_cost_per_million`,
   `output_token_cost_per_million`, `usage_unit`, `usage_level`,
   `estimate_cost`, `configure_model` helper.
7. Write the five concrete backends (`anthropic.py`, `ollama.py`,
   `ollama_cloud.py`, `openai.py`, `gemini.py`): `MODELS` table,
   `__init__`, `to_messages`, `to_tools`, `to_payload`, `headers`, `url` —
   per the signatures called out above (Anthropic/Gemini: `to_messages(messages)`;
   Ollama-family: `to_messages(system, messages)`).
8. Write `boukensha/prompt_builder.py`: `PromptBuilder` delegator class.
9. Copy forward `prompts/system.md` verbatim.
10. Wire `boukensha/__init__.py` to export `Config`, `Player`, `Tool`,
    `Message`, `Context`, `Registry`, `UnknownToolError`,
    `UnsupportedModelError`, `PromptBuilder`, and the five backend classes.
11. Port `examples/example.py`: build `Config` → system prompt → `Context`
    → `Registry`, register `look` + `move`, add the three messages (user,
    assistant, tool_result), resolve `provider`/`model`, dispatch to the
    matching backend class (raising `ValueError` on an unsupported
    provider), build a `PromptBuilder`, print config/provider/model and
    the pretty-printed `to_api_payload()`.
12. Reuse `requirements.txt` (PyYAML, python-dotenv) and `pyproject.toml`
    (editable-install metadata) from the step 02 pattern, bumping the
    `description` field to reference Step 3.
13. Install this step editable into the shared root `.venv`
    (`pip install -e week1_baseline/python/03_prompt_builder`), repointing
    from step 02.
14. Run `./week1_baseline/bin/python/03_prompt_builder` and compare against
    `./week1_baseline/bin/ruby/03_prompt_builder`'s actual output for the
    same `.boukensha/` fixture — expect the same class of cosmetic diffs
    already accepted in steps 00–02 (JSON pretty-printer whitespace,
    `#<...>`/`<...>` repr differences), nothing more. Fixture provider is
    `anthropic`, so this only exercises the Anthropic backend end-to-end;
    the other four backends are unit-testable by construction
    (`Backend(api_key=..., model=...)` + `to_payload(ctx)`) but have no
    settings-driven path through `example.py` in this step.
15. Port `README.md`: backend contract tables, the four per-API format
    comparison blocks (system prompt, tool results, tool definitions,
    message roles), and a Considerations section that (a) carries forward
    the stateless-conversation and tool-results-as-user-messages notes
    from Ruby, and (b) adds the new `to_messages` arity wrinkle described
    above as an inherited-not-fixed quirk.

## Open questions

Resolved during planning:

1. **`Backends::Base`'s `model_info` name collision** (classmethod lookup
   vs. instance reader, impossible to keep both names in Python) —
   **resolved: keep `model_info` as the classmethod, rename the instance
   reader to `current_model_info`.**
2. **The `PromptBuilder.to_messages()` / Ollama-family arity mismatch** —
   **resolved: preserve faithfully.** Port each backend's `to_messages`
   signature exactly as Ruby has it and document the resulting latent bug
   in the README's Considerations section rather than normalizing the
   signatures across backends.
