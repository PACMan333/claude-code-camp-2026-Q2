# MudManager

The MudManager has the following responsibilities:

- manages long-lived telnet sessions
- manages the multi-step process of logging back in
- provides generic primitives for MUD commands

## The MCP interface (use MudManager from any language)

MudManager is written in Ruby, but bootcampers work in Python, Java, Rust,
Go, and more. Rather than reimplement the session/login/telnet logic in
every language (fragile, O(N) maintenance, bugs rediscovered N times), the
library ships a single **MCP server** that any language can drive:

```sh
mud-manager --mcp
```

This starts a long-lived process that holds one `MudManager::Session`
internally and speaks **JSON-RPC 2.0 over stdio** (the standard MCP stdio
transport). Because MCP is a documented, cross-language protocol with
existing client SDKs for most major languages, a client in *any* language
needs no MUD- or Ruby-specific knowledge — it just spawns this process and
talks to it.

See [`docs/plans/mud_manager/generic_interfacing.md`](../../docs/plans/mud_manager/generic_interfacing.md)
for the full comparison of why MCP was chosen over per-language wrappers,
a bare CLI, or a bespoke protocol.

### The contract

| Method | Purpose |
|---|---|
| `initialize` / `notifications/initialized` | Handshake; the server reports its `serverInfo` (name `mud-manager`, version). |
| `tools/list` | Self-describing capability discovery. Every command is advertised with a name, description, and JSON Schema for its arguments (including `enum` constraints, e.g. `move`'s `direction`). No per-language docs needed. |
| `tools/call` | Dispatch a command. Returns `{ "content": [{ "type": "text", "text": ... }], "isError": <bool> }` — cleanly separating "executed, here's the output" from "executed, but failed for a game-logic reason" (e.g. an invalid direction). |

The advertised tools are the full `MudManager::Primitives` surface (55
commands: movement, combat, communication, inventory, doors, perception,
magic, shop/bank/mail, character/lifecycle).

### Connection details travel by environment

The MUD connection is opened **lazily**, on the first `tools/call` — so
`tools/list` (pure discovery) works with no credentials and no side
effect. When the first command arrives, the session connects and logs in
using:

| Variable | Default | |
|---|---|---|
| `MUD_HOST` | `localhost` | |
| `MUD_PORT` | `4000` | |
| `MUD_NAME` | — | required to log in |
| `MUD_PASSWORD` | — | required to log in |

A spawning MCP host passes these as the server entry's `env`, per the
stdio transport convention.

### Minimal client sketch (any language)

```
1. spawn:      mud-manager --mcp   (with MUD_* in the child's environment,
                                    MERGED onto the parent env — do not
                                    replace it, or you lose PATH)
2. handshake:  -> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}
               <- {... "result":{"serverInfo":{"name":"mud-manager",...}}}
               -> {"jsonrpc":"2.0","method":"notifications/initialized"}
3. discover:   -> {"jsonrpc":"2.0","id":2,"method":"tools/list"}
               <- {... "result":{"tools":[{"name":"look","inputSchema":{...}}, ...]}}
4. act:        -> {"jsonrpc":"2.0","id":3,"method":"tools/call",
                   "params":{"name":"look","arguments":{}}}
               <- {... "result":{"content":[{"type":"text","text":"..."}],"isError":false}}
```

A complete, working reference client (Python, stdlib only, zero
MUD-specific code) lives in
`week1_baseline/python/10_standard_tool_library/boukensha/mcp/client.py`
and `.../boukensha/tools/mcp.py`. The Ruby host is
`week1_baseline/ruby/10_standard_tool_library/lib/boukensha/{mcp,tools}`.

### Try it offline (no live MUD, no credentials)

`MudManager::FakeMud` (shipped in this gem) is a minimal in-process fake
CircleMUD server — the MCP tests and the Boukensha `--dry` demos spawn the
real daemon against it, so you can exercise the full handshake → discovery
→ dispatch path without touching a real MUD.

```sh
ruby week1_baseline/ruby/10_standard_tool_library/examples/mcp_mud_demo.rb --dry
```

## Build the Gem

From this directory:

```sh
gem build mud_manager.gemspec
gem install ./mud_manager-0.1.0.gem
```

Installing the gem puts the `mud-manager` executable on your `PATH`, so
`mud-manager --mcp` (see below) works from anywhere. Run `mud-manager --help`
for usage.

## Uninstall

```sh
gem uninstall mud_manager
```

## Examples

Test the live session:

```sh
MUD_NAME=YourCharacterName MUD_PASSWORD=yourpassword ruby mud_manager/examples/live_session_test.rb
```

If you are already inside the `mud_manager` directory, run:

```sh
MUD_NAME=YourCharacterName MUD_PASSWORD=yourpassword ruby examples/live_session_test.rb
```
