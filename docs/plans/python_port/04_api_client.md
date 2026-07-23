# Python Port Plan — Step 04: The API Client

## Scope

Port `week1_baseline/ruby/04_api_client` to a new
`week1_baseline/python/04_api_client`. Same as steps 00–03, this is a
self-contained copy of the `boukensha` package at this point in its
history (mirroring Ruby's per-step-folder duplication), not a diff
against `python/03_prompt_builder`.

The runner already exists and defines the contract:
`week1_baseline/bin/python/04_api_client` does

```bash
cd week1_baseline/python/04_api_client
"$REPO_ROOT/.venv/bin/python" examples/example.py
```

— same shared repo-root `.venv` as steps 00–03 (see
`docs/plans/python_port/00_config` for the settled venv/packaging answers,
reused unchanged).

**This step is different from every prior step in one important way: the
example makes a real, live HTTP POST to `https://api.anthropic.com/v1/messages`
using whatever key is in `.boukensha/.env`.** This was confirmed by actually
running the Ruby example — it reached the real API and got back a genuine
tool-use response with real token usage. Steps 00–03 never touched the
network. Per discussion with the user: verification during this port should
run the built example **once**, to confirm the round trip works (which is
the entire point of this step), not repeatedly the way earlier steps'
outputs were diffed freely.

## Source files being ported (reference)

| Ruby source | Purpose | Python target |
|---|---|---|
| `Gemfile` (`dotenv` only) | unchanged | `requirements.txt` (unchanged) |
| `lib/boukensha.rb` | require list — adds `require_relative "boukensha/client"` | `boukensha/__init__.py` — adds `Client` and `ApiError` to exports |
| `lib/boukensha/client.rb` | **new** — `Client#call(max_output_tokens:)`: builds the request from a `PromptBuilder`, POSTs it via `net/http` with retry/backoff on transient errors and retryable status codes, raises `ApiError` on final failure, returns parsed JSON on success | `boukensha/client.py` — new `Client` class, stdlib `urllib.request` only (see design mapping) |
| `lib/boukensha/errors.rb` | **changed** — adds `ApiError < StandardError` | `boukensha/errors.py` — add `class ApiError(Exception): pass` |
| `lib/boukensha/config.rb` | **cosmetic only** — one comment reworded ("gem/library code" → "this step"), trailing blank line. No functional change from step 03 | `boukensha/config.py` — copy forward from step 03, reword the one comment to match |
| `lib/boukensha/tasks/base.rb` | **changed** — (a) fixes an error-message typo (`settings.yml` → `settings.yaml`) in `provider`/`model`; (b) `fetch` (the private helper both of those and `prompt_override?` route through) gains a guard: `return nil unless settings.is_a?(Hash)` | `boukensha/tasks/base.py` — (a) **already matches**, verified: the existing Python port already says `"...required in settings.yaml"` (it never carried the Ruby typo), so no change needed there; (b) add the missing `isinstance(settings, dict)` guard — see design mapping |
| `lib/boukensha/tool.rb`, `message.rb`, `context.rb`, `registry.rb`, `prompt_builder.rb` | byte-identical to step 03 (`diff` confirmed) | copy forward unchanged from `python/03_prompt_builder` |
| `lib/boukensha/backends/*.rb` (all 5 + `base.rb`) | byte-identical to step 03 (`diff` confirmed) — the Ruby README's own "Updated Files" table claims backends "now own supported model tables," but that was already true as of step 03; treat that table entry as stale, not a real step-04 change | copy forward unchanged from `python/03_prompt_builder` |
| `lib/boukensha/tasks/player.rb` | byte-identical to step 03 | copy forward unchanged |
| `prompts/system.md` | **changed** — new default system prompt text ("Boukensha, an autonomous player exploring a CircleMUD world...") | `prompts/system.md` — copy new text verbatim (still unused by the shipped fixture, which sets `prompt_override.system: true` and supplies its own override) |
| `examples/example.rb` | builds `Config` → `Context` → `Registry`, registers `read_file`/`list_directory` tools, adds one user message, resolves provider/model, builds `PromptBuilder` + `Client`, calls `client.call`, prints the raw JSON response | `examples/example.py` |
| `README.md` | Client contract, "No Dependencies" rationale, OpenSSL rough-edge note, per-backend raw response shape, Considerations, Review Considerations | `README.md` (adapted — see design mapping for what does/doesn't transfer) |

Runner already in place, no change needed: `week1_baseline/bin/python/04_api_client`
(verify it's executable — step 03's wasn't, by default).

**Note on the README's own tables**: this step's Ruby README's "Updated
Files" table lists `config.rb` as now "reads `tasks.player` instead of
top-level provider/model settings" — but `config.rb` has read task-based
settings since step 00. Like the stale "Expected Output" block discovered
in step 02's README, this table describes cumulative history rather than
the real step-03→step-04 delta. The plan (and the ported README) should
describe the real, `diff`-verified change, not repeat the stale claim.

## Target layout

```
week1_baseline/python/04_api_client/
  requirements.txt
  pyproject.toml                  # editable-install metadata, same pattern as 00-03
  prompts/
    system.md                      # new text this step
  boukensha/
    __init__.py                    # adds Client, ApiError to exports
    config.py                      # copied forward, one comment reworded
    tool.py                        # copied forward
    message.py                     # copied forward
    context.py                     # copied forward
    errors.py                      # adds ApiError
    registry.py                    # copied forward
    prompt_builder.py               # copied forward
    client.py                      # new
    tasks/
      __init__.py
      base.py                      # copied forward, adds isinstance(settings, dict) guard
      player.py                    # copied forward
    backends/
      __init__.py
      base.py                      # copied forward
      anthropic.py                 # copied forward
      ollama.py                    # copied forward
      ollama_cloud.py               # copied forward
      openai.py                    # copied forward
      gemini.py                    # copied forward
  examples/
    example.py
  README.md
```

## Ruby → Python design mapping

- **`net/http` → `urllib.request` (stdlib only), not `requests`.** The
  Ruby README is explicit that avoiding third-party HTTP libraries is
  intentional ("the HTTP call itself is trivial and should be visible, not
  hidden behind a library"), and this matches the project-wide directive in
  `week1_baseline/ruby/ITERATIONS.md` ("attempt to use the Standard Library
  as much as possible and avoid introducing third party libraries"). Python
  has an equally capable stdlib option (`urllib.request`), so there's no
  reason to break that precedent here — this isn't presented as an open
  question because the existing project-wide constraint already answers it.
- **The retry/transient-error structure differs in shape, not intent,
  because of how the two HTTP stacks report failure.** Ruby's `net/http`
  always returns a response object, even for a 500 or 429 — the caller
  checks `response.is_a?(Net::HTTPSuccess)` explicitly. Python's
  `urllib.request.urlopen` instead *raises* `urllib.error.HTTPError` for any
  non-2xx status (an `HTTPError` is itself usable like a response — it has
  `.code`, `.reason`, `.read()`). So the Python `Client.call` has two
  `except` clauses instead of one `if`/`else`:
  - `except urllib.error.HTTPError as e:` — status-based failures. Retry if
    `e.code` is in `RETRYABLE_STATUS_CODES` and attempts remain; otherwise
    raise `ApiError` with the code + body, same message shape as Ruby.
  - `except (URLError, TimeoutError, ConnectionError, IncompleteRead, ssl.SSLError):`
    — connection-level failures. Retry with the same exponential backoff.
- **Ruby's explicit 8-class `TRANSIENT_ERRORS` whitelist doesn't map
  one-to-one onto Python exception types, and that's fine — document it as
  a deliberate simplification, not a gap.** `urllib.error.URLError` already
  buckets most of Ruby's individually-listed causes (`Errno::ECONNRESET`,
  `Errno::ECONNREFUSED`, `SocketError`/DNS failure, `OpenSSL::SSL::SSLError`,
  `Net::OpenTimeout`) under one exception type, wrapping the real cause in
  `.reason` — Python's stdlib just doesn't split these the way Ruby's does.
  `TimeoutError`, `ConnectionError` (base of `ConnectionResetError`/
  `ConnectionRefusedError`), and `http.client.IncompleteRead` are also
  caught directly alongside `URLError`, because those three can surface
  *unwrapped* when a failure happens during `response.read()` — i.e. after
  `urlopen()` already returned successfully and the connection drops
  mid-body, the Ruby analogue of catching bare `EOFError`.
- **`Client` stays a stateful instance holding `@builder`/`self._builder`,
  matching Ruby exactly — this is a known, self-acknowledged wrinkle in the
  Ruby source, not something to "fix" while porting.** The Ruby README's own
  "Review Considerations" section says outright: *"It looks like some
  generated code did not adhere to the stateless classes... eg. Client but
  we are going to keep it the same for now."* Per the discovered-quirk
  policy established in steps 02/03 (preserve, document, don't silently
  fix), the Python `Client.__init__(self, builder)` mirrors this rather
  than becoming a stateless function or classmethod.
- **The OpenSSL certificate rough edge in the Ruby README doesn't transfer
  and doesn't need a Python equivalent workaround.** Ruby's `net/http`
  historically needed an explicit `ca_file` on some platforms (the Ruby
  source's own comment notes `OpenSSL::X509::DEFAULT_CERT_FILE` breaks on
  Linux/WSL2 and is left commented out, relying on system-default cert
  discovery instead). Python's `urllib.request` already uses
  `ssl.create_default_context()` automatically for `https://` URLs, which
  resolves system CA certs the same way on macOS/Linux/Windows with zero
  configuration — there's no analogous rough edge to reproduce or document
  as a workaround. Note this as a "doesn't transfer" item in the ported
  README, same treatment as the symbol→string non-transfer note in step
  02's README.
- **`tasks/base.py` gains the same `isinstance(settings, dict)` guard Ruby
  added to its private `fetch` helper.** The existing Python port never had
  a shared `fetch` helper (it inlined `.get()` calls directly in `provider`/
  `model`/`prompt_override`, since Python doesn't need Ruby's
  symbol/string dual-key handling) — but the *new* guard Ruby added is about
  something else: defending against `settings` not being a dict at all
  (e.g. `None`, if a task name isn't found in `settings.yaml`). Add a small
  private `_fetch(settings, key)` classmethod matching Ruby's now-explicit
  one, used by `provider`, `model`, and `prompt_override`, so this defense
  exists in one place: `return settings.get(key) if isinstance(settings, dict) else None`.
- **`ApiError(Exception)`** — same plain-marker-exception treatment as
  `UnknownToolError`/`UnsupportedModelError`.
- **`JSON.parse(response.body)` → `json.loads(response.read())`** — the one
  extra step is decoding bytes (`response.read()` returns `bytes`;
  `json.loads` accepts `bytes` directly in Python 3, no explicit `.decode()`
  needed).
- **Retry backoff formula is a direct translation**:
  `BASE_RETRY_DELAY * (2 ** (attempt - 1))`, `MAX_RETRIES = 3`,
  `BASE_RETRY_DELAY = 0.5` — same constants, same formula, `time.sleep`
  instead of Ruby's `sleep`.
- **New tools in `examples/example.py` (`read_file`, `list_directory`) are
  plain local filesystem operations** — `Path(path).read_text()` for
  `read_file`; `os.listdir(path)` filtered to drop dotfiles (matching
  Ruby's `Dir.entries(path).reject { |f| f.start_with?(".") }`, which
  includes `.`/`..` in the unfiltered list — Python's `os.listdir` never
  includes those two, so the filter only needs to drop other dotfiles, a
  minor behavioral non-issue worth noting rather than silently diverging
  on).

## Config directory & schema

Unchanged from steps 00–03 — same `.boukensha/` fixture. One operational
note specific to this step: **the fixture's `.env` currently holds a real,
live `ANTHROPIC_API_KEY`**, not a placeholder — confirmed by actually
running the Ruby example and getting a real tool-use response back. This
means both `example.rb` and the ported `example.py` make a small real,
billed API call every time they're run unconditionally (no dry-run flag in
either). Per the user: verify the built Python example works by running it
once, not repeatedly.

## Task list

1. Create `week1_baseline/python/04_api_client/` skeleton (dirs above).
2. Copy forward `tool.py`, `message.py`, `context.py`, `registry.py`,
   `prompt_builder.py`, `tasks/player.py`, and all of `backends/*.py`
   verbatim from `python/03_prompt_builder`.
3. Copy forward `config.py`, rewording the one comment
   ("shipped alongside this package's code" → "shipped alongside this
   step", matching Ruby's wording change) — no functional change.
4. Update `errors.py`: add `ApiError(Exception)`.
5. Update `tasks/base.py`: add the `_fetch(settings, key)` guard helper
   and route `provider`/`model`/`prompt_override` through it.
6. Write `boukensha/client.py`: `Client` class per the design mapping
   above (`urllib.request`, `HTTPError`/connection-error retry split,
   exponential backoff, `ApiError` on final failure).
7. Copy forward `prompts/system.md` with the new text.
8. Wire `boukensha/__init__.py` to add `Client` and `ApiError` to the
   existing step-03 export list.
9. Port `examples/example.py`: `read_file`/`list_directory` tools, one
   user message, provider/model resolution (same if/elif chain as step
   03), `PromptBuilder` + `Client`, print config/provider/model/url, call
   `client.call()`, pretty-print the raw JSON response.
10. Reuse `requirements.txt` (PyYAML, python-dotenv — `Client` needs
    nothing new, it's stdlib-only) and `pyproject.toml` from the step 03
    pattern, bumping `description` to reference Step 4.
11. Install this step editable into the shared root `.venv`
    (`pip install -e week1_baseline/python/04_api_client`), repointing
    from step 03.
12. Verify the runner (`week1_baseline/bin/python/04_api_client`) is
    executable; `chmod +x` if not (found missing at least once before, in
    step 03).
13. Run `./week1_baseline/bin/python/04_api_client` **once** and confirm
    it reaches the real API and prints a parsed JSON response, matching
    the shape of the Ruby run captured during planning. Do not loop this
    for cosmetic diffing the way steps 00–03 were — one successful,
    real round trip is the whole point of this step and the full extent
    of the verification budget agreed with the user.
14. Port `README.md`: Client contract table, "No Dependencies" rationale
    (translated to "stdlib `urllib.request` only, no `requests`"), drop the
    OpenSSL-certificate-workaround section (doesn't transfer — note why
    instead), per-backend raw response shape examples (unchanged from
    Ruby, these are just what the APIs return), a Considerations section
    covering `ApiError`-on-failure and the retry/backoff behavior, and a
    Review Considerations section carrying forward both of Ruby's own
    self-noted wrinkles (hardcoded Ollama host — already true in the
    Python port since step 03; stateful `Client` — deliberately preserved,
    see design mapping above).

## Open questions

Resolved during planning:

1. **How to handle verification given this step makes real, billed API
   calls** (new territory — steps 00–03 were fully local) — **resolved:
   run the built Python example once to confirm the round trip works,
   then stop; don't re-run it for cosmetic diffing the way earlier steps'
   outputs were compared.**

Decided without asking (precedent already answers these; noted here for
visibility, not as open forks):

2. **stdlib `urllib.request` vs. a third-party HTTP library** — the
   Ruby README's own stated rationale plus the project-wide
   avoid-third-party-libraries directive in `ITERATIONS.md` already settle
   this in favor of stdlib-only.
3. **Whether to "fix" the self-acknowledged stateful-`Client` wrinkle** —
   the discovered-quirk policy from steps 02/03 (preserve + document,
   don't silently fix) already settles this; Ruby's own README flags it
   as a known, deliberately-kept wrinkle, not an oversight to correct.
