# Delta Plan — Carrying Forward Session Improvements into Step 12 (Context)

## Context

Across this session's work on `week0_explore/mud_manager` and
`week1_baseline/ruby/10_standard_tool_library`/`11_tui`, several fixes and
improvements were made that live outside step 12's own lesson content:

1. `week0_explore/mud_manager/` (the shared, external `mud_manager` gem
   source) — `lib/mud_manager/session.rb` (login-drain race fix, and the
   "already in use" reconnect-message fix), `bin/mud-manager` (the `look`
   `target: "room"` fix, `--help`/`--mcp` CLI hardening, load-path
   robustness), `mud_manager.gemspec` (packaged the daemon as a real gem
   executable), `README.md` (documented the MCP interface).
2. `week1_baseline/ruby/10_standard_tool_library/test/test_mcp_servers_config.rb`
   and `week1_baseline/ruby/11_tui/test/test_mcp_servers_config.rb` — both
   fixed the stale `test_returns_a_tool_count_per_server` assertion from
   `26` (a curated reference-daemon count that no longer exists) to `55`
   (the real, shipped daemon's full `MudManager::Primitives` surface).
3. Step 11's own gems (`charm`/`bubbletea`/etc.) were installed and a
   vendored patch (`patches/bubbletea/patch_bubbletea.rb`) applied to fix
   a real multi-byte-input-truncation bug in `bubbletea`'s native
   extension.

The user asked to identify what still needs to carry forward into
`week1_baseline/ruby/12_context`, the next step's already-authored lesson
content (not something built this session — `12_context` ships with real,
extensive content of its own: context-window tracking, compaction,
reasoning/plan log events, and an MCP client hardening fix, all new to
this step).

## Investigation

A full `diff -rq` between `week1_baseline/ruby/11_tui` and
`week1_baseline/ruby/12_context`, followed by direct diffs of every
flagged file, plus an actual `bundle install` + full test run.

### Already present in step 12, byte-identical to step 11 — nothing to carry over

- `lib/boukensha_loader.rb`, `bin/boukensha` — the full env var →
  `~/.boukensharc` → bundled-default resolution, YAML mapping support,
  and `--no-tui` CLI flag are all already there, unchanged.
- `Gemfile`, `boukensha.gemspec` — unchanged (the new `gum` gem below
  arrives as a transitive dependency, not a new `Gemfile` line).
- `patches/bubbletea/*` — the vendored patch directory is byte-identical
  to step 11's. `bundle install` in step 12 pulls a precompiled
  `bubbletea` native gem at the same version step 11 already validated;
  nothing new to patch there.
- `lib/boukensha/tool.rb`, `registry.rb`, `run_dsl.rb`, `message.rb`,
  `tasks/*` — unchanged from step 11.

### Not automatically shared, but already fine — `week0_explore/mud_manager` is referenced by path

Every fix made to `week0_explore/mud_manager/` this session (the
`Session` login-drain race, the "already in use" reconnect fix, the
`look`/`target: "room"` daemon fix, CLI hardening, gemspec packaging)
already applies to step 12 automatically — `test/helper.rb` and
`examples/*.rb` locate the daemon via the same relative path up to
`week0_explore/mud_manager` as every earlier step. Nothing to carry over
here.

### The one real, concrete regression — actually stale in step 12

`week1_baseline/ruby/12_context/test/test_mcp_servers_config.rb`'s
`test_returns_a_tool_count_per_server` still asserts
`{ "mud" => 26 }`, the pre-fix expectation — reverted back to the stale
value even though both step 10 and step 11 already carry the `55` fix.
Confirmed by actually running the suite (`rake test` from
`week1_baseline/ruby/12_context`, after a clean `bundle install`):

```
22 runs, 65 assertions, 1 failures, 0 errors, 0 skips
  1) Failure:
TestMcpServersConfig#test_returns_a_tool_count_per_server [.../test_mcp_servers_config.rb:125]:
Expected: {"mud"=>26}
  Actual: {"mud"=>55}
```

This is the **only** failure in the entire suite — every other test
passes cleanly against step 12's real content as-is.

### A new dependency, checked, not a blocker

`bundle check` initially reports `gum (0.3.2)` missing — a new
transitive dependency (arrives via `Gemfile.lock`, no new line in
`Gemfile` itself; likely a newer `charm`/`bubbletea` sub-dependency).
Unlike step 11's 14-missing-gem, fully-blocked state, `bundle install`
here resolves and installs a single precompiled `x86_64-linux` native
gem cleanly — no Go toolchain, no source patch needed for it (confirmed:
`require "boukensha"` succeeds and the full test suite runs afterward).

That said, this is the same class of thing `bubbletea` was — a native
extension nobody has exercised interactively yet. The test suite doesn't
touch the TUI's rendering path (Ruby has no headless TUI harness the way
Textual's `run_test()` gave the Python port), so "installs cleanly and
the suite passes" is not the same guarantee as "the TUI actually renders
correctly with real keyboard/paste input." Flagging this rather than
declaring it clean, per the same discovered-bug caution `bubbletea`
warranted.

### Confirmed *not* regressions — legitimate new step-12 design, left alone

Several large diffs looked concerning at first glance but are step 12's
actual, deliberate lesson content, consistently applied everywhere they
touch (not a half-finished carry-over):

- `Context#initialize` drops `task:` entirely (replaced by
  `context_window:`/`compaction_threshold:` and new `usage_fraction`/
  `needs_compaction?`/`compact_messages!` methods). Every call site
  (`boukensha.rb`, `test/helper.rb`, `examples/mcp_mud_demo.rb`) is
  updated together — not a stale caller left behind.
- `Repl`/`Agent` drop `task_settings:` in favor of `Config#agent_max_iterations`/
  `agent_max_turn_tokens`/`agent_max_output_tokens`/`agent_compaction_threshold`,
  each with a safe numeric default when `settings.yaml` has no `agent:`
  block (confirmed: the repo's real `.boukensha/settings.yaml` has no
  `agent:` block today, and nothing crashes — it just falls back to the
  documented defaults).
- `models.rb` (new) — a static model → `context_window` table built from
  each backend's own `MODELS` constant, used to auto-size a model's
  context window without the user configuring it in `settings.yaml`.
- `Logger#compaction`/`#reasoning`/`#plan`, `Agent#record_usage`/
  `#compact_if_needed`/`#log_reasoning` — new logging/compaction plumbing
  behind the context-window feature.
- `Mcp::Client#spawn_unbundled` / `#stderr_detail` (in
  `lib/boukensha/mcp/client.rb`) — a real, new hardening fix: spawns MCP
  servers via `Bundler.with_unbundled_env` so a server with its own,
  different Gemfile doesn't inherit boukensha's `BUNDLE_GEMFILE`/`RUBYOPT`
  and fail to activate; also drains the child's stderr on an unexpected
  EOF so a crash during spawn/handshake is diagnosable instead of a bare
  "server closed the connection". This is new-to-step-12 content, not
  something missing from an earlier step that needs backporting.
- `Tui`'s progress/status lines now read `@context.usage_pct`/
  `current_tokens`/`context_window` (with yellow/red color thresholds)
  instead of step 11's simple running session-token counters, and handle
  a new `"compaction"` event phase. Consistent with the `Context` API
  change above.

None of this needs "fixing" — it's exactly the new material step 12 is
supposed to teach. Called out here only so the task list below doesn't
get confused with it.

## Task list

1. Apply the identical one-line fix already made in steps 10 and 11 to
   `week1_baseline/ruby/12_context/test/test_mcp_servers_config.rb`:
   change the `test_returns_a_tool_count_per_server` assertion from
   `{ "mud" => 26 }` to `{ "mud" => 55 }`, carrying forward the same
   explanatory comment.
2. Re-run `rake test` from `week1_baseline/ruby/12_context` and confirm
   all 22 tests pass (currently 21/22, only the item-1 failure).
3. **Don't** touch `Context`, `Repl`, `Agent`, `models.rb`, `Logger`,
   `Mcp::Client`, or `Tui` — every diff there is step 12's own intended
   new content, already internally consistent, not a stale carry-over.
4. Flag (don't pre-emptively patch) the new `gum` native gem: it installs
   cleanly and passes the full non-TUI test suite, but — like
   `bubbletea` before it was found to need a patch — hasn't been
   exercised through real interactive keyboard/paste input yet. The
   right verification is a live `boukensha` TUI session in step 12 (real
   terminal required; not something this delta can do headlessly the way
   the Python port's Textual `run_test()` pilot could). Only patch it if
   an actual bug surfaces during that live check.

## Open questions

None blocking — item 1 is a single, unambiguous one-line change with a
known-correct target value (55, matching steps 10/11's already-approved
resolution). Item 4 is flagged for a live check, not resolved here, since
there's no confirmed bug to fix yet (unlike `bubbletea`, where the
truncation bug was reproduced before patching).
