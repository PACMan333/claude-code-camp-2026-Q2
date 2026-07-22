# Python Port Plan — Step 00: Configuration

## Scope

Port `week1_baseline/ruby/00_config` to a new `week1_baseline/python/00_config`.
This is the only Ruby step that exists in the repo so far (`ruby/01_struct_skeleton`
onward haven't been built yet — see `week1_baseline/ruby/ITERATIONS.md`), so this
is the only step being planned right now. Later steps (`01_struct_skeleton`,
`02_the_registry`, ...) should each get their own plan file in this directory
(`docs/plans/python_port/01_struct_skeleton`, etc.) once their Ruby source exists.

The runner script already exists and defines the contract we must satisfy:
`week1_baseline/bin/python/00_config` does

```bash
cd week1_baseline/python/00_config
"$REPO_ROOT/.venv/bin/python" examples/example.py
```

So step 00 must be runnable as a script from a **shared repo-root `.venv`**
(not a per-step venv), with no package install step.

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `week1_baseline/ruby/00_config/Gemfile` | declares the `dotenv` gem | `week1_baseline/python/00_config/requirements.txt` (or `pyproject.toml`, see Q1) |
| `week1_baseline/ruby/00_config/lib/boukensha.rb` | top-level require, wires config + player task together | `week1_baseline/python/00_config/boukensha/__init__.py` |
| `week1_baseline/ruby/00_config/lib/boukensha/config.rb` | `Boukensha::Config` — resolves `.boukensha/` dir, loads `.env`, loads `settings.yaml`, exposes `tasks`, `mud_*`, `dig` | `week1_baseline/python/00_config/boukensha/config.py` |
| `week1_baseline/ruby/00_config/lib/boukensha/tasks/base.rb` | abstract `Tasks::Base` — classmethods for `provider`, `model`, `prompt_override?`, `prompt`/`system_prompt` resolution | `week1_baseline/python/00_config/boukensha/tasks/base.py` |
| `week1_baseline/ruby/00_config/lib/boukensha/tasks/player.rb` | concrete `Tasks::Player < Base`, `task_name = "player"` | `week1_baseline/python/00_config/boukensha/tasks/player.py` |
| `week1_baseline/ruby/00_config/prompts/system.md` | default system prompt shipped with the lib | `week1_baseline/python/00_config/prompts/system.md` (copy verbatim) |
| `week1_baseline/ruby/00_config/examples/example.rb` | runnable smoke test, prints config summary | `week1_baseline/python/00_config/examples/example.py` |
| `week1_baseline/ruby/00_config/README.md` | design notes + expected output | `week1_baseline/python/00_config/README.md` (adapted — Python API, same expected-output contract) |

Runner already in place, no change needed:
`week1_baseline/bin/python/00_config`

Shared fixture, already in place, no change needed:
`.boukensha/` at repo root (config dir picked up via `BOUKENSHA_DIR`, same as
the Ruby example does).

## Target layout

```
week1_baseline/python/00_config/
  requirements.txt            # or pyproject.toml — see Q1
  boukensha/
    __init__.py                # re-exports Config, tasks.Player
    config.py                  # Config class
    tasks/
      __init__.py
      base.py                  # Base with classmethods
      player.py                # Player(Base)
  prompts/
    system.md
  examples/
    example.py
  README.md
```

## Ruby → Python design mapping

- **`Boukensha::Config` → `boukensha.config.Config`** — same constructor-time
  resolution order: `BOUKENSHA_DIR` env var → `~/.boukensha`. Use `pathlib.Path`
  instead of `Pathname`/`File`. Use `python-dotenv`'s `load_dotenv(path)` in
  place of the `dotenv` gem. Use `yaml.safe_load` (`PyYAML`) in place of
  `YAML.safe_load` — direct equivalent.
- **Symbol/string dual keys → strings only.** Ruby's `dig`/`tasks` accept both
  `:player` and `"player"` because hashes there are keyed either way. Python
  `settings.yaml` loads as `str` keys only, so `Config.tasks(name)` and `dig(*keys)`
  take plain `str` args — no symbol equivalent needed. Simplifies the port,
  not a behavior gap.
- **`Tasks::Base` classmethods → Python `classmethod`s on a base class.**
  Ruby's "stateless class, no instances" pattern maps directly to
  `@classmethod` methods taking a `settings: dict` — no need for actual
  instances or a dataclass. `task_name` becomes an abstract classmethod
  (raise `NotImplementedError` in the base, matching Ruby).
  `.provider(settings)` / `.model(settings)` raise `ValueError` (Ruby's
  `ArgumentError` equivalent) when the key is missing.
- **`attr_reader` → Python `@property`** for `Config.dir` / `Config.settings`.
- **`to_s`/`inspect` → `__repr__`** on `Config`, same summary format
  (`<Boukensha.Config dir=... tasks=...>`).
- **`File.exist? / File.read` → `Path.exists() / Path.read_text()`**, `.strip()`
  matches Ruby's `.strip`.
- **`examples/example.rb` → `examples/example.py`** — same section-by-section
  print output so the "Run Example" contract in the README still holds
  (compare line-for-line against the Ruby expected output in
  `ruby/00_config/README.md`).

## Config directory & schema

No changes — this is shared infrastructure, already real on disk:

- Resolution order: `BOUKENSHA_DIR` env var → `~/.boukensha`.
- Directory shape: `.env`, `settings.yaml`, `prompts/<task>/system.md`.
- Schema: `tasks.<name>.{provider,model,prompt_override.system}`, `mud.{host,port,username,password}`.

The Python port must read the *same* `.boukensha/settings.yaml` and produce
equivalent output to the Ruby version, so both can point at one config dir
side by side (this matches `ITERATIONS.md`'s note: "we will have to ensure
the MudManager ruby version works with both Ruby and Python").

## Task list

1. Create `week1_baseline/python/00_config/` skeleton (dirs above).
2. Port `config.py` (dir resolution, `.env` load, `settings.yaml` load, `tasks()`, `dig()`, `mud_*`, `__repr__`).
3. Port `tasks/base.py` and `tasks/player.py`.
4. Copy `prompts/system.md` verbatim.
5. Port `examples/example.py`, matching the Ruby example's print sections and output shape.
6. Add dependency manifest (pyyaml, python-dotenv) — format per Q1.
7. Set up the shared root `.venv` referenced by `bin/python/00_config` and install deps into it — per Q2.
8. Port `README.md`, updating code samples to Python, keeping the same "Run Example" expected-output block.
9. Run `./week1_baseline/bin/python/00_config` and diff its output against `./week1_baseline/bin/ruby/00_config`'s output for the same `.boukensha/` fixture.

## Open questions

1. **Dependency manifest format** — `requirements.txt` + plain `venv`, or
   `pyproject.toml` + `uv` (matching the precedent in
   `week0_explore/circlemud-world-parser`, which uses `uv`/hatchling/Python
   3.14)? This also determines how `.venv` gets created/populated.
- use `requirements.txt` + plain `venv`
2. **Where does the shared root `.venv` get declared?** `bin/python/00_config`
   assumes one `.venv` at the repo root shared by *all* future python steps
   (00 through 12), unlike Ruby where each step folder is fully
   self-contained with its own `Gemfile`. Should dependencies for every step
   accumulate in one root-level manifest (e.g. `week1_baseline/python/requirements.txt`
   or a repo-root `pyproject.toml`), even though each step's `boukensha/` code
   is otherwise a self-contained copy like Ruby's?
- the venv should be loaded at the root of the project because we will be creating iterations in future folders and having a single python venv in a single place will make thing easier.   
3. **Python version floor** — pin to 3.14 (matching `circlemud-world-parser`)
   or something looser/older for broader compatibility?
- use something looser/older for broader compatibility
4. **Packaging** — does `examples/example.py` import via `sys.path`
   manipulation (`sys.path.insert(0, ...)` then `import boukensha`), or should
   each step folder be pip-installed editable (`pip install -e .`) into the
   shared venv? Ruby's `require_relative` has no direct equivalent; this
   choice affects eshould be pip-installed editable 
5. **Later steps carry more dependencies** (HTTP client, later an MCP client,
   TUI framework in step 11, etc.) — do we want the manifest format decided
   here in step 0 to be one we're committed to for the rest of the port, or
   is it fine to revisit per-step?
- let the manifest format be revisted per-step
