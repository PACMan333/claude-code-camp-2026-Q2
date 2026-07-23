# 03 · The Prompt Builder (Python port)

Python port of `week1_baseline/ruby/03_prompt_builder`. Same behaviour, same
`.boukensha/` config directory — see that step's README for the full design
rationale (per-API format tables, considerations on statelessness, etc.).
This file only covers the Python-specific API, setup, and the differences
worth calling out (see Considerations).

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/03_prompt_builder/requirements.txt
.venv/bin/pip install -e week1_baseline/python/03_prompt_builder
```

This step is a self-contained copy of the `boukensha` package (mirroring
Ruby's per-step-folder duplication). `tool.py`, `message.py`, `context.py`,
and `tasks/base.py`/`tasks/player.py` are copied forward unchanged from
`python/02_the_registry`. `config.py` is copied forward too, but re-gains
the `PROMPTS_DIR` module constant — present back in `python/00_config`,
dropped in 01/02, and reinstated here because the Ruby source did the same
this step. Installing this step editable repoints `import boukensha` at
this step's copy.

## New Files

| File | Description |
|---|---|
| `boukensha/prompt_builder.py` | `PromptBuilder` — delegates serialization to whichever backend it's given |
| `boukensha/backends/base.py` | Shared backend contract: model validation, model metadata, cost estimation |
| `boukensha/backends/anthropic.py` | Serializes context into the Anthropic Messages API format |
| `boukensha/backends/ollama.py` | Serializes context into the local Ollama `/api/chat` format |
| `boukensha/backends/ollama_cloud.py` | Serializes context into the Ollama Cloud format |
| `boukensha/backends/openai.py` | Serializes context into the OpenAI Chat Completions format |
| `boukensha/backends/gemini.py` | Serializes context into the Gemini `generateContent` format |
| `boukensha/errors.py` | Gains `UnsupportedModelError` alongside `UnknownToolError` |
| `prompts/system.md` | Default system prompt, used when a task doesn't override it |

`PromptBuilder` does not call any API — it only prepares the payload, URL,
and headers for a request the caller makes itself.

## How It Works

```
Context (Python objects)
        |
PromptBuilder
        |
Backend (Anthropic, OpenAI, Gemini, or Ollama)
        |
API payload (plain dicts and lists)
        |
POST to API
```

## `boukensha.PromptBuilder`

| Method | Description |
|---|---|
| `to_messages()` | Delegates message serialization to the backend |
| `to_tools()` | Delegates tool serialization to the backend |
| `to_api_payload(max_output_tokens=1024)` | Assembles the complete payload ready to POST |
| `headers()` | Returns the correct headers for the backend |
| `url()` | Returns the correct endpoint URL for the backend |

## Backends

Each backend owns its supported model table as a `MODELS` class attribute,
keyed by model name (string, not Ruby symbol). A backend refuses to
construct with an unknown model — `configure_model` calls
`validate_model`, which raises `UnsupportedModelError` — so `settings.yaml`
can't silently select an unsupported or misspelled model. Each model entry
carries:

| Key | Meaning |
|---|---|
| `context_window` | The model's known token context window |
| `cost_per_million["input"]` | USD input token price per million tokens, when known |
| `cost_per_million["output"]` | USD output token price per million tokens, when known |
| `usage_unit` | `"tokens"`, `"local_compute"`, or `"ollama_cloud_usage"` |
| `usage_level` | Ollama Cloud usage tier, when applicable |

Backend instances expose `context_window`, `input_token_cost_per_million`,
`output_token_cost_per_million`, `usage_unit`, `usage_level`, and
`estimate_cost(input_tokens=, output_tokens=)` (keyword-only, matching
Ruby's keyword arguments here). For local Ollama models, cost is `0.0`.
For Ollama Cloud, pricing is plan/usage based rather than token based, so
`estimate_cost` returns `None`.

The prices in this step are static tutorial data, carried forward
unchanged from the Ruby source (current as of 2026-06-16 per that step's
README), and should be reviewed whenever the selected model set changes.

### `boukensha.Anthropic`

Talks to `https://api.anthropic.com/v1/messages`. Requires
`ANTHROPIC_API_KEY`. Supported models: `Anthropic.MODELS`.

### `boukensha.Ollama`

Talks to `http://localhost:11434/api/chat`. Requires `ollama serve`
running locally. No API key needed. Supported models: `Ollama.MODELS`.

### `boukensha.OllamaCloud`

Talks to `https://ollama.com/api/chat`. Requires `OLLAMA_API_KEY`.
Supported models: `OllamaCloud.MODELS`.

### `boukensha.OpenAI`

Talks to `https://api.openai.com/v1/chat/completions`. Requires
`OPENAI_API_KEY`. Supported models: `OpenAI.MODELS`.

### `boukensha.Gemini`

Talks to `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`.
Requires `GEMINI_API_KEY`. Supported models: `Gemini.MODELS`.

## Considerations

**Ruby → Python: the `model_info` class-method/instance-method name
collision doesn't survive translation as-is.** Ruby lets
`self.model_info(model)` (a class-method lookup by name) and `model_info`
(a zero-arg instance reader for the resolved model) share one name,
because Ruby stores class methods and instance methods in separate
tables. Python has a single namespace per class body, so keeping both
under `model_info` would let the second definition silently clobber the
first. This port keeps `model_info(model)` as the classmethod lookup and
renames the instance accessor to `current_model_info` — neither name is
referenced outside this class today, so the rename is invisible from the
call sites in `examples/example.py`.

**Ruby → Python: a latent, inherited arity bug in `PromptBuilder.to_messages()`.**
Ruby's `PromptBuilder#to_messages` calls `@backend.to_messages(@context.messages)`
— one argument, unconditionally. But `Anthropic`/`Gemini` define
`to_messages(messages)` (system is a separate top-level payload field for
those two APIs), while `Ollama`/`OllamaCloud`/`OpenAI` define
`to_messages(system, messages)` (these three APIs inline the system prompt
as a `role: system` message). Calling `PromptBuilder.to_messages()`
directly therefore raises for the three Ollama-family backends. This
port preserves that exactly — it is not fixed here. The shipped
`.boukensha/settings.yaml` fixture uses `provider: anthropic`, and
`examples/example.py` only calls `to_api_payload()` (whose `to_payload` on
each backend calls its own `to_messages` internally, with the right
arity, bypassing `PromptBuilder.to_messages` entirely) — so the bug is
real but not exercised by this step's example. Calling
`PromptBuilder(ctx, Ollama(...)).to_messages()` directly reproduces it:

```
TypeError: Ollama.to_messages() missing 1 required positional argument: 'messages'
```

**The conversation is stateless.** The model has no memory between turns.
Every API call includes the entire history from the beginning. BOUKENSHA
is responsible for carrying that state.

**Tool results are user messages on Anthropic.** This feels
counterintuitive — the result came from BOUKENSHA, not the human — but it
reflects how the Anthropic API models the conversation. Ollama, OpenAI,
and Gemini all handle this with dedicated message/part types instead.

**The agent only sees schemas.** The `description` field on each tool is
the only thing the agent uses to decide which tool to call. The actual
`block` never leaves BOUKENSHA.

## Run Example

```bash
./week1_baseline/bin/python/03_prompt_builder
```

Expected output (verified against the real Ruby output for the same
`.boukensha/` fixture — `provider: anthropic`, `model: claude-haiku-4-5`):

```
=== BOUKENSHA Step 3: Prompt Builder ===

Config: <Boukensha.Config dir=/path/to/.boukensha tasks=player>
Provider: anthropic
Model: claude-haiku-4-5
{
  "model": "claude-haiku-4-5",
  "system": "You are a MUD Journey Agent. ...",
  "max_tokens": 1024,
  "tools": [ ... ],
  "messages": [ ... ]
}
```

Expect the same class of cosmetic diff already accepted since step 00:
Ruby's `JSON.pretty_generate` spreads empty arrays/objects (`"properties": {\n},`)
across multiple lines; Python's `json.dumps(..., indent=2)` compacts them
onto one line (`"properties": {},`). Same content, different pretty-printer
— not a byte-identical match.
