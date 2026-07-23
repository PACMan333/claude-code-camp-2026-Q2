# 05 · The Agent Loop (Python port)

Python port of `week1_baseline/ruby/05_agent_loop`. This is the step where
BOUKENSHA stops being setup and starts actually doing work: everything
before this — the structs, the registry, the prompt builder, the client —
supports the loop that lives here.

**Like step 04, this step's example makes real, billed HTTP requests to a
live LLM API**, using whatever key is configured in `.boukensha/.env` — and
now potentially several per turn (once per loop iteration, plus one
wind-down call), not just one.

## Setup

Uses the same shared repo-root `.venv` as the earlier steps:

```bash
.venv/bin/pip install -r week1_baseline/python/05_agent_loop/requirements.txt
.venv/bin/pip install -e week1_baseline/python/05_agent_loop
```

This step is a self-contained copy of the `boukensha` package (mirroring
Ruby's per-step-folder duplication). `config.py`, `tool.py`, `message.py`,
`context.py`, `registry.py`, `tasks/player.py`, `backends/base.py`, and
`prompts/system.md` are copied forward unchanged from
`python/04_api_client` — their Ruby sources are byte-identical at this
step too. Installing this step editable repoints `import boukensha` at
this step's copy.

## New Files

| File | Description |
|---|---|
| `boukensha/agent.py` | The agent loop — sends requests, dispatches tools, and knows when to stop |

## Updated Files

| File | Change |
|---|---|
| `boukensha/errors.py` | Adds `LoopError` (defined for future use — see Considerations, nothing raises it yet) |
| `boukensha/tasks/base.py` | Adds `max_iterations`/`max_output_tokens` classmethods, each with a default (25 / 1024) |
| `boukensha/client.py` | `call` gains a `tools=` keyword, threaded through to the payload |
| `boukensha/prompt_builder.py` | `to_api_payload` gains `tools=`; adds `parse_response`, delegating to the backend |
| `boukensha/backends/*.py` | Each gains `parse_response` (normalizes the raw reply) and, except Anthropic, a private `_assistant_message`/`_assistant_parts` (rebuilds a provider-specific assistant turn from the normalized shape) |

Note: the Ruby step's own README claims `context.rb` changed this step
("carries the active task object alongside messages and tools") — but
`Context` (and its Python port) has held `task` since step 04. That table
entry is stale in the Ruby source; this port doesn't repeat the claim.

## How It Works

```
send messages to API
        |
stop_reason == "tool_use"?
    yes -> extract tool calls
        -> dispatch each tool via Registry
        -> inject results as tool_result messages
        -> go back to top
    no  -> return final text response
```

## `boukensha.Agent`

| Method | Description |
|---|---|
| `run()` | Starts the loop and returns the final text response when the agent is done |

```python
agent = Agent(
    context=ctx,
    registry=registry,
    builder=builder,
    client=client,
    task_settings=player_settings,
)
result = agent.run()
```

## Every Backend Speaks the Same Normalized Shape

Five providers means five different response formats — Anthropic nests
tool calls inside `content`, Ollama puts them in `message["tool_calls"]`,
OpenAI nests them under `choices[0]["message"]["tool_calls"]`, and Gemini
calls them `functionCall` parts. Rather than teach the loop about each of
these, every backend implements `parse_response`, converting its raw
response into one common shape:

```python
{
    "stop_reason": "tool_use" | "end_turn",
    "content": [
        {"type": "text", "text": "..."},
        {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
    ],
}
```

`Agent` only ever sees this shape — it calls
`self._builder.parse_response(response)`, which delegates to the backend,
and never inspects a raw provider response directly.

The conversion also runs in reverse. When the conversation history is
replayed on the next request, OpenAI, Ollama, Ollama Cloud, and Gemini
each rebuild a provider-specific assistant message from the normalized
`content` blocks via a private `_assistant_message` (or `_assistant_parts`
for Gemini) method — the inverse of `parse_response`. Anthropic's
`content` array doubles as both the normalized shape and the wire format,
so it needs no extra conversion.

**Tool call IDs aren't universal.** Anthropic and OpenAI assign every tool
call a unique `id`, echoed back in the `tool_result`. Ollama, Ollama
Cloud, and Gemini don't assign call ids at all — those backends reuse the
tool's `name` as its `id` and match the `tool_result` back to the call by
name.

## Task Configuration

```yaml
tasks:
  player:
    provider: anthropic
    model: claude-haiku-4-5
    prompt_override:
      system: true
    max_iterations: 25
    max_output_tokens: 1024
```

`max_iterations` controls model round-trips per turn before wind-down, and
`max_output_tokens` is passed to each model reply. The shipped
`.boukensha/settings.yaml` doesn't set either key, so both fall back to
`Tasks.Base`'s defaults (25 and 1024) — that's expected, not a fixture
gap.

## What the Loop Looks Like

Running the example produces output like this:

```
=== BOUKENSHA Step 5: Agent Loop ===

[iteration 1/25]
  tool call → list_directory({'path': '.'})
  tool result → README.md, examples, lib

[iteration 2/25]
  tool call → read_file({'path': 'README.md'})
  tool result → # 05 · The Agent Loop (Python port)...

=== FINAL RESPONSE ===
This is BOUKENSHA's agent loop step...
```

## Considerations

**The assistant message must be stored before the tool result.** The
Anthropic API requires the assistant's `tool_use` block to appear in the
message history before its corresponding `tool_result`. `Agent._handle_tool_calls`
handles this by adding the assistant message first, then dispatching each
tool call and adding its result — get the order wrong and the API rejects
the request.

**The model can call multiple tools in one turn.** The loop handles this
by iterating over every `tool_use` block in a single response before
making the next API call.

**`Agent.MAX_ITERATIONS` and `Tasks.Base.DEFAULT_MAX_ITERATIONS` are two
independent constants that happen to both be 25, not the same value
referenced twice.** `Agent.MAX_ITERATIONS` is `Agent`'s own standalone
fallback, used only when it's constructed without `task_settings` (or the
task doesn't define `max_iterations`). In the shipped example, `Agent` is
always given `task_settings=player_settings` and `Player` always defines
`max_iterations`, so the value actually in effect is
`Tasks.Base.DEFAULT_MAX_ITERATIONS`, not `Agent.MAX_ITERATIONS` — they're
just numerically identical by coincidence of both defaulting to 25.

**The agent has no way to stop itself.** The model signals it's done via
`stop_reason: "end_turn"`; the loop watches for that and exits. The agent
never unilaterally decides to stop — reaching `max_iterations` triggers
one tools-disabled wind-down call rather than an immediate abort, so a
turn that runs out of room still ends with a coherent message instead of
a raised error.

**`LoopError` is defined but never raised — that's inherited from Ruby,
not a Python gap.** Ruby's `errors.rb` adds `LoopError` this step and its
own README describes it as being "for runaway agents," but `Agent#run`'s
iteration ceiling is handled entirely by the wind-down call, which
returns a message rather than raising anything. Grepping the whole Ruby
step confirms `LoopError` is referenced nowhere outside its own
definition and that one README line. It's ported here for parity (and
because a later step may wire it up), but nothing in this step raises it.

**Ruby's `config.rb` has a fixture-masked `PROMPTS_DIR` regression this
step; Python's `config.py` was never subject to it.** Ruby's `PROMPTS_DIR`
changed from `File.expand_path("../../prompts", __dir__)` (step 04,
correct) to `File.expand_path("../../../prompts", __dir__)` (step 05),
which now resolves one directory too high and points at a path that
doesn't exist. This never surfaces in practice because
`.boukensha/settings.yaml` sets `prompt_override.system: true`, so the
system prompt always resolves from the user-prompts override
(`.boukensha/prompts/player/system.md`) and never falls through to the
broken default-prompts path — the same "latent, fixture-masked bug" shape
as step 03's `to_messages` arity mismatch. Python's `config.py` computes
`PROMPTS_DIR` via a `pathlib` parent-chain
(`Path(__file__).resolve().parent.parent / "prompts"`), not by counting
`../` segments, and has done so since step 00 — it was never expressed
the way Ruby's is, so there's no equivalent bug to "preserve." This was a
deliberate choice, confirmed with the project owner rather than assumed:
Python's implementation is left correct as-is.

**Tool-call console logging prints Python's dict repr, not Ruby's Hash
repr** (`{'path': 'README.md'}` vs. Ruby's `{"path" => "README.md"}`) —
the same class of cosmetic, string-keyed-collection repr difference
already accepted for `Struct#to_s`/`dataclass.__str__` in earlier steps,
not a new kind of divergence.

## Run Example

```bash
./week1_baseline/bin/python/05_agent_loop
```

This makes one or more real POSTs to the configured provider's API (one
per loop iteration, plus a wind-down call if `max_iterations` is
reached) and prints the agent's final response. Exact iteration count,
response text, and token counts will differ run to run since it's a live
model call, not a fixture.
