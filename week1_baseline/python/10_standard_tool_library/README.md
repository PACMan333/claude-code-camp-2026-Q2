# 10 · A Standard Tool Library (Python port)

Python port of `week1_baseline/ruby/10_standard_tool_library`. This step
removes every built-in tool boukensha ever had. The agent becomes a pure
**MCP host**: it spawns whatever's listed in `settings.yaml`'s
`mcp_servers:` block as subprocesses, speaks MCP-over-stdio to each, and
registers their advertised tools. Want file access? Point at a filesystem
MCP server. Want to play a MUD? Point at `mud-manager --mcp`. Swapping
what the agent can do is a config edit, not a code change.

This step also absorbs Ruby step 09 (`global_executable`), which was
never separately ported to Python — Ruby's step 10 source already
contains everything step 09 introduced (`boukensha_loader.rb`,
`bin/boukensha`, the gemspec) baked in alongside step 10's own MCP work,
so this Python port covers both in one place. Everywhere below, "the
previous step" means `python/08_the_repl_loop`, the last one actually
built.

**Like steps 04–08, this step's example makes real, billed HTTP requests
to a live LLM API** (via `Client`/`Agent`, inherited, not new) — and,
new this step, a real MCP server subprocess gets spawned too (the
`mud-manager` daemon connecting to a real MUD), though that connection
itself is lazy and free until the agent sends its first gameplay action.

## The key idea: MCP hosting is language-agnostic — no MUD code needed here

The whole point of this step is that boukensha ships zero tools of its
own. The `mud-manager --mcp` daemon this repo's Ruby side spawns (see
`week0_explore/mud_manager/bin/mud-manager`) is just an external process
speaking a wire protocol — **the exact same daemon works as this Python
port's MCP server too**, with zero Python-side MUD code. The real work in
this step is porting the generic *host* layer:
`Boukensha::Mcp::Client`/`Boukensha::Tools::Mcp` → `boukensha.mcp.Client`/
`boukensha.tools.mcp`.

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/10_standard_tool_library/requirements.txt
.venv/bin/pip install -e week1_baseline/python/10_standard_tool_library
```

This step is a self-contained copy of the `boukensha` package. `tool.py`,
`message.py`, `errors.py`, `prompt_builder.py`, `logger.py`, `agent.py`,
`tasks/player.py`, `tasks/base.py`, `backends/base.py`, and all five
backends are copied forward unchanged from `python/08_the_repl_loop`.
Installing this step editable repoints `import boukensha` at this step's
copy — and also registers a real `boukensha` console command (see below).

## New Files

| File | Description |
|---|---|
| `boukensha/mcp/client.py` | `Client` — minimal MCP-over-stdio client: spawn, handshake, `tools/list`, `tools/call` |
| `boukensha/tools/mcp.py` | `register`/`register_client` — registers a spawned server's tools into a `Registry`, with prefixing and collision detection |
| `boukensha_loader.py` | Resolves which step's package to load and which config dir to use, then boots the REPL — the "global executable" concept from Ruby step 09 |
| `bin/boukensha` | Shebang script delegating to the loader (mirrors Ruby's `bin/boukensha`) |

## Updated Files

| File | Change |
|---|---|
| `boukensha/__init__.py` | `run()`/`start_repl()` gain `working_dir=` (metadata only) and call a new `_register_mcp_servers` helper; `start_repl` passes a `servers=` summary to `Repl` |
| `boukensha/config.py` | Drops `mud_host`/`mud_port`/`mud_username`/`mud_password` for good this time (superseded by `mcp_servers()`, not oscillating dead code); `_resolve_dir` reverts to 2-tier (see Considerations) |
| `boukensha/client.py` | Drops the 401-specific `ApiError` message added in step 08 (see Considerations) |
| `boukensha/context.py` | Adds `working_dir` — metadata only, registers nothing |
| `boukensha/registry.py` | Adds `tool_names()` |
| `boukensha/run_dsl.py` | Adds `tool_names()`, delegating to the registry |
| `boukensha/repl.py` | Accepts `servers=`; banner gains a `servers:` line |
| `boukensha/version.py` | `"0.8.0"` → `"0.10.0"` |
| `pyproject.toml` | Adds `py-modules = ["boukensha_loader"]` and a `[project.scripts] boukensha = "boukensha_loader:main"` entry point |

## `boukensha.mcp.Client` / `boukensha.tools.mcp`

```python
client = boukensha.mcp.Client.spawn(command="mud-manager", args=["--mcp"])
for t in client.tools:
    print(t["name"])
print(client.call_tool("look")["text"])
client.close()

# Or, to register a server's tools straight into a Registry:
boukensha.tools_mcp.register(
    registry, command="mud-manager", args=["--mcp"],
    env={"MUD_HOST": "localhost"}, prefix="tbamud",  # -> tbamud__look
)
```

`Client` spawns the server via `subprocess.Popen` (Ruby's `Open3.popen3`
equivalent), does the `initialize`/`notifications/initialized` handshake,
fetches `tools/list`, and lets you `call_tool(name, arguments)`. It knows
nothing about any particular server — MUD, filesystem, anything that
speaks MCP works identically.

`register`/`register_client` turn a spawned client's advertised tools
into `Registry` tools, applying an optional `prefix` (agent-side only —
the server always sees its own bare name on the wire) and raising
`CollisionError` if a name is already taken, whether by another MCP
server or a tool boukensha registered some other way.

## `mcp_servers:` in `settings.yaml`

```yaml
mcp_servers:
  mud:
    command: mud-manager
    args:    [--mcp]
    prefix:  tbamud
    env:
      MUD_HOST:     your.mud.host
      MUD_NAME:     Gandalf
      MUD_PASSWORD: secret

  filesystem:
    command:  npx
    args:     [-y, "@modelcontextprotocol/server-filesystem", /tmp]
    prefix:   fs
    required: false          # can't start? warn and carry on
```

| Key | Default | Meaning |
|---|---|---|
| `command` | — | Executable to spawn. Resolved by the OS, so a relative path depends on cwd. |
| `args` | `[]` | Its argv. |
| `env` | `{}` | Extra environment — the server also inherits this process's full environment; these keys override it. |
| `prefix` | none | Scopes discovered names (`fs` → `fs__read_file`). |
| `required` | `true` | `false` downgrades a failed spawn into a warning instead of an error. |

`boukensha.run`/`start_repl` call a new `_register_mcp_servers` at
startup, spawning every configured server and registering its tools —
this is the agent's *only* source of tools now.

## The Global Executable (`boukensha` command)

```bash
.venv/bin/boukensha
```

Works from anywhere once installed — no `cd` into a step folder needed.
Which implementation and which config directory it uses are each
resolved independently:

| Setting | 1st priority | 2nd priority | Default |
|---|---|---|---|
| Implementation | `BOUKENSHA_PATH` env var | `boukensha_path` in `~/.boukensharc` | This step's own bundled package |
| Runtime config | `BOUKENSHA_DIR` env var | `boukensha_dir` in `~/.boukensharc` | `~/.boukensha` |

```bash
BOUKENSHA_PATH=~/Sites/boukensha/week1_baseline/python/04_api_client .venv/bin/boukensha
# => boukensha: the step at .../04_api_client does not support the
#    interactive REPL (added in step 7)...
```

`~/.boukensharc` is YAML (a bare single-line path is still accepted, for
backward compatibility with the original pre-step-9 format):

```yaml
boukensha_path: ~/Sites/boukensha/week1_baseline/python/10_standard_tool_library
boukensha_dir: ~/projects/mybot/.boukensha
```

`BOUKENSHA_DEBUG=1` prints the resolved step directory on startup.

There's also a plain `bin/boukensha` script in this step's own folder
(mirroring Ruby's), usable without a real `pip install` — but note its
`#!/usr/bin/env python3` shebang uses the *system* Python, which won't
have `pyyaml`/`python-dotenv` installed unless you run it explicitly via
this repo's venv (`.venv/bin/python bin/boukensha`). The real "global
executable" experience is the `[project.scripts]` entry point
(`.venv/bin/boukensha`, or plain `boukensha` after a real `pip install`
outside this dev venv) — `pip` wires that one to the correct interpreter
automatically.

## Task Configuration

Unchanged from steps 05–08 for the `tasks:` block; `mcp_servers:` is new
(see above).

## Considerations

**No MUD-specific Python code exists anywhere in this port, and that's
the point.** `examples/mcp_mud_demo.py` and the real `.boukensha/settings.yaml`
both spawn the *same* Ruby `mud-manager --mcp` daemon the Ruby port
spawns — proof that MCP hosting is genuinely language-agnostic. Verified
live: this port's `boukensha.run(...)` reached the real MUD on port 4000
through that daemon, in the same session that built and fixed the daemon
itself (see the daemon's own history for two real bugs found and fixed
along the way — a login-drain race and an over-eager `target: "room"`
tool call — both benefit this port automatically since it's the same
daemon).

**Two Ruby regressions relative to `python/08_the_repl_loop`, matched
rather than preserved-from-Python.** Both were added in step 08 and
silently absent by step 10's Ruby source, with nothing in the
README/tests/comments explaining either as deliberate:
- The 401-specific `ApiError` message is gone from `client.rb`; `client.py`
  drops it too.
- `Config#resolve_dir`'s 3-tier form (env → cwd `.boukensha/` → home)
  reverted to 2-tier (env → home); `config.py` matches.

Resolved in favor of fidelity to what the *current* Ruby step actually
teaches, not preservation of a prior Python step's improvement the
current Ruby source no longer has — consistent with this port's general
policy of mirroring the real diff rather than editorializing about churn
in the lesson's own history (the same treatment the `mud_host`/`LoopError`
deletions-and-re-additions got in earlier steps).

**The loader (`boukensha_loader.py`) uses `sys.path` + `sys.modules`
cache-busting, not `importlib.util.spec_from_file_location`.** This is
the first time this port has needed a *dynamic* "which package backs this
name at runtime" mechanism — every step before this assumed whatever's
currently `pip install -e`'d is `boukensha`. Prepending the resolved
step's directory to `sys.path` and discarding any stale
`sys.modules["boukensha"]`/`boukensha.*` entries before a fresh `import boukensha`
mirrors Ruby's own path-based `$LOAD_PATH.unshift` + `require` mechanism
directly, and is sufficient for a one-shot CLI invocation that runs once
and exits — there's no risk of `boukensha` already being cached from an
earlier import in the same process, the scenario that would make the
heavier `importlib` approach worth its extra complexity.

**`subprocess.Popen(env=...)` replaces the environment; Ruby's
`Open3.popen3(env, *cmd)` merges it.** A literal `env=server_env` would
wipe `PATH` and everything else a spawned server needs to even be found —
`Client.__init__` builds `merged_env = {**os.environ, **server_env}`
explicitly before spawning, matching Ruby's actual (merge, not replace)
behavior.

**Boukensha's tool-call kwargs need no symbol→string transform on the
Python side.** Ruby's `registry.tool(local) { |**kwargs| ... client.call_tool(remote, kwargs.transform_keys(&:to_s)) }`
needs that transform because Ruby's `**kwargs` splat produces
*symbol*-keyed hashes; Python's `Registry.dispatch` already calls tool
blocks with string-keyed `**(args or {})` (from JSON), so a Python tool
block declared `def block(**kwargs)` receives string keys natively — a
direct simplification, not a behavior gap, the same class already
catalogued for other symbol/string situations in earlier steps.

**No committed Python test suite for the new MCP code, consistent with
every prior step.** Ruby step 10 is the first to ship a real `test/`
directory, and it was genuinely valuable as a reference contract while
building the daemon this session (it's what pinned down the exact
`argument_error:`-prefixed error text, prefix-collision ordering, and
tool-result shape) — but steps 00–08 never mechanically ported Ruby's
Minitest suites into a Python `pytest`/`unittest` tree either, relying
instead on execute-phase mock/manual verification. This port continues
that precedent: the same scenarios the Ruby tests cover (handshake,
discovery, dispatch, error-as-data, spawn failure, prefixing, collision
detection, enum surfacing) were all exercised directly against the real
daemon during this step's build, just not committed as a formal suite.

**`examples/mcp_mud_demo.py`'s `--dry` mode spawns a throwaway Ruby
process to host `MudManager::FakeMud`**, rather than reimplementing a
fake MUD in Python — there's no reason to duplicate a perfectly good
fixture the Ruby side already has, and it's one more small proof that
this port's MCP layer doesn't care what language is on the other end of
the pipe. One naming note: the Ruby demo's comments reference a
`cast_spell` tool; this session's rebuilt `mud-manager` daemon (the
original reference implementation was lost — see the daemon's own build
history) names every tool after its underlying `MudManager::Primitives`
method directly, so this is `cast`, not `cast_spell`. The Python demo
uses the name that actually exists.

## Run Example

```bash
./week1_baseline/bin/python/10_standard_tool_library
```

Prints the config, the configured MCP server names, and whether an API
key is set, then asks the agent to look around, check its score, and
check the exits — same as `example.rb`, this doesn't print the agent's
final response either (neither does the Ruby source this step; every
phase is still written to `.boukensha/sessions/<session-id>.jsonl` if you
want to see what happened).

```bash
python examples/mcp_mud_demo.py --dry    # offline smoke test, no API key, no live MUD
python examples/mcp_mud_demo.py          # same as example.py
```
