# 04 · The API Client (Python port)

Python port of `week1_baseline/ruby/04_api_client`. Same behaviour, same
`.boukensha/` config directory — see that step's README for the full
per-backend raw response shapes. This file covers the Python-specific
API, setup, and what does/doesn't carry over from the Ruby source (see
Considerations).

**This step's example makes a real HTTP request to a live LLM API**, using
whatever key is configured in `.boukensha/.env`. Running it has a small
real cost. That's true of the Ruby step too — it's the whole point of this
step (proving the round trip actually works against a real API), not a
Python-specific concern.

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/04_api_client/requirements.txt
.venv/bin/pip install -e week1_baseline/python/04_api_client
```

This step is a self-contained copy of the `boukensha` package (mirroring
Ruby's per-step-folder duplication). `tool.py`, `message.py`, `context.py`,
`registry.py`, `prompt_builder.py`, `tasks/player.py`, and all five
backends are copied forward unchanged from `python/03_prompt_builder` —
their Ruby sources are byte-identical at this step too. Installing this
step editable repoints `import boukensha` at this step's copy.

## New Files

| File | Description |
|---|---|
| `boukensha/client.py` | `Client` — POSTs a `PromptBuilder` payload and returns the parsed JSON response |
| `boukensha/errors.py` | Gains `ApiError` alongside `UnknownToolError`/`UnsupportedModelError` |

## How It Works

```
PromptBuilder
      |
Client
      |
POST to API endpoint
      |
Raw JSON response
```

## `boukensha.Client`

| Method | Description |
|---|---|
| `call(max_output_tokens=1024)` | POSTs the payload and returns the parsed JSON response |

```python
builder = PromptBuilder(ctx, backend)
client = Client(builder)
response = client.call()
```

`Client` retries on transient failures (connection resets, DNS failures,
SSL errors, timeouts) and on a fixed set of retryable HTTP status codes
(408, 409, 429, 500, 502, 503, 504), up to 3 retries with exponential
backoff (0.5s, 1s, 2s). Anything else — or retries exhausted — raises
`ApiError` with the status code and response body (for HTTP failures) or
the underlying exception (for connection-level failures).

## No Third-Party Dependencies

`Client` uses Python's standard library `urllib.request` — no `requests`,
no HTTP client gem/package. This mirrors the Ruby step's own explicit
choice to use `net/http` instead of a gem like HTTParty, and the
project-wide preference (see `week1_baseline/ruby/ITERATIONS.md`) for
standard-library solutions over third-party dependencies: the HTTP call
itself is meant to be visible in the code, not hidden behind a library.

## What the Response Looks Like

The raw response shape differs between backends — see the Ruby step's
README for the full Anthropic/Ollama examples; they're unchanged by this
port, since they're just what each API actually returns. When the model
wants to call a tool, Anthropic adds a `tool_use` block to `content` with
`stop_reason: "tool_use"`; Ollama adds a `tool_calls` array to `message`.
Handling those differences is the job of a later step (the agent loop) —
this step only proves the raw round trip.

## Considerations

**`Client` raises `ApiError` on failure**, same as Ruby — a non-2xx
response or an exhausted retry budget means something went wrong (bad API
key, malformed payload, server error, network failure), and BOUKENSHA
surfaces that explicitly instead of returning `None` or a partial result.

**Ruby → Python: the retry/error-handling shape differs because the two
HTTP stacks report failure differently — not because of a design choice.**
Ruby's `net/http` always returns a response object, even for a 500 or 429;
the caller checks `response.is_a?(Net::HTTPSuccess)` itself. Python's
`urllib.request.urlopen` instead *raises* `urllib.error.HTTPError` for any
non-2xx status (itself usable like a response — it has `.code`, `.reason`,
`.read()`). So `Client.call` has two `except` clauses instead of one
`if`/`else`: one for `HTTPError` (status-based, checks the retryable-codes
set), one for connection-level transient errors.

**Ruby's explicit 8-class `TRANSIENT_ERRORS` whitelist doesn't map
one-to-one onto Python exception types — that's a simplification, not a
gap.** `urllib.error.URLError` already buckets most of what Ruby lists
individually (connection reset/refused, DNS failure, SSL handshake
failure, connect timeout) under one exception type, wrapping the real
cause in `.reason`. Python's port catches `URLError` broadly instead of
enumerating each wrapped cause, plus `TimeoutError`, `ConnectionError`,
and `http.client.IncompleteRead` directly — those three can surface
*unwrapped* when a failure happens reading the response body, after
`urlopen()` already returned successfully (the analogue of Ruby's bare
`EOFError`).

**Ruby → Python: the OpenSSL certificate rough edge in the Ruby README
doesn't transfer, and there's no Python equivalent workaround needed.**
Ruby's `net/http` historically needed an explicit `ca_file` on some
platforms — the Ruby source's own comment notes the "obvious" default
(`OpenSSL::X509::DEFAULT_CERT_FILE`) breaks on Linux/WSL2 and leaves it
commented out, relying on system cert discovery instead. Python's
`urllib.request` already uses `ssl.create_default_context()` automatically
for `https://` URLs, resolving system CA certs the same way across
macOS/Linux/Windows with zero configuration. There's nothing to work
around here.

## Review Considerations

Carried forward from the Ruby step's own README:

**The Ollama backend hardcodes `http://localhost:11434`** rather than
reading it from an environment variable. This was already true of the
Python port as of step 03 (`Ollama.__init__`'s `host` default) — not a new
step-04 change, just inherited as-is.

**`Client` is a stateful instance holding `self._builder`, not a stateless
function** — the Ruby README calls this out directly as a known
inconsistency ("some generated code did not adhere to the stateless
classes... eg. Client... but we are going to keep it the same for now").
This is a deliberate, acknowledged wrinkle in the Ruby source, not an
oversight — the Python port preserves it rather than "fixing" it into a
`@staticmethod`, matching the discovered-quirk policy already applied in
steps 02 and 03 (preserve and document, don't silently correct the
original lesson).

## Run Example

```bash
./week1_baseline/bin/python/04_api_client
```

This makes one real POST to the configured provider's API and prints the
raw JSON response — expect the shape to match the per-backend examples in
the Ruby step's README (same `id`/`content`/`stop_reason`/`usage` fields
for Anthropic, same `model`/`message`/`done_reason` fields for Ollama).
The exact response text and token counts will differ run to run since it's
a live model call, not a fixture.
