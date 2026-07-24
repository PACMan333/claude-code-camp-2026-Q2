Our MUDManager is written in Ruby.
In our Bootcamp, bootcampers want to use their own language eg. Java, Python, Rust, Go, etc.

What is he solution?
- We have to create wrapper per lang
- We make MUDManager a command line tool, and other languages execute shell commands in their language.
- We implement a communication protocol
- We implement MCP as a layer.

Consider that the MUDManager is mnaging the sessions for the MUD.

## Technical Exploration

This isn't a purely theoretical comparison — a working implementation of
option 4 (MCP) already exists in this repo and has been exercised end to
end against a real MUD server, and option 2 was effectively prototyped
along the way too (it's the shape option 4's daemon degrades to if you
strip the protocol framing back out). The evidence below is drawn from
that build, not just first-principles reasoning.

### The constraint that decides this: MudManager manages *sessions*, not one-shot commands

`MudManager::Session` is a long-lived telnet connection with a background
reader thread continuously draining the socket, stripping telnet IAC
negotiation, and buffering whatever arrives — including chatter from
other players that shows up *between* the commands your code explicitly
sends. Logging in is itself a multi-step dance (name prompt → password
prompt → welcome/menu → "enter the game"), and reconnecting is neither
free nor instant. Any solution that doesn't keep that connection alive
across multiple commands either has to pay the reconnect+login cost on
every single action, or silently drop async messages that arrive while
nothing is "listening." This one property does most of the work of
ranking the four options below — it's why option 2, taken literally,
doesn't actually work, and why option 4 needs the daemon to hold the
`Session` internally rather than treating each MCP call as independent.

### Option 1 — A wrapper per language

Reimplement (or FFI-bind) `MudManager::Session`/`Primitives` natively in
each target language: a Java wrapper, a Python wrapper, a Rust wrapper, a
Go wrapper, and so on for every language a bootcamper wants to use.

**Problems, concretely:**
- **O(N) maintenance for N languages**, and it's not thin-wrapper work —
  each reimplementation has to independently get right the telnet
  IAC-stripping, the background-buffering-thread design, the CircleMUD
  login dance, and all ~55 command primitives (movement, combat,
  communication, inventory, doors, perception, magic, shop/bank/mail).
  That's a lot of genuinely fiddly protocol logic to duplicate, not
  boilerplate.
- **Bugs get rediscovered N times instead of fixed once.** While building
  the MCP daemon for this repo, two real bugs surfaced in
  `MudManager::Session` itself: a login-drain race (the post-login banner
  arrives in more than one TCP burst, and a single quiet-window read
  returned before the second burst landed, so the very first command
  after login came back empty) and a client-side tool-call issue where an
  agent's `look at room` was rejected by the MUD because there's no
  object literally named "room". Both were fixed once, centrally, in the
  shared Ruby library and/or the shared daemon — under a per-language
  wrapper strategy, each of N reimplementations would have had to hit
  that same race independently before anyone could fix it, in N
  codebases, possibly N different ways.
- FFI approaches (JRuby for Java, embedding a Ruby interpreter, etc.)
  trade the reimplementation problem for a deployment/tooling problem
  instead — now every bootcamper's toolchain needs a working
  cross-language bridge, which is its own maintenance surface.

This is the worst option for a many-language bootcamp specifically
*because* it's many languages — the cost scales with exactly the
variable the bootcamp wants to maximize.

### Option 2 — MudManager as a CLI, other languages shell out

Ship `mud-manager` as a command-line tool; a bootcamper's Python/Java/Rust
code invokes it as a subprocess per action (`mud-manager look`,
`mud-manager move north`, …) and reads the output.

**This doesn't survive contact with the session-state constraint above.**
A literal one-shot-CLI-per-command design means reconnecting and logging
in again for *every single action* — paying the multi-burst login
handshake cost repeatedly, and losing the background thread's job of
catching async messages between commands entirely (there's no "between
commands" if the process exits after each one). To make this workable at
all, the CLI would need to talk to an already-running, persistent
daemon process instead of embodying the session itself — at which point
you've reinvented a client/daemon split anyway, just without the rest of
what option 4 gets for free (see below): no self-describing capability
discovery, no standard argument-typing convention, no standard
error-vs-success result shape. Each language would still need to invent
its own answer to "how do I talk to the already-running daemon," which
re-imports a chunk of option 1's per-language duplication problem, just
scoped to transport plumbing instead of MUD-protocol logic.

A one-shot CLI mode isn't worthless, though — it's exactly the right
shape for scripting and smoke-testing *outside* the agent path (this repo
already has this, informally: `examples/mcp_mud_demo.rb --dry` spawns the
daemon and dispatches a couple of calls directly for a quick sanity
check). It's a poor fit as the *primary* interface a bootcamper's agent
code drives many typed calls through, which is the actual use case here.

### Option 3 — Roll a custom communication protocol

Define a bespoke wire protocol (newline-delimited JSON over a Unix
socket, some length-prefixed binary framing, whatever) that a persistent
`mud-manager` daemon speaks, and have every language write a thin client
for *that* protocol.

This fixes option 2's session-persistence problem (the daemon holds the
`Session`, same as option 4) but means owning, from scratch, every design
question a wire protocol needs answered:
- Message framing and versioning.
- How a client discovers what commands exist and what arguments they
  take, without the daemon author hand-writing per-language
  documentation that inevitably drifts from the real command set.
- How argument *types* and constraints (e.g. "direction must be one of
  north/east/south/west/up/down") get communicated, so a client can
  validate before ever sending a request.
- A standard shape for "the call was received and executed, but failed
  for a game-logic reason" (invalid argument, dead target) versus "the
  transport itself broke."

Every one of these is something a bespoke protocol has to invent and
document, and the result only works for this one project — no bootcamper
arrives already knowing it, and there's no existing client-library
ecosystem to lean on. This is real, avoidable design and implementation
cost relative to option 4, which has already made every one of these
decisions and published them as a spec.

### Option 4 — MCP as a layer (implemented and verified in this repo)

A long-running `mud-manager --mcp` daemon holds one `MudManager::Session`
internally — opened **lazily**, on the first tool call rather than at
handshake time, so pure capability discovery (`tools/list`) never
requires MUD credentials or has a side effect — and speaks JSON-RPC 2.0
over stdio:

- `initialize` / `notifications/initialized` — handshake, reports
  `serverInfo` (name/version).
- `tools/list` — self-describing capability discovery. Every command the
  daemon supports is advertised with a name, a description, and a JSON
  Schema for its arguments (including `enum` constraints, e.g. `move`'s
  `direction` parameter) — a client in *any* language can introspect the
  full command surface and its typing without the daemon author writing
  per-language docs.
- `tools/call` — dispatch, returning a standard
  `{content: [{type: "text", text: ...}], isError: bool}` shape that
  cleanly separates "executed, here's the result" from "executed, but
  this was a game-logic failure" (e.g. an invalid direction), without
  conflating either with a transport-level exception.

**This was built and proven cross-language in this repo, not just
sketched:**
- The Ruby daemon: `week0_explore/mud_manager/bin/mud-manager` (~55
  tools, one per `MudManager::Primitives` command), backed by
  `week0_explore/mud_manager/lib/mud_manager/fake_mud.rb` for offline
  testing.
- A from-scratch Python MCP client + host, with **zero MUD-specific
  Python code anywhere**: `boukensha.mcp.Client` (~120 lines, stdlib
  `subprocess` + `json` only) and `boukensha.tools.mcp.register`
  (~90 lines) in `week1_baseline/python/10_standard_tool_library/boukensha/`.
  Verified end to end: handshake, tool discovery, dispatch, error-as-data,
  prefix-scoped naming, name-collision detection, and — the real proof —
  a live run where a Python-orchestrated agent reached the actual MUD on
  port 4000 through the identical Ruby daemon the Ruby-side agent uses.
- Because the daemon is a separate OS process speaking a documented wire
  protocol, a Java/Rust/Go bootcamper needs only a small MCP client in
  their own language — and in practice wouldn't even need to write one:
  MCP is a real, existing, increasingly standard protocol with published
  client SDKs for most major languages already, so "adopt an existing MCP
  client library" is a legitimate option 4 sub-choice, not just "write
  another 120-line client."

**Concrete implementation gotchas worth carrying forward** (each is a
real bug or near-bug hit while building this, not a hypothetical):
1. **Environment inheritance must be a merge, not a replace.** Ruby's
   `Open3.popen3(env, *cmd)` merges `env` into the current process's
   environment; a naive Python `subprocess.Popen(env=server_env)`
   *replaces* it wholesale, silently wiping `PATH` and breaking the spawn
   entirely. Every client-side implementation needs to build
   `{**os.environ, **server_env}` (or the equivalent) explicitly.
2. **Open the session lazily, not at handshake time.** Keeps
   `tools/list` (pure discovery) free of side effects and credential
   requirements — you can introspect what a daemon can do without
   connecting it to anything yet.
3. **A single quiet-window read is not enough to consider a login
   "settled."** The MUD sends the entering-game banner and the starting
   room's description as separate bursts; the daemon's login step needs
   to drain in a bounded loop until a pass comes back genuinely empty, or
   the first real command after login silently gets a stale/truncated
   buffer instead of its own response. This is exactly the class of bug
   option 1 would have risked reintroducing independently in every
   per-language reimplementation; here it was fixed once, in the shared
   library everything else depends on.
4. **Tool granularity is a real design axis MCP itself doesn't decide.**
   This daemon exposes all ~55 command primitives as individual tools,
   one per `MudManager::Primitives` method. A separate legacy reference
   somewhere apparently exposed a smaller, curated ~26 — illustrating
   that "how many tools, how granular, which ones get merged behind a
   shared enum parameter" is a choice the daemon author makes, independent
   of transport. Worth deciding deliberately and documenting, not
   defaulting to either extreme by accident.

### Recommendation

**Option 4 (MCP).** It's the only option that solves the actual
constraint — a stateful, persistent session shared across many typed
calls — without either duplicating the Ruby session/protocol logic
per language (option 1) or inventing and documenting a bespoke wire
protocol from scratch (option 3). Option 2 (bare CLI) is worth keeping
*in addition*, but only as a one-shot scripting/smoke-test convenience
built on top of the same daemon (`--dry`/direct-dispatch style), not as
the primary interface — it cannot, on its own, keep the session alive
across the many calls an agent actually needs to make.

The reference implementation already in this repo
(`week0_explore/mud_manager/bin/mud-manager` plus the Python host in
`week1_baseline/python/10_standard_tool_library/boukensha/{mcp,tools}`)
is a working template for what a Java/Rust/Go MCP client would need to
match: spawn the daemon with a merged environment, do the `initialize`
handshake, call `tools/list` for self-describing discovery, and dispatch
through `tools/call` — with zero MUD- or Ruby-specific knowledge anywhere
in the client.