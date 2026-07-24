# Python Port Plan — Step 10: A Standard Tool Library

## Scope

Port `week1_baseline/ruby/10_standard_tool_library` to a new
`week1_baseline/python/10_standard_tool_library`. Same as steps 00–08,
this is a self-contained copy of the `boukensha` package at this point in
its history, not a diff against `python/08_the_repl_loop`.

**Ruby step 09 (`global_executable`) was never ported to Python.** Per
the user's explicit direction, this plan diffs step 10 directly against
`python/08_the_repl_loop` (the last real Python port) rather than against
Ruby step 09. Step 10's Ruby source is cumulative — it already contains
everything step 09 introduced (`boukensha_loader.rb`, `bin/boukensha`,
`boukensha.gemspec`) baked in alongside step 10's own new content — so
this single plan necessarily covers both: the "global executable, pick
any step at runtime" concept (step 09's contribution) and "boukensha
ships no tools of its own, everything comes from MCP servers declared in
`settings.yaml`" (step 10's own contribution). Both land in one Python
step folder, matching how they already coexist in one Ruby step folder.

**This step removes every built-in tool boukensha ever had.** The agent
becomes a pure MCP *host*: it spawns whatever's listed in `settings.yaml`'s
`mcp_servers:` block as subprocesses, speaks MCP-over-stdio to each, and
registers their advertised tools. Since MCP is a language-agnostic
wire protocol, **the Python port needs no MUD-specific code of its own at
all** — the exact same `mud-manager --mcp` Ruby daemon this session
already built and verified against the real MUD (see
`week0_explore/mud_manager/bin/mud-manager`) can be spawned by a Python
MCP client exactly as it's spawned by the Ruby one. Porting `Boukensha::Mcp::Client`
and `Boukensha::Tools::Mcp` to Python is the real work here; there is
nothing MUD-related to reimplement.

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `Gemfile` | **changed** — adds `gemspec` (pulls in `boukensha.gemspec`'s own metadata) | `requirements.txt` (unchanged) + `pyproject.toml` gains packaging/entry-point metadata (see design mapping) |
| `boukensha.gemspec` | **new** (absorbed from step 09) — gem metadata, declares the `boukensha` executable | `pyproject.toml` — adds a `[project.scripts]` entry point |
| `bin/boukensha` | **new** (absorbed from step 09) — shebang script, delegates to the loader | `bin/boukensha` — new, delegates to `boukensha_loader.main()` |
| `lib/boukensha_loader.rb` | **new** (absorbed from step 09; cosmetic-only changes between the step-09 and step-10 copies) — resolves which step's implementation and which config dir to use, then boots the REPL | `boukensha_loader.py` — new top-level module (sibling to the `boukensha` package, not inside it) |
| `lib/boukensha.rb` | **changed** — `run`/`repl` gain `working_dir:` (defaults to `Dir.pwd`, passed to `Context`, registers nothing); both call a new private `register_mcp_servers`; `repl` passes a `servers:` summary to `Repl`; requires `boukensha/tools/mcp` | `boukensha/__init__.py` — `run()`/`start_repl()` gain `working_dir=None` defaulting to `os.getcwd()`, call a new `_register_mcp_servers` helper, `start_repl` passes `servers=` through to `Repl` |
| `lib/boukensha/config.rb` | **changed** — `mud_host`/`mud_port`/`mud_username`/`mud_password` removed again (this time for good — replaced by the general `mcp_servers` mechanism, not dead-code churn); adds `mcp_servers`; `resolve_dir` reverts to the 2-tier form (see design mapping — resolved without re-asking, matching current Ruby) | `boukensha/config.py` — same: drop the four `mud_*` methods, add `mcp_servers()`, `_resolve_dir` reverts to 2-tier |
| `lib/boukensha/client.rb` | **changed** — the 401-specific `ApiError` message is gone (see design mapping — resolved without re-asking, matching current Ruby) | `boukensha/client.py` — drop the 401 special case |
| `lib/boukensha/context.rb` | **changed** — adds `working_dir` (expanded path or `nil`), attr-exposed | `boukensha/context.py` — adds `working_dir` param + property |
| `lib/boukensha/registry.rb` | **changed** — adds `tool_names` (returns registered names; used by the collision check in `Tools::Mcp`) | `boukensha/registry.py` — adds `tool_names()` |
| `lib/boukensha/run_dsl.rb` | **changed** — adds `tool_names`, delegating to the registry | `boukensha/run_dsl.py` — adds `tool_names()` |
| `lib/boukensha/repl.rb` | **changed** — accepts `servers:`; banner gains a `servers:` line summarizing what's connected (`"name (count)"` per server, or a "no tools" message) | `boukensha/repl.py` — same |
| `lib/boukensha/version.rb` | **changed** — `"0.9.0"` → `"0.10.0"` | `boukensha/version.py` — `VERSION = "0.10.0"` |
| `lib/boukensha/mcp/client.rb` | **new** — minimal MCP-over-stdio client: spawn, handshake, `tools/list`, `tools/call` | `boukensha/mcp/client.py` — new `Client` class over `subprocess.Popen` |
| `lib/boukensha/tools/mcp.rb` | **new** — registers a spawned server's tools into a `Registry`, with prefixing and collision detection | `boukensha/tools/mcp.py` — new `register`/`register_client` functions |
| `lib/boukensha/tool.rb`, `message.rb`, `prompt_builder.rb`, `logger.rb`, `errors.rb`, `agent.rb`, `backends/*.rb` (all 5 + `base.rb`), `tasks/base.rb`, `tasks/player.rb` | byte-identical to `python/08_the_repl_loop`'s Ruby source (`diff` confirmed) | copy forward unchanged from `python/08_the_repl_loop` |
| `prompts/system.md` | **changed** — adds a paragraph explaining the MUD session connects lazily on the first gameplay action, so the agent shouldn't report itself as unable to connect | `prompts/system.md` — copy new text verbatim |
| `examples/example.rb` | **rewritten** — no tool registration at all; prints `cfg.mcp_servers.keys`; calls `Boukensha.run` with no `register_tools`/block, since everything comes from config | `examples/example.py` — same shape |
| `examples/mcp_mud_demo.rb` | **new** — a `--dry` self-contained smoke test (spawns the daemon against `MudManager::FakeMud`, no LLM, no live MUD) plus a full-agent-run mode identical to `example.rb` | `examples/mcp_mud_demo.py` — new, same two modes, still shelling out to the *Ruby* daemon (see scope note above — no Python MUD code needed) |
| `test/*.rb` (`helper.rb`, `test_mcp_client.rb`, `test_tools_mcp.rb`, `test_mcp_servers_config.rb`, `test_boukensha_loader.rb`) | **new** — Minitest suite covering the MCP client/host contract and the loader | Not mechanically ported (this port has never carried Ruby's `test/` trees forward — see design mapping); the same contract is instead verified during execute via the established mock/manual-check pattern, reusing the real daemon this session already built |
| `README.md` | Overview, `Mcp::Client`/`Tools::Mcp` docs, `mcp_servers:` schema, what went away, Technical Considerations | `README.md` — adapted; carries forward this step's own honestly-scoped caveats plus the discovered regressions (see design mapping) |

Runner already in place, no change needed: `week1_baseline/bin/python/10_standard_tool_library`
(verify it's executable; `chmod +x` if not).

## Target layout

```
week1_baseline/python/10_standard_tool_library/
  requirements.txt
  pyproject.toml                  # adds [project.scripts] boukensha = "boukensha_loader:main"
  boukensha_loader.py              # new — sibling to the boukensha/ package, not inside it
  bin/
    boukensha                      # new — shebang script, mirrors Ruby's bin/boukensha
  prompts/
    system.md                      # updated: lazy MUD-connect note
  boukensha/
    __init__.py                    # working_dir=, _register_mcp_servers, servers= passthrough
    version.py                     # VERSION = "0.10.0"
    config.py                      # drops mud_*, adds mcp_servers(), 2-tier _resolve_dir
    tool.py                        # copied forward unchanged
    message.py                     # copied forward unchanged
    context.py                     # adds working_dir
    errors.py                      # copied forward unchanged
    registry.py                    # adds tool_names()
    prompt_builder.py               # copied forward unchanged
    client.py                      # drops the 401 special case
    logger.py                      # copied forward unchanged
    agent.py                       # copied forward unchanged
    run_dsl.py                     # adds tool_names()
    repl.py                        # adds servers=, banner line
    mcp/
      __init__.py
      client.py                    # new — Mcp::Client
    tools/
      __init__.py
      mcp.py                       # new — Tools::Mcp
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
    mcp_mud_demo.py                 # new
  README.md
```

## Ruby → Python design mapping

- **No MUD-specific code is needed in the Python port at all.** Step 10's
  entire point is that boukensha ships zero tools of its own — every
  capability comes from an external MCP server subprocess, spawned by
  `command`/`args`/`env` from `settings.yaml`. That subprocess can be
  written in any language; this session already built and verified a real
  one (`week0_explore/mud_manager/bin/mud-manager`, a Ruby script). The
  Python port's `mcp_servers: mud:` entry can point at that *exact same*
  daemon (`command: ruby`, same args/env as the Ruby config already uses)
  — nothing about the daemon cares which language is hosting it. This is
  worth demonstrating explicitly in the ported README as the clearest
  possible proof that MCP hosting is language-agnostic.

- **`Boukensha::Mcp::Client` → `boukensha/mcp/client.py`, `Open3.popen3` →
  `subprocess.Popen`.** Ruby's three-pipe-plus-wait-thread return from
  `Open3.popen3` maps directly to `subprocess.Popen(cmd, env=merged_env, stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True)`:
  - `initialize`/handshake: send a `jsonrpc: "2.0"` `initialize` request,
    read until the matching `id` comes back, capture `result.serverInfo`,
    then send the `notifications/initialized` notification (no response
    expected — Ruby's `notify` has no counterpart read).
  - `fetch_tools`: one `tools/list` request, `result.tools`.
  - `call_tool(name, arguments)`: one `tools/call` request; unpack
    `result.content` (a list of `{"type": "text", "text": ...}` blocks —
    join every block's `"text"` with `"\n"`, matching Ruby's
    `Array(result["content"]).map { |c| c["text"] }.compact.join("\n")`)
    and `result.get("isError", False)`.
  - `close`: close stdin, `process.wait()`, close stdout/stderr — direct
    equivalent of Ruby's `@stdin.close; @wait&.value; @stdout.close; @stderr.close`.
  - `write`/`read_until`: `json.dumps(...)` + `\n` write to stdin, flush;
    read lines from stdout via `process.stdout.readline()`, `json.loads`,
    loop until the response's `"id"` matches (ignoring notifications/
    mismatched ids, same as Ruby).
  - Spawning a nonexistent command: Ruby's `Open3.popen3` raises
    `Errno::ENOENT` immediately; Python's `subprocess.Popen` does too
    (`FileNotFoundError`, which **is** `OSError`/`Errno.ENOENT` under the
    hood in Python 3 — `FileNotFoundError` is a subclass of `OSError`
    matching `errno.ENOENT`). Let it propagate uncaught, same as Ruby.

- **`Boukensha::Tools::Mcp` → `boukensha/tools/mcp.py`, module-level
  functions (not a class) matching Ruby's module-function style already
  used for `MudManager::Primitives`-adjacent code elsewhere in this
  project**:
  - `register(registry, *, command, args=None, env=None, prefix=None)`:
    spawns a `Client`, registers an `atexit.register(lambda: client.close())`
    (Ruby's `at_exit { client.close rescue nil }` — Python's `atexit`
    callback should also swallow exceptions, matching the `rescue nil`),
    calls `register_client`, returns the client.
  - `register_client(registry, client, *, prefix=None)`: mirrors Ruby's
    collision-checking loop exactly — `taken = registry.tool_names() if hasattr(registry, "tool_names") else []`;
    for each discovered tool, compute the (possibly prefixed) local name,
    raise `CollisionError` (a `ValueError` subclass, matching Ruby's
    `CollisionError < ArgumentError`) if already taken, else register a
    tool whose `block` calls `client.call_tool(remote_name, kwargs)` and
    returns `"error: {text}"` on `result["error"]` else `result["text"]`.
  - `prefixed(name, prefix)`: `f"{prefix}__{name}"` if prefix else `name`
    (`SEPARATOR = "__"`, matching Ruby's constant).
  - `to_boukensha_params(input_schema)`: walks `inputSchema["properties"]`,
    appends `" (one of: ...)"` to the description when `"enum"` is
    present — same as the existing `_provider_name`-adjacent enum-surfacing
    logic already established for the `move` tool in step 07's design
    (`Tools::Mcp` and this port's own `Logger` independently arrived at
    the same "surface the enum in the description" idea).
  - **Boukensha's own tool-registration kwargs vs. MCP arguments is a
    string-keyed dict on both sides in Python — no symbol/string dual-key
    concern at all.** Ruby's `registry.tool(local, ...) { |**kwargs| ... client.call_tool(remote, kwargs.transform_keys(&:to_s)) }`
    needs `transform_keys(&:to_s)` because Ruby's `**kwargs` splat produces
    *symbol*-keyed hashes that the wire protocol needs as strings; Python's
    `Registry.dispatch` already calls tool blocks with `**(args or {})`
    where `args` is already string-keyed (from JSON), so a Python tool
    block declared as `def block(**kwargs): ...` receives string keys
    natively — no transform step needed, a direct simplification (not a
    behavior gap) of the same kind already catalogued in
    `references/conventions.md` for other symbol/string situations.

- **`boukensha_loader.rb` → `boukensha_loader.py`, using `sys.path` +
  `sys.modules` cache-busting to select which step's package backs
  `import boukensha` at runtime.** This is the first time this port has
  needed a *dynamic* "which package is this name" mechanism — every prior
  step assumed whatever's currently `pip install -e`'d is `boukensha`.
  Ruby's own mechanism is itself path-based (`$LOAD_PATH.unshift` +
  `require`), so the direct translation prepends the resolved step's
  directory to `sys.path`, discards any stale `sys.modules["boukensha"]`
  entry, then does a fresh `import boukensha`:
  ```python
  def load_and_start_repl():
      main_dir = resolve()  # the step folder containing a boukensha/ package
      sys.path.insert(0, str(main_dir))
      sys.modules.pop("boukensha", None)
      import boukensha
      if not hasattr(boukensha, "start_repl"):
          sys.exit(
              "boukensha: the step at {} does not support the interactive REPL "
              "(added in step 7/8). Run its examples directly, e.g.:\n"
              "  python {}/examples/example.py\n"
              "Or point BOUKENSHA_PATH at step 7 or later.".format(main_dir, main_dir)
          )
      boukensha.start_repl()
  ```
  This is adequate because `bin/boukensha` is a one-shot CLI invocation
  that runs once and exits — there's no risk of `boukensha` already being
  cached in `sys.modules` from an earlier import in the same process, the
  scenario that would make the heavier `importlib.util.spec_from_file_location`
  approach (manually building a module spec from an explicit file path,
  bypassing `sys.path` entirely) worth its extra complexity.
  `resolve()`/`load_rc()`/`expand_rc_path()` are direct translations of
  their Ruby counterparts:
  - `rc_file()`: `str(Path("~/.boukensharc").expanduser())`.
  - `load_rc()`: `yaml.safe_load` (already a dependency); a parsed
    string → `{"boukensha_path": parsed}` (backward-compat, matching
    Ruby); `None`/empty file → `{}`; anything else → exit with an error
    message naming the rc file (matching Ruby's `abort`, Python's
    `sys.exit(...)`); a `yaml.YAMLError` → the same "invalid YAML in
    {file}" exit message (Ruby's `rescue Psych::SyntaxError`).
  - `resolve()`: `BOUKENSHA_DIR` env wins over `boukensha_dir` in the rc
    file, applied via `os.environ.setdefault` semantics (only set it if
    not already set, matching Ruby's `ENV["BOUKENSHA_DIR"] = ... if !ENV["BOUKENSHA_DIR"] && rc_config_dir`);
    `BOUKENSHA_PATH` env wins over `boukensha_path` in the rc file; no
    source at all → the bundled step's own directory; a source that
    doesn't contain a `boukensha` package → exit with an error naming
    `BOUKENSHA_PATH`/the rc file.
  - `BUNDLED_LIB`/bundled default: the directory containing
    `boukensha_loader.py` itself (`Path(__file__).resolve().parent`) —
    this step's own `python/10_standard_tool_library/` folder.

- **Packaging: `pyproject.toml` gains a `[project.scripts]` entry point,
  the Python equivalent of the gemspec's `spec.executables = ["boukensha"]`.**
  `boukensha_loader.py` needs a `main()` function for the entry point to
  target (`boukensha = "boukensha_loader:main"`); `main()` is a thin
  wrapper calling `load_and_start_repl()`. `boukensha_loader.py` also
  needs to be picked up as a top-level module by the build backend — add
  `py-modules = ["boukensha_loader"]` alongside the existing
  `[tool.setuptools.packages.find]` entry (which only covers the
  `boukensha` package, not this sibling module). `bin/boukensha` (the
  plain shebang script, usable without a real `pip install`, mirroring
  how the Ruby lesson lets you run `./bin/boukensha` directly) does
  `#!/usr/bin/env python3` + `import boukensha_loader; boukensha_loader.main()`,
  with the same `sys.path` bootstrapping every other step's `examples/*.py`
  already needs to find the local package before it's installed.

- **Two discovered Ruby regressions relative to `python/08_the_repl_loop`,
  resolved by matching Ruby's current state rather than re-asking** (the
  user declined a fresh round of questions on these and asked to proceed
  directly; the reasoning is recorded here for visibility, per the
  existing discovered-inconsistency policy in `references/conventions.md`):
  - **`Client`'s 401-specific `ApiError` message is gone in step 10's
    `client.rb`.** It was added in step 08 (ported and tested then), and
    step 10's `client.rb` no longer has it, with nothing in the
    README/tests/comments explaining the removal as deliberate — it reads
    as unnoticed churn, the same shape as the `mud_host`/`LoopError`
    deletions-and-re-additions seen in earlier steps. Resolved in favor of
    **matching Ruby's current state** (drop the special case in
    `client.py` too): this port's stated job is fidelity to what the
    *current* step teaches, not preservation of a prior Python step's
    improvement the current Ruby source no longer has.
  - **`Config#resolve_dir` reverted from step 08's 3-tier form (env → cwd
    `.boukensha/` → home default) back to a 2-tier form (env → home
    default only), with no explanation.** Same reasoning, same
    resolution: match Ruby's current 2-tier `_resolve_dir` in
    `config.py`, not the tested 3-tier version from step 08.

- **`Context#working_dir` is metadata only — it registers nothing.**
  Direct translation: `Context.__init__(self, task=None, system=None, working_dir=None)`,
  storing `str(Path(working_dir).resolve()) if working_dir is not None else None`.
  `run()`/`start_repl()` default it to `os.getcwd()` (matching Ruby's
  `working_dir: Dir.pwd` default), pass it straight through to `Context(...)`,
  and nothing else reads it — same as Ruby, where the README is explicit
  that this survived from the old `Tools::FileSystem` days as pure
  bookkeeping, not a real capability.

- **`Registry#tool_names`/`RunDSL#tool_names` → plain `list`-returning
  methods**, direct translations (`list(self._context.tools.keys())` /
  delegate to the registry) — this is exactly what
  `Tools::Mcp.register_client`'s collision check needs
  (`registry.respond_to?(:tool_names) ? ... : []` → Python
  `getattr(registry, "tool_names", None)` pattern, or simpler: since
  every `Registry` this port ever constructs now has `tool_names()`,
  just call it directly rather than porting Ruby's defensive
  `respond_to?` duck-typing check literally).

- **`Repl`'s new `servers:` banner line is a direct translation** of
  Ruby's `servers_status_string`: `"(none configured — the agent has no
  tools)"` if the summary dict is empty/`None`, else
  `"  ".join("{} ({})".format(name, count) for name, count in servers.items())`.

- **This port still doesn't mechanically translate Ruby's `test/`
  directory, consistent with every prior step.** Steps 00–08 never
  carried Minitest suites forward into a Python `pytest`/`unittest` tree;
  verification has always happened during the execute phase via mock
  servers and direct `.venv/bin/python -c "..."` checks. Step 10's
  Minitest suite is unusually valuable as a *reference* though — it's
  what pinned down the exact MCP wire contract (tool result shape,
  collision error wording, prefix behavior) during this session's
  earlier work fixing the Ruby `mud-manager` daemon — so the execute
  phase should exercise the *same* scenarios those tests cover (handshake,
  tool discovery, dispatch, prefixing, collision detection, a
  nonexistent-command spawn failure) directly against the real
  `mud-manager`/`FakeMud` daemon pair, without necessarily writing them
  as a formal, committed pytest suite (open question below).

## Config directory & schema

**Changed this step**: `Config#mcp_servers` is new (parses
`settings.yaml`'s `mcp_servers:` block into
`{name: {command, args, env, prefix, required}}` with defaults applied);
`mud_host`/`mud_port`/`mud_username`/`mud_password` are gone for good this
time (superseded by the general mechanism, not oscillating dead code);
`_resolve_dir` reverts to 2-tier (see design mapping). The real
`.boukensha/settings.yaml` already has a working `mcp_servers: mud:` entry
from this session's live debugging work — the Python port can point at
that exact same entry (same daemon, same real MUD on port 4000) to prove
the port end-to-end.

## Task list

1. Create `week1_baseline/python/10_standard_tool_library/` skeleton
   (dirs above).
2. Copy forward unchanged from `python/08_the_repl_loop`: `tool.py`,
   `message.py`, `errors.py`, `prompt_builder.py`, `logger.py`,
   `agent.py`, `tasks/player.py`, `tasks/base.py`, `backends/base.py`,
   all 5 `backends/*.py`.
3. Update `version.py`: `VERSION = "0.10.0"`.
4. Update `config.py`: drop the four `mud_*` methods; add `mcp_servers()`
   per the design mapping; revert `_resolve_dir` to 2-tier.
5. Update `client.py`: drop the 401 special case (back to the plain
   generic `ApiError` message for any non-2xx, non-retryable status).
6. Update `context.py`: add `working_dir` param + property.
7. Update `registry.py`: add `tool_names()`.
8. Update `run_dsl.py`: add `tool_names()` delegating to the registry.
9. Write `boukensha/mcp/client.py`: `Client` class per the design mapping
   (spawn via `subprocess.Popen`, JSON-RPC handshake, `tools/list`,
   `tools/call`, `close`).
10. Write `boukensha/tools/mcp.py`: `register`/`register_client`/
    `CollisionError`/`prefixed`/`to_boukensha_params` per the design
    mapping.
11. Update `repl.py`: accept `servers=None`, add the banner's `servers:`
    line.
12. Update `__init__.py`: `run()`/`start_repl()` gain `working_dir=None`
    (default `os.getcwd()`), call a new `_register_mcp_servers(registry, cfg)`
    helper (mirroring Ruby's `register_mcp_servers`: iterate
    `cfg.mcp_servers()`, call `tools.mcp.register(...)`, catch
    `CollisionError` and re-raise, catch any other exception and raise a
    plain `RuntimeError` if `required` else print a warning and continue;
    return the `{name: tool_count}` summary); `start_repl` passes
    `servers=` through to `Repl`.
13. Write `boukensha_loader.py` (top-level, sibling to the `boukensha/`
    package) per the design mapping: `rc_file()`, `load_rc()`,
    `expand_rc_path()`, `resolve()`, `load_and_start_repl()`, `main()`.
14. Write `bin/boukensha`: shebang script bootstrapping `sys.path` to
    find `boukensha_loader` locally, then calling `main()`.
15. Update `pyproject.toml`: bump `description` to reference Step 10; add
    `py-modules = ["boukensha_loader"]`; add
    `[project.scripts]\nboukensha = "boukensha_loader:main"`.
16. Port `prompts/system.md`: copy the new lazy-MUD-connect paragraph
    verbatim.
17. Port `examples/example.py`: no tool registration; print
    `cfg.mcp_servers().keys()`; call `boukensha.run(...)` (or
    `start_repl`, matching whichever `example.rb` actually calls — confirm
    against the real source when writing this) with no `register_tools`.
18. Port `examples/mcp_mud_demo.py`: `--dry` mode spawning the Ruby
    `mud-manager` daemon against `MudManager::FakeMud` (both invoked via
    `subprocess`/`ruby`, no Python reimplementation) for a self-contained,
    no-API-key, no-live-MUD smoke test; full-agent mode identical to
    `example.py`.
19. Reuse `requirements.txt` (unchanged — the MCP client is stdlib-only:
    `subprocess`, `json`; no new dependency) from the step 08 pattern.
20. Install this step editable into the shared root `.venv`
    (`pip install -e week1_baseline/python/10_standard_tool_library`),
    repointing from step 08.
21. Verify the runner (`week1_baseline/bin/python/10_standard_tool_library`)
    is executable; `chmod +x` if not. Also `chmod +x bin/boukensha`.
22. **Verification, reusing the real daemon this session already built
    and validated (no live-cost concern — this is all local subprocess
    spawning, not a paid API call until the agent itself runs):**
    exercise the same scenarios the Ruby Minitest suite covers, directly
    against `week0_explore/mud_manager/bin/mud-manager` +
    `MudManager::FakeMud`: (a) handshake reports `serverInfo`; (b)
    `tools/list` discovers `look`/`attack`/etc. with `inputSchema`
    present; (c) `tools/call` dispatches and returns matching text; (d) a
    tool-level `ArgumentError` comes back as `isError` data, not a raised
    exception; (e) spawning a nonexistent command raises the Python
    `FileNotFoundError`/`OSError` equivalent of Ruby's `Errno::ENOENT`;
    (f) prefixing applies agent-side only, bare names work with no
    prefix; (g) a name collision (same prefix registered twice, or
    against a pre-existing non-MCP tool) raises `CollisionError` naming
    the fix; (h) the enum-bearing `move` tool's parameter description
    surfaces "(one of: ...)".
23. Run `./week1_baseline/bin/python/10_standard_tool_library` against
    the real `.boukensha/settings.yaml` (which already has a working
    `mcp_servers: mud:` entry from this session's live debugging) and
    confirm it reaches the real MUD on port 4000 — the same live
    connection already proven from the Ruby side, now proven from Python
    too. Ask before spending this live budget, same as every prior step.
24. Port `README.md`: `Mcp::Client`/`Tools::Mcp` docs, the `mcp_servers:`
    schema table, "what went away" section, and a Considerations section
    covering: the language-agnostic-MCP-host point (no Python MUD code
    needed), the loader's `sys.path`/`sys.modules` mechanism and why it's
    sufficient for a one-shot CLI, the two discovered-and-matched
    regressions (401 handling, config dir tiers) with the fidelity
    reasoning, and that this port still doesn't mechanically translate
    Ruby's `test/` tree (same as every prior step).

## Open questions

Resolved during planning, without a fresh round of questions (the user
explicitly asked to proceed directly rather than pause again; reasoning
recorded here for visibility and so it can be revisited on review):

1. **How to translate `boukensha_loader.rb`'s dynamic "pick which step's
   package backs `import boukensha` at runtime" mechanism**, since no
   prior step needed anything like it — **resolved: `sys.path` +
   `sys.modules` cache-busting**, not `importlib.util.spec_from_file_location`.
   Sufficient for a one-shot CLI invocation; the heavier importlib
   approach would only earn its complexity if `boukensha` risked already
   being cached from an earlier import in a long-running process, which
   doesn't apply here.
2. **Whether to match or preserve-past-Ruby on the 401 `ApiError`
   message** (added in step 08, silently absent in step 10's `client.rb`)
   — **resolved: match Ruby's current state** (drop it), per this port's
   fidelity-to-the-current-lesson stance.
3. **Whether to match or preserve-past-Ruby on `Config`'s 3-tier vs.
   2-tier directory resolution** (3-tier added in step 08, silently back
   to 2-tier in step 10's `config.rb`) — **resolved: match Ruby's current
   state** (2-tier), same reasoning as #2.

Still open, worth a real decision before or during execute (lower stakes
than the above — flagging rather than resolving unilaterally):

4. **Whether to write a committed Python test suite for the new MCP
   client/host code**, given step 10 is the first Ruby step to ship a
   real `test/` directory at all, and its tests were genuinely valuable
   as a reference contract during this session's Ruby-side daemon work.
   Every prior Python step skipped formal test-suite porting in favor of
   execute-phase mock/manual verification (see task 22 above, which
   reuses that pattern) — this plan defaults to continuing that
   precedent, but step 10's tests were unusually load-bearing (they
   caught real, otherwise-invisible contract details like the exact
   `argument_error:`-prefixed error text and prefix-collision ordering),
   so it's worth confirming that skipping a committed suite is still the
   right call here rather than assuming it silently.
