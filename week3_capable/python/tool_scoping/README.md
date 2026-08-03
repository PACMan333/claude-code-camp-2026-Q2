# Week 3 (Capable) · Tool Scoping

A full, self-contained copy of `week1_baseline/python/12_context`'s
`boukensha` package (same copy-forward-not-diff convention Week 1 used for
every step), with one new capability: **which MCP tools actually get
registered — and therefore sent to the model on every API call — is now
configurable per server, tool by tool, in `settings.yaml`.**

Everything from Week 1 (context/token tracking, auto-compaction, the
MCP-host tool model, the Textual TUI, all five provider backends) is
unchanged in its fundamentals here — see
`week1_baseline/python/12_context/README.md` for that material. This
README covers only what this track adds.

## Setup

Uses the same shared repo-root `.venv` as `week1_baseline`:

```bash
.venv/bin/pip install -r week3_capable/python/tool_scoping/requirements.txt
.venv/bin/pip install -e week3_capable/python/tool_scoping
```

No new third-party dependency (still `PyYAML`, `python-dotenv`, `textual`).

## The problem this solves

The agent's tools all come from MCP servers declared in `settings.yaml`'s
`mcp_servers:` block — boukensha ships none of its own. Every tool a server
advertises via `tools/list` used to get registered unconditionally, and
every registered tool is serialized into the `tools:` array of *every*
`POST /v1/messages` call. Against this repo's `mud-manager` fixture
(`week0_explore/mud_manager`) that's 55 tool definitions on every call —
input tokens, model attention, and cost spent on tools the agent has never
once reached for. In practice, only three get used: moving, examining
things, and checking your own status.

## Scoping which MCP tools get registered

Add an optional `tools:` table under any `mcp_servers.<name>` entry:

```yaml
mcp_servers:
  mud:
    command: mud-manager
    args:    [--mcp]
    prefix:  tbamud
    tools:
      move:    on
      look:    off
      examine: on
      info_self:
        "on": true
        as: check
      # ...every other tool the server can advertise, off
```

**No `tools:` key at all** → unchanged default behavior: register
everything the server advertises, under its own name (or
`prefix + "__" + name`).

**A `tools:` key present** — even with every entry `off`, even an empty
mapping — switches that server to explicit mode: only tools listed *and*
`on` get registered. Anything not mentioned in the table at all is treated
as off. This is deliberate for a fully-enumerated table like the one
shipped in the repo's real `.boukensha/settings.yaml` (all 55 of
`mud-manager`'s tools listed, only 3 `on`): flipping a tool back on is a
one-line edit (`off` → `on`), never a code change, and you never have to
remember or retype the exact tool name — it's already sitting there in the
file, correctly spelled, matching `mud_manager/lib/mud_manager/primitives.rb`'s
`TOOLS` array 1:1.

Each entry is either a bare `on`/`off`, or — when the tool should be
renamed — a small mapping with `"on":`/`as:`. **Quote the `"on"` key when
using the mapping form.** PyYAML's implicit resolver treats a bare `on` as
the boolean `True` even when it appears as a *mapping key*, not just a
value — `info_self: {on: true, as: check}` parses as `{True: True, "as":
"check"}`, silently losing the `on` flag under a boolean key instead of a
string one. `Config._parse_tools` guards against this (it checks both the
string key and the boolean-`True` key), so an unquoted `on:` still works —
but the shipped config quotes it (`"on": true`) to be unambiguous on
inspection rather than relying on that fallback.

### Renaming a tool: `tbamud__check`

The real tbaMUD server has a genuine `check` command, but
`mud_manager`'s MCP wrapper doesn't expose one — it only wraps 55 of
tbaMUD's ~140 raw commands into MCP tools, several as grouped,
parameterized wrappers rather than 1:1 passthroughs. `info_self(kind:)` is
one such wrapper: its `kind` enum (`score`, `inventory`, `equipment`,
`gold`, `exits`, `time`, `weather`, `levels`, `wimpy`, `toggle`, `where`)
sends `kind` straight through as the raw MUD verb — `info_self(kind:
"exits")` sends the literal `exits` command.

Rather than adding a new tool to `mud_manager`'s Ruby primitives layer (a
different package), `info_self` is renamed to `check` **at the boukensha
registration layer only**:

```yaml
info_self:
  "on": true
  as: check
```

The agent sees and calls `tbamud__check` — e.g.
`{"name": "tbamud__check", "input": {"kind": "exits"}}` — with the exact
same `kind` enum `info_self` always had. The wire call to `mud-manager`
is completely unaffected: it always sends `"name": "info_self"`. The
rename is agent-side-only, exactly like `prefix:` already was.

### How it's implemented

- `Config.mcp_servers()` (`boukensha/config.py`) parses each server's
  `tools:` table into `{remote_name: {"enabled": bool, "as": str|None}}`.
  `None` (key absent) means unfiltered.
- `boukensha.tools.mcp.register`/`register_client` (`boukensha/tools/mcp.py`)
  apply the filter and the rename at the one place that turns "what the
  server advertises" into "what the agent can call" — nothing downstream
  (`Context`, the `Anthropic` backend's `to_tools`, `Registry`) needs to
  know either mechanism exists. A config entry naming a tool the server
  doesn't actually advertise (typo, or the server's tool list changed)
  prints a warning rather than raising — same tone as an optional server
  that fails to spawn.
- `_register_mcp_servers` (`boukensha/__init__.py`) now derives each
  server's tool-count summary (shown in the REPL/TUI) from a
  before/after `registry.tool_names()` diff, not the server's raw
  advertised count — otherwise a 3-tool config against a 55-tool server
  would still report "55 tools," looking like the feature silently didn't
  work.

## Run the demo

```bash
# Offline, no API key, no live MUD -- uses the daemon's built-in fake MUD.
# Demonstrates the real move/examine/check(info_self) table against the
# actual mud-manager process: confirms the daemon advertises 55 tools but
# the agent only registers 3, and that tbamud__check really does reach
# info_self on the wire.
python examples/mcp_mud_demo.py --dry

# One-shot demo against the real Anthropic API + real mud-manager daemon,
# using .boukensha/settings.yaml's tools: table:
python examples/example.py
```

## Considerations

**The shared root `.boukensha/settings.yaml` fixture was edited in place**
(backed up first to `settings.yaml.bak`), not forked into a separate config
tree — a deliberate choice to keep one config, at the cost of also scoping
down `week1_baseline/python/12_context`'s own demo to the same 3 tools when
it's run against this fixture.

**No tests were carried forward from `12_context`'s absence of a test
suite; this track adds one.** `tests/test_tools_mcp.py` unit-tests the
filter/rename logic against an in-process fake MCP client double (no
subprocess, no MUD) — collision handling, the all-`off`-means-nothing edge
case, and the alias-affects-only-the-local-name property are all covered
there. `examples/mcp_mud_demo.py --dry` is the only check that exercises it
against the real `mud-manager` daemon.
