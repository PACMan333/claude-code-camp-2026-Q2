---
name: port-ruby-to-python
description: Ports one step of this repo's `week1_baseline/ruby/<NN_name>` Boukensha tutorial code to its `week1_baseline/python/<NN_name>` counterpart. Covers both halves of the workflow — writing the port plan doc under `docs/plans/python_port/<NN_name>.md`, and then building the actual Python package once the plan is settled. Use this whenever the user asks to port a Ruby step to Python, write or execute a "python port plan", work on `week1_baseline/python/*`, or mentions Boukensha/the `.boukensha` config fixture in the context of Ruby-to-Python porting. Also trigger on requests like "plan step 05", "do the next port", or "port 04_api_client" even without the word "plan" or "python" explicitly, and when the user references an existing file under `docs/plans/python_port/`.
---

# Port Ruby to Python (Boukensha tutorial)

This repo carries a step-by-step Ruby tutorial (`week1_baseline/ruby/<NN_name>/`)
forward into a parallel Python port (`week1_baseline/python/<NN_name>/`). Each
step is a **self-contained copy** of the whole `boukensha` package at that
point in its history — mirroring how the Ruby source duplicates itself into
every step folder — not a diff applied on top of the previous step. This
convention was settled early in the port (see
`references/conventions.md`) and every step since has followed it; don't
relitigate it per-step.

The workflow has two phases, and the same Ruby step folder is the input to
both:

1. **Plan** — read the Ruby source, understand what changed since the last
   ported step, and write a plan doc.
2. **Execute** — once the plan is settled (any open questions answered),
   build the actual Python package from it.

## Step 0: figure out which step, and which phase

If the user names a step (a number like `04`, a folder name like
`04_api_client`, or just "the next step"), resolve it against
`week1_baseline/ruby/`. If they didn't name one, find it yourself: compare
`week1_baseline/ruby/*` against `week1_baseline/python/*` and
`docs/plans/python_port/*` to find the earliest Ruby step folder that has
real source (non-empty — check with `find <dir> -type f | wc -l`, several
Ruby step folders exist as empty placeholders ahead of where the tutorial
actually is) but no finished Python port yet. Confirm the step with the
user before writing anything if it was ambiguous which one they meant —
don't guess silently and start writing files for the wrong step.

If the named Ruby step folder is empty or doesn't exist, stop and say so —
there's nothing to port yet. Don't invent source to fill the gap.

Then check `docs/plans/python_port/<NN_name>.md`:

- **Missing or empty** → do the **Plan** phase (Step 1 below).
- **Has real content** → do the **Execute** phase (Step 2 below). Read the
  whole plan file first; it already contains the settled answers to any
  design forks (look for "Open questions" with answers filled in beneath
  each one, or a "Resolved during planning" list) — don't re-ask what it
  already answered.

If the user explicitly asks for one phase only ("just write the plan, don't
build it yet"), do only that phase even if the other's precondition is met.

## Step 1: Plan phase

The goal is a plan doc at `docs/plans/python_port/<NN_name>.md` that's
detailed enough that the Execute phase can follow it mechanically, with no
new judgment calls left over. Read `references/conventions.md` first — it
catalogs every settled decision from prior steps (venv/packaging setup,
Ruby-idiom → Python-idiom mappings, how to handle discovered Ruby bugs,
etc.) so you're not rediscovering them from scratch each time.

1. **Read the full Ruby source** for the target step: `Gemfile`, everything
   under `lib/`, `examples/`, `prompts/` (if present), and `README.md`.
2. **Diff against the previous Ruby step** (the last one that has a
   finished Python port) file-by-file. Most files are byte-identical
   copy-forwards; the plan only needs new prose for what actually changed
   or is new this step. Calling a file "byte-identical to step NN-1" is a
   valid, useful, and *checked* (via `diff`, not assumption) statement to
   put in the plan.
3. **Read the previous Python step's actual code**, not just its plan —
   the plan describes intent, the code is what's really there to copy
   forward (`week1_baseline/python/<previous>/boukensha/...`). Also skim
   its `README.md` "Considerations" section for simplifications or
   caveats that should carry forward into this step's README too.
4. **Run the Ruby example** (`bundle exec ruby examples/example.rb` from
   the step's directory, or via `week1_baseline/bin/ruby/<NN_name>` if that
   runner exists) against the repo's real `.boukensha/` fixture and look at
   its actual output. Ruby step READMEs have historically shipped stale
   "Expected Output" blocks that don't match the real code (discovered in
   step 02) — the plan must describe the real, verified behavior, never
   propagate a stale README example forward.
5. **Find the genuine design forks** — the places where "translate Ruby to
   Python" doesn't have one obvious answer. Concretely, look for: Ruby
   idioms with no direct Python equivalent (trailing blocks, symbol/string
   dual keys, bang/query method names), naming collisions that Ruby's
   separate class-method/instance-method tables allow but Python's single
   class namespace doesn't, and — importantly — **latent bugs or
   inconsistencies already present in the Ruby source** (e.g. a method
   whose call site doesn't match its declared arity, but only for code
   paths the shipped example/fixture doesn't happen to exercise). These
   are worth hunting for deliberately: read every method's call sites, not
   just its definition, and check whether all sibling implementations of
   an interface actually share the same shape.

   For each fork with real consequences, **ask the user directly** with
   `AskUserQuestion` rather than picking silently — give a recommended
   default and a concrete code preview of each option so the choice is
   easy to evaluate at a glance (see this step's own git history —
   `docs/plans/python_port/03_prompt_builder.md` — for two worked
   examples: a class/instance method naming collision, and a decision to
   preserve vs. fix a latent Ruby bug). Write the resolution directly into
   the plan's "Open questions" section once answered — a plan with
   unresolved questions isn't ready for the Execute phase.
6. **Write the plan doc**, following the structure every prior plan in
   `docs/plans/python_port/` uses (read 2-3 of them for the exact shape —
   `00_config.md` through `03_prompt_builder.md` are good references):
   - `## Scope` — one paragraph: what's being ported, and the
     copy-forward-not-diff framing.
   - `## Source files being ported (reference)` — a table: Ruby source →
     purpose (noting unchanged/changed/new) → Python target.
   - `## Target layout` — the resulting directory tree.
   - `## Ruby → Python design mapping` — the substantive section. One
     bullet per notable translation decision, each with the *why*, not
     just the *what*.
   - `## Config directory & schema` — usually "unchanged from step N-1",
     called out explicitly if anything about `.boukensha/` resolution
     changes.
   - `## Task list` — a numbered, mechanically-followable build sequence.
   - `## Open questions` — forks you flagged, with the user's answer
     written directly beneath each one.

## Step 2: Execute phase

Follow the plan's task list. A few things that matter regardless of what
the specific plan says:

1. **Copy forward files the plan marks unchanged** from the previous
   Python step's actual code — don't retype them from the Ruby source or
   "improve" them along the way. If a copy-forward file needs one small
   change (e.g. re-adding a constant), start from the previous step's
   Python file and edit it, don't write it fresh.
2. **Build the new/changed files** per the plan's design mapping section.
3. **Reuse the packaging pattern** from the previous Python step
   (`requirements.txt`, `pyproject.toml`) per `references/conventions.md`,
   bumping only the description field.
4. **Install this step editable into the shared root `.venv`**
   (`.venv/bin/pip install -e week1_baseline/python/<NN_name>`) — this
   repoints `import boukensha` at the new step, away from whichever step
   was installed before.
5. **Check the runner script is executable.** `week1_baseline/bin/python/<NN_name>`
   is usually already scaffolded in the repo ahead of time, but has
   sometimes been left without the executable bit (`chmod +x` it if
   `./week1_baseline/bin/python/<NN_name>` fails with "Permission denied").
6. **If this step's code has any real-world cost or side effect — a paid
   API call, an external service, anything non-idempotent or hard to
   undo — verify it against a local mock first, before spending that
   budget.** Step 04 introduced this: `Client` POSTs to a real, billed LLM
   API with no dry-run mode, so before the one live call the user approved,
   it's worth standing up a throwaway local HTTP server (Python's
   `http.server.HTTPServer` in a background thread is enough) that returns
   canned success/error responses, and running the new code against
   *that* first. This is how retry/backoff timing, the exhausted-retries
   path, and the non-retryable-status-code path all got confirmed without
   touching the real API — those branches are exactly the ones a single
   live run won't exercise (a real API rarely fails on demand), and they're
   also the ones most likely to have an off-by-one or wrong-exception-type
   bug. Only spend the real/live budget once the mock run gives confidence
   the logic itself is right.
7. **Run both runners and diff.** Run
   `week1_baseline/bin/python/<NN_name>` and
   `week1_baseline/bin/ruby/<NN_name>` against the same `.boukensha/`
   fixture and diff the output. Expect only the cosmetic-diff classes
   already accepted since step 00 (see `references/conventions.md`) — a
   diff outside that class means something is actually wrong, not a
   Ruby/Python quirk to wave away. If the step has a real-world cost per
   run (per point 6 above), treat this comparison run itself as part of
   that spending budget — don't re-run it repeatedly the way steps 00–03's
   free, local-only runs could be.
8. **Exercise code paths the shared fixture doesn't reach**, if the step
   added anything conditional on config the fixture doesn't set (e.g.
   step 03 added five LLM backends but the fixture only selects one of
   them) — construct the untested branches directly
   (`.venv/bin/python -c "..."`) to confirm they work before calling the
   step done.
9. **Port the README**, adapting the Ruby step's structure/tables to
   Python, and add a "Considerations" section documenting any deliberate
   simplification or preserved-quirk decision from the plan's open
   questions — these are teaching points, and future steps (and future
   invocations of this skill) will look at this section the same way you
   looked at prior steps' README Considerations in Step 1.3 above.
10. **Don't commit.** Leave the new/changed files in the working tree for
    the user to review, unless they've explicitly asked for a commit.

See `references/conventions.md` for the accumulated settled decisions
(packaging, venv, and the specific Ruby → Python idiom translations) so
you're applying them, not re-deriving them.
