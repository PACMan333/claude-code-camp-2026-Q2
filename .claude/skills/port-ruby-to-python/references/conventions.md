# Settled conventions (steps 00–04)

These were decided once, early in the port, and every step since has
followed them without re-litigating. Apply them; don't re-derive them or
ask the user about them again unless a new step's Ruby source genuinely
breaks an assumption behind one.

## Packaging & environment

- **One shared `.venv` at the repo root**, not a per-step venv. Ruby's
  per-step folders are each fully self-contained with their own `Gemfile`;
  Python's aren't — every step installs editable into the same root
  `.venv`, and installing a new step repoints `import boukensha` away from
  whichever step was previously installed. Decided in `00_config.md` Q2:
  future iterations living in future folders make a single shared venv
  simpler than juggling one per step.
- **`requirements.txt` + plain `venv`**, not `pyproject.toml` + `uv`.
  Decided in `00_config.md` Q1, despite `week0_explore/circlemud-world-parser`
  using `uv` — that precedent doesn't bind this port.
- **Editable installs** (`pip install -e week1_baseline/python/<step>`),
  not `sys.path` manipulation. Decided in `00_config.md` Q4.
- **Loose/older Python version floor** (`requires-python = ">=3.9"`), not
  pinned to the newest interpreter — decided in `00_config.md` Q3 for
  broad compatibility.
- **The manifest format is revisited per step, not locked in forever** —
  `00_config.md` Q5. If a later step needs something `requirements.txt`
  can't express well, that's a legitimate new question, not a violation
  of precedent.
- Every step's `pyproject.toml` uses the same `name = "boukensha"` — only
  `description` changes, to name the current step.

## Directory shape (mirrors Ruby exactly)

- **Every Python step is a full self-contained copy** of the `boukensha`
  package at that point in history — settled in `01_struct_skeleton.md` Q1
  specifically to mirror Ruby's own per-step-folder duplication
  (see `week1_baseline/ruby/ITERATIONS.md`). Don't factor shared, unchanged
  code into one common location across steps, even though it means
  hand-copying files that haven't changed.
- Runner scripts (`week1_baseline/bin/python/<step>`) are pre-scaffolded
  ahead of the Ruby tutorial's actual progress — most steps 00 through 12
  already have a runner file waiting, even for Ruby steps that don't exist
  yet. Don't create the runner; it already defines the contract
  (`cd week1_baseline/python/<step> && "$REPO_ROOT/.venv/bin/python" examples/example.py`).
  Do check it's executable — this has been found missing (`chmod +x`) at
  least once (step 03).
- The `.boukensha/` config fixture at the repo root is shared, real, and
  untouched by the port — same resolution order, same schema, across
  every step. Don't modify it as part of a port; it's a fixed test fixture.

## Ruby idiom → Python idiom (recurring translations)

- **`Struct.new(...) do ... end` with one overridden method (`to_s`) →
  `@dataclass` with `__str__` overridden.** (`Tool`, `Message`.)
- **Plain Ruby `class` with `attr_reader`s and mutable instance state →
  plain Python class with `@property` getters (no setters, matching
  Ruby's read-only `attr_reader`).** (`Context`.)
- **Symbol/string dual-key hashes → plain string keys, no dual form
  needed.** Ruby's `dig`/`tasks` accept both `:player` and `"player"`
  because Ruby hashes can be keyed either way; Python has only `str` keys,
  so the dual-lookup logic simply doesn't need porting — not a behavior
  gap, a simplification.
- **Symbol role/name literals → string literals.** `ctx.add_message(:user, ...)`
  becomes `ctx.add_message("user", ...)`; `case msg.role when :tool_result`
  becomes `if msg.role == "tool_result"`.
- **Trailing block syntax (`do |x:| ... end`) → an explicit `block=`
  keyword argument**, a plain `lambda`/`def`. Matching Ruby's
  keyword-arg-only blocks, these callables should also be **keyword-only**
  in Python (`lambda *, direction: ...`, not `lambda direction: ...`) —
  decided in `02_the_registry.md` Q1/Q2.
- **Bang/query method names drop the punctuation**: `validate_model!` →
  `validate_model`, `prompt_override?` → `prompt_override`. Python has no
  syntactic equivalent, so the convention is just to drop it, not
  replace it with `_bang`/`is_` prefixes.
- **A Ruby class-method/instance-method name collision has no direct
  Python equivalent and needs an explicit rename.** Ruby's singleton-class
  method table lets `self.model_info(model)` (class-level lookup) and
  `model_info` (zero-arg instance reader) share one name; Python has one
  namespace per class body, so the second definition silently clobbers
  the first. When this comes up, ask the user which one keeps the
  original name (see `03_prompt_builder.md`'s resolution: classmethod kept
  `model_info`, instance reader renamed to `current_model_info` — pick
  based on which call sites are external/public vs. internal-only).
- **`Hash#fetch` / `ENV.fetch` (raises on missing key) → `dict[key]` /
  `os.environ[key]`** (also raises, `KeyError`) — a direct translation,
  no `.get()` fallback needed.
- **`JSON.pretty_generate` → `json.dumps(payload, indent=2)`.** Expect a
  cosmetic difference on empty collections (see below), not a
  byte-identical match.

## What counts as an acceptable "cosmetic diff" vs. a real bug

When diffing Ruby and Python runner output against the same
`.boukensha/` fixture, these differences are expected and *not* bugs —
don't try to make them byte-identical:

- Ruby's `#<Boukensha::Config ...>` object repr vs. Python's
  `<Boukensha.Config ...>` (`__repr__`/`__str__` formatting only).
- Ruby's `[:direction]` (symbol array repr) vs. Python's `['direction']`
  (string list repr) when a struct's `to_s`/`__str__` prints
  `parameters.keys()`.
- Ruby's `JSON.pretty_generate` spreads empty arrays/hashes across
  multiple lines (`"properties": {\n},`); Python's `json.dumps(indent=2)`
  compacts them onto one line (`"properties": {},`). Same content,
  different pretty-printer.

Anything beyond these categories in a diff is a real discrepancy worth
investigating, not something to wave away as "just a Ruby/Python thing."

## Live/paid side-effect verification policy

**Step 04** introduced something none of steps 00–03 had: `Client` makes a
real HTTP call to a live LLM API, with no dry-run mode, and no way to
exercise it at all without that call actually happening. This was found by
actually running the Ruby example (not by reading the code and assuming) —
it hit `api.anthropic.com` for real and came back with a genuine
tool-use response and real token usage, using whatever key sits in
`.boukensha/.env`. That's a materially different situation from "run it as
many times as you like to diff cosmetic output," and it was handled in two
parts:

- **Ask the user before treating live calls as free to repeat.** This
  isn't something to decide unilaterally just because "the code needs to
  be tested" — it's real money and a real external service, the same
  category of thing this skill already asks about for hard-to-reverse
  actions generally. Step 04's resolution: verify by running the built
  example **once**, not in a loop, and not for the kind of repeated
  cosmetic re-diffing steps 00–03 tolerated.
- **Verify the actual logic — retries, backoff, error paths — against a
  local mock, not the live service, before spending any of that budget.**
  A real API essentially never fails on demand, so a single live call can
  only ever confirm the happy path; it says nothing about whether the
  retry/backoff math is right, whether a non-retryable status code short-
  circuits correctly, or whether exhausting retries actually raises the
  right error. Step 04 stood up a throwaway `http.server.HTTPServer` in a
  background thread that returned canned success/error responses, and
  exercised all four cases (happy path, retry-then-succeed with correct
  backoff timing, immediate failure on a non-retryable code, exhausted-
  retries) against that — all confirmed working *before* the one live
  call was spent.

The general shape: **when a step's new code has a real-world cost or
side effect, the free/local verification work (mocks, fakes, stubs) is not
optional scaffolding — it's what actually proves the logic is correct,
since the live/paid path usually can't exercise the failure branches at
all.** Treat "verify with a mock first" as the default whenever a later
step introduces something else in this category (a different paid API, a
write to a real external system, anything non-idempotent) — not something
unique to HTTP clients specifically.

## Discovered-bug policy

Twice now the Ruby source has turned out to have a real defect once read
closely:

- **Step 02**: the Ruby README's own "Expected Output" block was stale
  and didn't match the actual `Tool`/`Context` `to_s` format. Resolution:
  match the *real, verified* Ruby behavior (run the Ruby example and look
  at what it actually prints), not the stale README text — and fix the
  same staleness in the ported README rather than propagating it forward.
- **Step 03**: `PromptBuilder#to_messages` calls
  `backend.to_messages(messages)` with one argument unconditionally, but
  three of the five backends declare `to_messages(system, messages)` —
  two required arguments. This is a latent bug that the shipped
  `.boukensha/settings.yaml` fixture never exercises (it only selects the
  two backends whose `to_messages` takes one argument), so nothing in the
  example actually breaks. Resolution (user's explicit call, asked via
  `AskUserQuestion`): preserve the bug faithfully in the port rather than
  quietly normalizing the five backends' signatures, and document it in
  the README's Considerations section as an inherited-not-fixed wrinkle.

The general policy this establishes: **when the Ruby source itself is
wrong or inconsistent, don't silently fix it while porting.** Surface it
to the user as an explicit open question (recommend preserving it unless
there's a strong reason not to — the point of the port is fidelity to the
Ruby lesson, warts included), and whichever way it's resolved, write down
*why* in the plan and/or the ported README so the decision doesn't need
re-justifying next time someone reads the code.
