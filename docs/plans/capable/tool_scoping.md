# Week 3 (Capable) Plan — Scoped MCP Tool Registration

## Problem

The agent's tools all come from the `mud-manager` MCP server (see
`week1_baseline/python/12_context/boukensha/tools/mcp.py`): on startup,
`_register_mcp_servers` calls `tools_mcp.register(...)`, which registers
**every** tool the server's `tools/list` advertises into the `Context`. Every
registered tool is then serialized into the `tools:` array of every
`POST /v1/messages` call (`Anthropic.to_tools`, in
`boukensha/backends/anthropic.py`) — whether the agent ever calls it or not.

Against the repo's own `mud-manager` fixture
(`week0_explore/mud_manager/bin/mud-manager`, `lib/mud_manager/primitives.rb`
`TOOLS`) that's currently 55 advertised tools. In practice the user has only
ever seen the agent reach for three: `tbamud__move`, `tbamud__examine`,
`tbamud__check`. Every other tool definition sent is pure token overhead on
every single API call — input tokens, model attention, and (uncached) cost,
with no behavioral upside.

**`check` doesn't exist as a `mud-manager` tool today.** The real tbaMUD
server has ~140 raw commands (confirmed against the user's pasted `commands`
listing), including a literal `check`. `mud_manager/lib/mud_manager/primitives.rb`
wraps only 55 of those into MCP tools, several as grouped/parameterized
wrappers rather than 1:1 passthroughs — `info_self(kind:)` is one such
wrapper, and its `kind` enum (`score`, `inventory`, `equipment`, `gold`,
`exits`, `time`, `weather`, `levels`, `wimpy`, `toggle`, `where`) sends
`kind` straight through as the raw MUD verb (`info_self(kind: "exits")` →
raw `exits` command). There's no dedicated `check` wrapper.

**Resolved (this conversation):** rather than adding a new tool to
`mud_manager`'s Ruby primitives layer (a different package, out of scope
here), rename `info_self` to `check` **at the boukensha registration layer
only** — the agent sees `tbamud__check` and calls it exactly like
`info_self` (`{"kind": "exits"}`, etc.); the wire call to `mud-manager`
still sends `"name": "info_self"` (the server never hears about the rename,
same as prefixing already works). This needs one new capability beyond
plain on/off filtering: **per-tool renaming**, not just enable/disable.

## Goal

Make the set of tools actually registered (and therefore sent to the Claude
API) configurable in `settings.yaml`: every tool the `mud` MCP server can
advertise gets its own on/off switch, all 55 listed explicitly (not an
allowlist users have to keep in sync by hand — a full toggle table they can
flip). Two are `on` initially (`move`, `examine`), plus `info_self`
re-exposed as `tbamud__check` (also `on`). The other 52 are `off`. Turning
one back on is a one-line edit (`off` → `on`), no code change, no need to
remember the exact bare name (it's already sitting there in the file).

## Where the new code lives

Per-step copy-forward convention already established by
`week1_baseline/python/*` (see `docs/plans/python_port/12_context.md`): a
full, self-contained copy of the package, not a diff layered in place.
**Per user decision, no numeric step prefix for this new track** (Week 1's
`NN_name` convention doesn't carry over):

```
week3_capable/
└── python/
    └── tool_scoping/            # full copy of week1_baseline/python/12_context/
        ├── README.md
        ├── requirements.txt
        ├── pyproject.toml
        ├── bin/boukensha
        ├── boukensha_loader.py
        ├── examples/
        │   ├── example.py
        │   └── mcp_mud_demo.py
        ├── prompts/system.md
        ├── tests/
        │   └── test_tools_mcp.py      # new
        └── boukensha/
            ├── config.py               # changed
            ├── tools/mcp.py            # changed
            ├── __init__.py             # changed
            └── ... (everything else copied forward unchanged)
```

`week1_baseline/python/12_context` is untouched — it stays exactly as the
Week 1 lesson left it. All work for this feature happens only inside the
new `week3_capable/python/tool_scoping/` copy.

## Config: edit the shared root fixture directly

**Resolved (user decision, supersedes the earlier fork-a-new-`.boukensha`-dir
proposal):** edit `.boukensha/settings.yaml` (the repo-root fixture every
`week1_baseline/python/*` step's `examples/example.py` already points at)
in place, after taking an explicit backup copy first:

1. `cp .boukensha/settings.yaml .boukensha/settings.yaml.bak` before any
   edit (belt-and-suspenders alongside git history — the file is already
   tracked and currently clean, but an explicit on-disk backup was
   requested directly).
2. Edit `.boukensha/settings.yaml`'s `mcp_servers.mud` block in place per
   the schema below.

This means Week 1's `python/12_context` demo (and every earlier step that
shares the same fixture) will also see the scoped-down tool set once this
lands — accepted tradeoff per user decision; simpler than maintaining two
config trees, and arguably desirable anyway (cheaper to run).
`week3_capable/python/tool_scoping/examples/example.py` keeps the same
`BOUKENSHA_DIR` default (`<repo root>/.boukensha`) as `12_context` — no new
config directory needed.

## Design

### 1. `settings.yaml` schema — full per-tool table, on/off + rename

```yaml
mcp_servers:
  mud:
    command: ruby
    args:    [/home/p_coz/Claude/claude-code-camp-2026-Q2/week0_explore/mud_manager/bin/mud-manager, --mcp]
    prefix:  tbamud
    env:
      MUD_HOST:     localhost
      MUD_PORT:     "4000"
      MUD_NAME:     dummy
      MUD_PASSWORD: helloworld
    tools:
      # Perception
      look:            off
      # Movement & posture
      move:            on
      enter:           off
      leave:           off
      set_position:    off
      follow:          off
      flee:            off
      track:           off
      # Combat
      attack:          off
      skill_strike:    off
      order:           off
      insult:          off
      # Communication
      say_local:       off
      say_targeted:    off
      say_channel:     off
      say_group:       off
      say_quest:       off
      report_player:   off
      write_note:      off
      # Inventory & objects
      get:             off
      drop:            off
      put:             off
      give:            off
      equip:           off
      consume:         off
      transfer_liquid: off
      split_gold:      off
      # Doors
      door:            off
      # Perception & info
      examine:         on
      info_self:                  # exposed to the agent as tbamud__check,
        on: true                  # not tbamud__info_self -- same tool,
        as: check                 # same kind: enum (score/inventory/
                                   # equipment/gold/exits/time/weather/
                                   # levels/wimpy/toggle/where), renamed
                                   # only at the boukensha registration
                                   # layer. The server is still called with
                                   # "name": "info_self" on the wire.
      info_world:      off
      consider:        off
      diagnose:        off
      list_commands:   off
      # Character / preferences / lifecycle
      social:          off
      set_title:       off
      set_display:     off
      set_color:       off
      set_wimpy:       off
      toggle_pref:     off
      stealth:         off
      steal:           off
      practice:        off
      define_alias:    off
      save_char:       off
      quit:            off
      # Magic
      cast:            off
      use_magic_item:  off
      # Group
      group_manage:    off
      report_hp:       off
      # Room-procedural
      shop:            off
      bank:            off
      mail:            off
      rent:            off
      house_admin:     off
```

Keys are the tool's **remote** (server-side) name — the same name
`mud-manager`'s `tools/list` advertises, matching every other entry in
`TOOLS` (`lib/mud_manager/primitives.rb`). This is deliberate: a reader can
line this table up 1:1 against that source file. Renaming only changes what
the *agent* sees (`tbamud__check`), never what's sent over the wire to
`mud-manager` (`"name": "info_self"`).

Each value is either a bare `on`/`off` (the common case), or, when a rename
is needed, a small mapping (`on:`/`as:`). PyYAML's default (`yaml.safe_load`)
resolves unquoted `on`/`off`/`yes`/`no`/`true`/`false` to Python booleans via
its YAML 1.1 implicit resolver — confirmed, relied-upon behavior here, not
an accidental gotcha; `Config`'s parsing treats both a native bool and a
quoted string the same way regardless (see below), so `"on"`/`'off'` typed
as literal strings also work if a future editor's YAML linter insists on
quoting them.

**No `tools:` key on a server at all** → unchanged existing behavior:
register everything the server advertises, under its own bare name (or
`prefix + name` if `prefix:` is set). This keeps the feature fully
backward-compatible for any `mcp_servers` entry that doesn't opt in.

**A `tools:` key present** (even if every entry is `off`, even if it's
technically an empty mapping) → explicit mode: only tools listed *and*
`on` are registered; anything not mentioned in the table at all is treated
as `off`. This matters for the "exhaustive table" approach specifically —
an all-`off` table must mean "register nothing," not silently fall back to
"register everything" because an empty/all-false collection is falsy in
Python. The code must key off "was a `tools:` mapping present," not "is it
truthy."

### 2. `Config.mcp_servers()` — parse the per-tool table

`week3_capable/python/tool_scoping/boukensha/config.py`:

```python
def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
    raw_servers = self.dig("mcp_servers") or {}
    out: Dict[str, Dict[str, Any]] = {}
    for name, raw in raw_servers.items():
        entry = raw if isinstance(raw, dict) else {}
        required = entry.get("required")
        raw_tools = entry.get("tools")
        out[str(name)] = {
            "command": str(entry.get("command") or ""),
            "args": [str(a) for a in (entry.get("args") or [])],
            "env": {str(k): str(v) for k, v in (entry.get("env") or {}).items()},
            "prefix": str(entry["prefix"]) if entry.get("prefix") else None,
            "required": True if required is None else bool(required),
            "tools": self._parse_tools(raw_tools) if isinstance(raw_tools, dict) else None,
        }
    return out

@staticmethod
def _parse_tools(raw_tools: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """{"move": on/off, "info_self": {"on":, "as":}} -> {remote_name:
    {"enabled": bool, "as": str|None}}. Any `tools:` mapping present at
    all -- even empty, even all-off -- switches the server into explicit
    mode (see the schema note above); only `None` (key absent) means
    "unfiltered."
    """
    out = {}
    for remote, spec in raw_tools.items():
        if isinstance(spec, dict):
            enabled = Config._truthy(spec.get("on", True))
            alias = str(spec["as"]) if spec.get("as") else None
        else:
            enabled, alias = Config._truthy(spec), None
        out[str(remote)] = {"enabled": enabled, "as": alias}
    return out

@staticmethod
def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("on", "true", "yes", "1")
    return bool(value)
```

Update the docstring above `mcp_servers()` with the new `tools:` example
(the worked `mud` block above, trimmed).

### 3. `boukensha/tools/mcp.py` — filter + rename at registration time

This is the one place that turns "what the server advertises" into "what
the agent can call," so it's the right layer for both the filter and the
rename — nothing downstream (`Context`, the `Anthropic` backend's
`to_tools`, `Registry`) needs to know either exists.

```python
def register(registry, *, command, args=None, env=None, prefix=None, tools=None):
    ...
    client = Client.spawn(command=command, args=args or [], env=env or {})
    ...
    register_client(registry, client, prefix=prefix, tools=tools)
    return client


def register_client(registry, client, *, prefix=None, tools=None):
    """Register an already-spawned client's tools. `tools`, if given, is
    `{remote_name: {"enabled": bool, "as": str|None}}` (Config._parse_tools'
    shape) -- `None` means unfiltered (register everything, today's
    behavior). Returns the count actually registered.
    """
    taken = list(registry.tool_names()) if hasattr(registry, "tool_names") else []
    filtering = tools is not None
    seen = set()

    for tool in client.tools:
        remote = tool["name"]
        spec = tools.get(remote) if filtering else None
        if filtering and (spec is None or not spec["enabled"]):
            continue
        seen.add(remote)

        alias = spec["as"] if spec else None
        local = prefixed(alias or remote, prefix)

        if local in taken:
            raise CollisionError(
                "boukensha: MCP tool name collision on '{}' — a tool by that "
                "name is already registered. Give this server a distinct `prefix:` "
                "in mcp_servers.".format(local)
            )
        taken.append(local)

        def block(_remote=remote, _client=client, **kwargs):
            result = _client.call_tool(_remote, kwargs)
            return "error: {}".format(result["text"]) if result["error"] else result["text"]

        registry.tool(
            local,
            description=str(tool.get("description") or ""),
            parameters=to_boukensha_params(tool.get("inputSchema")),
            block=block,
        )

    if filtering:
        missing = sorted(
            name for name, spec in tools.items() if spec["enabled"] and name not in seen
        )
        if missing:
            print(
                "[boukensha] MCP server tool config lists {} tool(s) the server "
                "doesn't advertise: {} — check settings.yaml's mcp_servers "
                "entry".format(len(missing), ", ".join(missing))
            )

    return len(seen)
```

Key points, since this changes shape from the allowlist-of-names version
discussed earlier in this planning session:

- **`alias` only affects `local`** (what gets registered into the
  `Registry`/`Context`, therefore what name Claude sees and calls). The
  closure's `_remote` — what's actually sent to `mud-manager` in
  `call_tool(_remote, kwargs)` — is untouched by aliasing. This is exactly
  how `tbamud__check` ends up making a real, correct
  `{"name": "info_self", "arguments": {"kind": "exits"}}` call on the wire
  even though the agent never hears the name `info_self` at all.
- A config entry naming a tool the server doesn't actually advertise
  (typo, or the server's `TOOLS` list changed) degrades to a printed
  warning, not a crash — same tone as the existing "optional server that
  fails to spawn" handling in `_register_mcp_servers`, not the harder
  failure mode used for genuine name collisions.
- An all-`off` `tools:` table (`filtering=True`, every `spec["enabled"]`
  False) registers zero tools from that server — correct per the schema
  note in section 1, verified by a dedicated test (see Testing below).

### 4. `boukensha/__init__.py` — wire the config through, fix the summary count

`_register_mcp_servers` currently does:

```python
client = tools_mcp.register(registry, command=..., args=..., env=..., prefix=entry["prefix"])
summary[name] = len(client.tools)
```

`len(client.tools)` is the server's *advertised* count, not what got
registered — today those are the same number, so the bug is latent. Once
filtering exists they diverge (a 3-tool config against a 55-tool server
would still report "55 tools" in the REPL/TUI status line, which would
look like the feature silently didn't work). Fix, resolved earlier in this
planning session (and reconfirmed: `register_client`'s return value has
exactly one caller in the whole codebase today, so changing its meaning is
safe — nothing else in this repo snapshot consumes it):

```python
client = tools_mcp.register(
    registry, command=entry["command"], args=entry["args"],
    env=entry["env"], prefix=entry["prefix"], tools=entry["tools"],
)
```

Concretely: snapshot `before = set(registry.tool_names())` before calling
`tools_mcp.register(...)`, then
`summary[name] = len(set(registry.tool_names()) - before)` after. This
needs no signature change to `register()`'s return value at all (it still
just returns `client`, unaffected for `examples/mcp_mud_demo.py`'s existing
call sites, which use `client.tools` for their own unfiltered diagnostic
printout — that's still accurate, since `client.tools` legitimately means
"what the server has"; it was only the
*summary-as-a-proxy-for-registered-count* assumption in `__init__.py` that
was wrong).

### 5. Tests

`week3_capable/python/tool_scoping/tests/test_tools_mcp.py` — new (this
step's Python line has no test suite yet). Use a small in-process fake MCP
client double — `register_client` only needs an object with a `.tools`
list of `{"name":, "description":, "inputSchema":}` dicts and a
`.call_tool(name, args)` method — so the filtering/renaming logic can be
unit-tested with no subprocess, no MUD, no network:

- `tools=None` registers every tool the fake advertises, under bare (or
  prefixed) names — today's behavior, unchanged.
- A table with a mix of `on`/`off` registers exactly the `on` ones.
- An all-`off` table registers zero tools (the specific footgun called out
  in section 1 — must not silently fall back to "register everything").
- A tool marked `on` with `as: "renamed"` registers under
  `prefixed("renamed", prefix)`, **not** `prefixed(remote, prefix)`; the
  fake client's `call_tool` spy still receives the *original remote name*
  when the renamed tool is dispatched (proves the wire call is unaffected
  by the alias — the specific correctness property behind
  `tbamud__check` → real `info_self` calls).
- A table entry naming a tool the fake doesn't advertise is skipped
  silently (registration doesn't raise); assert the warning is printed
  (capture stdout) and that registration still succeeds for the names that
  *did* match.
- Filtering/renaming still composes with the existing collision check: two
  servers whose *local* (post-alias, post-prefix) names collide still
  raise `CollisionError` — e.g. one server renaming a tool to `move` while
  another genuinely advertises `move` under the same prefix.
- `register_client`'s return value equals the number of tools actually
  registered by that call (not the fake's total advertised count) when
  filtering narrows the set.

Optionally, update `examples/mcp_mud_demo.py`'s `--dry` path (against the
real fake-MUD-over-Ruby-subprocess harness it already spins up) to pass the
real `move`/`examine`/`info_self→check` table as one live smoke check
against the *actual* `mud-manager` tool list/dispatch path (not a fake
double) — in particular confirming `registry.dispatch("tbamud__check",
{"kind": "exits"})` returns a real exits response.

### 6. README

`week3_capable/python/tool_scoping/README.md`: adapt the copied-forward
`12_context/README.md`, trimming its now-irrelevant step-11/12-history
framing and adding a "Scoping which MCP tools get registered" section
documenting: the full on/off table, the default (no `tools:` key = register
everything, unchanged), the `as:` rename mechanism and *why* one exists
today (`info_self` → `check`, with the raw-tbaMUD-command-vs-`mud_manager`-
wrapper gap explained briefly), and how to flip a tool back on.

## Task list

1. `mkdir -p week3_capable/python` and copy
   `week1_baseline/python/12_context/` → `week3_capable/python/tool_scoping/`
   verbatim, excluding `__pycache__`/`boukensha.egg-info` (build artifacts,
   regenerate on install).
2. `cp .boukensha/settings.yaml .boukensha/settings.yaml.bak`.
3. Edit `.boukensha/settings.yaml`'s `mcp_servers.mud` block in place: add
   the full `tools:` table from Design section 1 (`move`/`examine`/
   `info_self as check` on, the other 52 off).
4. Edit `boukensha/config.py`: add `mcp_servers()`'s `tools` key plus the
   `_parse_tools`/`_truthy` helpers, per Design section 2; update the
   docstring/example.
5. Edit `boukensha/tools/mcp.py`: add `tools=None` param to `register()`
   and `register_client()`; implement the filter + `as:` rename + the
   unmatched-entry warning + corrected registered-count return, per
   Design section 3.
6. Edit `boukensha/__init__.py`: pass `tools=entry["tools"]` through in
   `_register_mcp_servers`; fix the `summary[name]` computation to use a
   before/after `registry.tool_names()` diff instead of `len(client.tools)`.
7. Write `tests/test_tools_mcp.py` per Design section 5, using an
   in-process fake MCP client double (no subprocess).
8. Update `examples/mcp_mud_demo.py`'s `--dry` path to demonstrate the real
   table against the fake-MUD harness (optional but recommended — the only
   test exercising this against the *actual* `mud-manager` process).
9. Update `pyproject.toml`'s `description` field
   (`"Boukensha agent — Week 3 Capable: Tool Scoping"`); leave `version.py`
   as `0.12.0` (new track, not a continuation of Week 1's version ladder).
10. Rewrite `README.md` per Design section 6.
11. Install editable into the shared root `.venv`
    (`.venv/bin/pip install -e week3_capable/python/tool_scoping`); run
    `tests/test_tools_mcp.py`.
12. Verify offline first (no live MUD, no API spend): run
    `examples/mcp_mud_demo.py --dry` and confirm exactly 3 tools register
    (`move`, `examine`, `tbamud__check` dispatching through to `info_self`).
13. Per the live/paid-verification policy: only after the above, ask
    before spending real budget on one live turn (`examples/example.py` —
    shared with `week1_baseline/python/12_context` via the now-edited root
    fixture, so this doubles as confirming Week 1's demo still runs cleanly
    with the trimmed tool set) to visually confirm the `tools:` array in
    the actual request payload contains exactly 3 entries, and that a
    live `tbamud__check(kind="exits")` call round-trips correctly. Read
    the payload off the existing `Logger`'s `prompt` event (already
    receives whatever gets sent) rather than adding new permanent logging.
14. Don't commit until the user reviews.

## Resolved decisions (from plan review)

1. **Config: edit the shared root fixture directly**, after an explicit
   backup copy (`settings.yaml.bak`) — supersedes the earlier
   fork-a-new-`.boukensha`-directory proposal. Accepted tradeoff: Week 1's
   `12_context` demo now also runs with the scoped-down tool set.
2. **No numeric step prefix** for `week3_capable/python/tool_scoping` — this
   is a new track, not a continuation of Week 1's `NN_name` ladder. (Applies
   to the code directory; this plan doc's filename was likewise renamed
   from `01_tool_scoping.md` to `tool_scoping.md` for consistency.)
3. **`register_client`'s return-value contract change is safe** — confirmed
   nothing outside this repo snapshot depends on its current meaning.
4. **`check` doesn't exist as a `mud-manager` tool** — resolved by renaming
   `info_self` to `check` at the boukensha registration layer (`as: check`
   in config), not by adding a new tool to `mud_manager`'s Ruby primitives
   layer. This is why per-tool filtering alone wasn't enough and the config
   schema grew an `as:` rename field (Design sections 1 and 3).
