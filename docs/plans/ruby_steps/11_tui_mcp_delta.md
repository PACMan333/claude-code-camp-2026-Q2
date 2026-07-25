# Delta Plan — Carrying Step 10's MCP/Loader Changes into Step 11 (TUI)

## Context

This session made real fixes while executing the MCP option from
`docs/plans/mud_manager/generic_interfacing.md`, touching three places:

1. `week0_explore/mud_manager/` (the shared, external `mud_manager` gem
   source) — `lib/mud_manager/session.rb` (login-drain race fix),
   `bin/mud-manager` (the `look` `target: "room"` fix, `--help`/`--mcp`
   CLI hardening, load-path robustness), `mud_manager.gemspec` (packaged
   the daemon as a real gem executable), `README.md` (documented the MCP
   interface).
2. `week1_baseline/ruby/10_standard_tool_library/test/test_mcp_servers_config.rb`
   — fixed the stale `test_returns_a_tool_count_per_server` assertion
   from `26` (a curated reference-daemon count that no longer exists) to
   `55` (the real, shipped daemon's full `MudManager::Primitives`
   surface).
3. `~/.boukensharc` (the user's own home-directory config, not part of
   this repo) — pointed the global `boukensha` command at step 10 instead
   of the stale installed step-9 gem.

The user asked to carry these deltas into `week1_baseline/ruby/11_tui`,
which they believed was missing the MCP implementation and the improved
`boukensha_loader.rb`.

## Investigation: what's actually missing

A full `diff -rq` between `week1_baseline/ruby/10_standard_tool_library`
and `week1_baseline/ruby/11_tui`, followed by direct diffs of every file
it flagged, shows the premise is only partly true:

**Already present in step 11, byte-identical to step 10 — nothing to
carry over:**
- `lib/boukensha/mcp/client.rb`, `lib/boukensha/tools/mcp.rb` — the full
  MCP client/host implementation.
- `lib/boukensha/config.rb` — `mcp_servers()` parsing.
- `lib/boukensha.rb` — `register_mcp_servers`, the `require_relative "boukensha/tools/mcp"`
  wiring, and the `mcp_servers:`-driven tool registration in both `run`
  and `repl`. Step 11 only *adds* TUI-specific bits on top (a `tui:`
  keyword on `repl`, wrapping the `Repl` in `Tui.new(...)` when enabled)
  — it doesn't lack anything step 10 has.
- `lib/boukensha_loader.rb` — already has the step-10 loader form (env
  var → `~/.boukensharc` → bundled default, for both the implementation
  path and the config dir) and layers its own `--no-tui` CLI flag on top.
- `context.rb`, `registry.rb`, `run_dsl.rb`, `agent.rb`, `client.rb`,
  `tasks/*`, `backends/*` — all unchanged from step 10.

**Not automatically shared — this repo's `week0_explore/mud_manager` is
referenced by path, not vendored per step:**
- Every fix made to `week0_explore/mud_manager/` (the `Session` login-drain
  race, the `look`/`target: "room"` daemon fix, `--help`/`--mcp` CLI
  hardening, the gemspec packaging) already applies to **both** step 10
  and step 11 automatically, because both steps' `test/helper.rb` and
  `examples/*.rb` locate the daemon via the same relative path up to
  `week0_explore/mud_manager` — there is nothing to carry over here; it
  was never step-10-only.

**The one real, concrete delta — actually stale in step 11:**
- `week1_baseline/ruby/11_tui/test/test_mcp_servers_config.rb`'s
  `test_returns_a_tool_count_per_server` still asserts
  `{ "mud" => 26 }`, the pre-fix expectation. Step 10's copy was updated
  to `{ "mud" => 55 }` (with a comment explaining why) in this session;
  step 11's copy needs the identical fix.

## A separate, unrelated blocker found along the way

Running step 11's test suite in its own bundled environment
(`bundle check` from `week1_baseline/ruby/11_tui`) shows **14 missing
gems** — `charm`, `bubbletea` (native extension, both platform variants),
`lipgloss`, `bubbles`, `bubblezone`, `glamour`, `gum`, `harmonica`,
`ntcharts` — none of which have ever been installed in this environment.
Step 11's `boukensha.rb` unconditionally `require_relative "boukensha/tui"`,
which unconditionally `require`s `bubbletea`/`lipgloss`/`bubbles`, so
**nothing in step 11 can currently boot at all** — not the test suite,
not `examples/example.rb`, not the REPL — regardless of the MCP delta.

This is a real, separate problem, not part of "carrying the step-10
delta forward": step 10 never had a TUI or a `charm` dependency, so
there's nothing to diff or port here — step 11 simply needs its own
dependencies installed for the first time. `patches/bubbletea/*` (a
vendored `.c`/`.patch` pair, per that directory's own `README.md`)
suggests `bubbletea`'s native extension needs a source patch applied
before or during its build, which means `bundle install` alone likely
isn't sufficient without also following whatever process
`patches/bubbletea/README.md` documents. This plan flags it rather than
attempting it unprompted, since installing/patching native gem
extensions is a materially different (and materially riskier) task than
a one-line test fix, and isn't what was asked for here.

## Task list

1. Apply the identical one-line fix already made in step 10 to
   `week1_baseline/ruby/11_tui/test/test_mcp_servers_config.rb`: change
   the `test_returns_a_tool_count_per_server` assertion from
   `{ "mud" => 26 }` to `{ "mud" => 55 }`, carrying forward the same
   explanatory comment.
2. Confirm no other test file in step 11 has drifted from its step-10
   counterpart in a way `diff -rq` didn't already surface (the initial
   `diff -rq` pass covers this, but re-run it after step 1 to confirm
   `test_mcp_servers_config.rb` is now the only test difference, and that
   the difference is exactly the TUI-unrelated fix just applied).
3. **Do not** attempt to install `charm`/`bubbletea`/etc. or apply the
   `patches/bubbletea` patch as part of this delta — flag it to the user
   as a separate, pre-existing environment gap unrelated to the MCP/loader
   carry-forward, and let them decide whether/when to tackle it.
4. Once the gems are available (whenever that happens, in or out of this
   session), re-run step 11's full test suite via `bundle exec rake test`
   (or the equivalent `bundle exec` invocation this repo's other steps
   use) to get a real pass/fail signal — the plain `ruby -Ilib -Itest`
   invocation used during investigation bypasses Bundler and isn't a
   valid check for a step with real external gem dependencies.

## Open questions

None blocking — the actual delta (item 1) is a single, unambiguous
one-line change with a known-correct target value (55, matching step
10's already-user-approved resolution). The native-gem installation
question (item 3) is flagged for the user's own judgment, not resolved
here, since it's out of scope for "carry the step-10 delta forward."
