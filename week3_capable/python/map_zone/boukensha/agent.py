from .errors import ApiError
from .logger import Logger


class Agent:
    # Default iteration ceiling. The *enforced* value comes from the
    # max_iterations= constructor arg (sourced from Config at the run/repl
    # path), which falls back to this constant. 0 (or None) disables the
    # ceiling.
    MAX_ITERATIONS = 25

    # The wind-down call is deliberately short and cheap.
    WRAP_UP_OUTPUT_TOKENS = 400
    WRAP_UP_DIRECTIVE = (
        "You have reached your action limit for this turn. Do not call any more tools.\n"
        "Briefly summarize what you accomplished, what is still unfinished, and the\n"
        "single next action you would take."
    )

    def __init__(
        self,
        *,
        context,
        registry,
        builder,
        client,
        logger=None,
        max_iterations=None,
        max_turn_tokens=None,
        max_output_tokens=None,
    ) -> None:
        self._context = context
        self._registry = registry
        self._builder = builder
        self._client = client
        self._logger = logger if logger is not None else Logger()
        self._max_iterations = int(max_iterations or self.MAX_ITERATIONS)
        self._max_turn_tokens = int(max_turn_tokens or 0)  # 0 = disabled
        self._max_output_tokens = max_output_tokens
        self._iteration = 0

    def run(self):
        self._context.reset_turn_tokens()
        self._compact_if_needed()

        while True:
            # Two independent ceilings; stop at whichever trips first. Limits
            # are *trigger thresholds*, not hard caps: when one is reached we
            # stop starting new work iterations and make exactly one terminal
            # wind-down call (counted in tokens, but not as another iteration).
            if self._iteration_limit_reached():
                self._logger.limit_reached(
                    kind="max_iterations", n=self._iteration, max=self._max_iterations
                )
                return self._wrap_up("max_iterations")
            if self._token_limit_reached():
                self._logger.limit_reached(
                    kind="max_tokens", n=self._context.turn_tokens, max=self._max_turn_tokens
                )
                return self._wrap_up("max_tokens")

            self._iteration += 1
            self._logger.iteration(n=self._iteration, max=self._max_iterations)
            self._logger.prompt(
                messages=self._context.messages,
                tools=self._context.tools,
                context_window=self._context.context_window,
            )

            response = self._client.call(**self._call_opts())
            self._logger.raw(data=response)
            parsed = self._builder.parse_response(response)
            self._record_usage(response)
            self._log_reasoning(parsed["content"])

            if parsed["stop_reason"] == "tool_use":
                self._handle_tool_calls(parsed["content"], response)
            else:
                text = self._extract_text(parsed["content"])
                self._logger.response(
                    text=text, usage=self._normalize_usage(response),
                    stop_reason=parsed["stop_reason"], task=None, backend=self._builder.backend(),
                )
                self._logger.turn_end(
                    reason="completed", iterations=self._iteration, tokens=self._context.turn_tokens
                )
                self._context.add_message("assistant", text)
                return text

    # ---------- private -----------------------------------------------

    def _iteration_limit_reached(self) -> bool:
        return self._max_iterations > 0 and self._iteration >= self._max_iterations

    def _token_limit_reached(self) -> bool:
        return self._max_turn_tokens > 0 and self._context.turn_tokens >= self._max_turn_tokens

    # Per-call options shared by every model round-trip of the turn.
    def _call_opts(self):
        return {"max_output_tokens": self._max_output_tokens} if self._max_output_tokens else {}

    # Add this call's input+output to the cumulative turn total (the spend
    # budget) and refresh the known context size from input_tokens (compaction
    # pressure). The trigger is evaluated on pre-wrap-up spend; the reported
    # total includes the wind-down call too.
    def _record_usage(self, response) -> None:
        usage = self._normalize_usage(response)
        self._context.add_turn_tokens(usage.get("input_tokens"), usage.get("output_tokens"))
        self._context.update_tokens(usage.get("input_tokens"))

    # Ruby's step-12 Agent reads response["usage"] directly with no fallback,
    # which only Anthropic/OpenAI's raw responses actually nest usage under.
    # Gemini's raw response carries usageMetadata (promptTokenCount/
    # candidatesTokenCount); Ollama/OllamaCloud's raw response has flat
    # top-level prompt_eval_count/eval_count fields. Left as Ruby wrote it,
    # those three backends would silently show 0 context usage, never
    # auto-compact, and log no cost estimate -- invisible in the shipped
    # fixture, which is pinned to Anthropic. This restores the union lookup
    # steps 10/11's Agent already had (as a uniform input_tokens/output_tokens
    # shape, which also satisfies Logger.response's own key-fallback list),
    # fixing a real regression rather than porting it forward. See
    # docs/plans/python_port/12_context.md.
    def _normalize_usage(self, response):
        if response.get("usage"):
            return response["usage"]
        if response.get("usageMetadata"):
            meta = response["usageMetadata"]
            return {
                "input_tokens": meta.get("promptTokenCount"),
                "output_tokens": meta.get("candidatesTokenCount"),
            }
        if "prompt_eval_count" in response or "eval_count" in response:
            return {
                "input_tokens": response.get("prompt_eval_count"),
                "output_tokens": response.get("eval_count"),
            }
        return {}

    def _compact_if_needed(self) -> None:
        if not self._context.needs_compaction():
            return

        before = self._context.current_tokens
        dropped = self._context.compact_messages()
        self._logger.compaction(before=before, dropped=dropped, context_window=self._context.context_window)

    # One final, tools-disabled model call so the agent ends the turn in
    # character rather than aborting. Runs *outside* the counted loop: it
    # never re-checks the limits (so it cannot re-trigger) and does not
    # increment self._iteration, though its tokens still count toward the
    # reported turn total. Falls back to a deterministic message if the call
    # fails.
    def _wrap_up(self, reason: str) -> str:
        self._context.add_message("user", self.WRAP_UP_DIRECTIVE)
        try:
            response = self._client.call(tools=[], max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS)
        except ApiError as e:
            self._logger.error(e, where="Agent._wrap_up", operation="api_call")
            msg = self._fallback_message(reason)
            self._logger.turn_end(reason=reason, iterations=self._iteration, tokens=self._context.turn_tokens)
            self._context.add_message("assistant", msg)
            return msg

        parsed_wrap = self._builder.parse_response(response)
        text = self._extract_text(parsed_wrap["content"])
        text = self._fallback_message(reason) if not text.strip() else text
        self._record_usage(response)
        self._logger.response(
            text=text, usage=self._normalize_usage(response),
            stop_reason=parsed_wrap["stop_reason"], task=None, backend=self._builder.backend(),
        )
        self._logger.turn_end(reason=reason, iterations=self._iteration, tokens=self._context.turn_tokens)
        self._context.add_message("assistant", text)
        return text

    def _fallback_message(self, reason: str) -> str:
        return (
            "I reached my {}-action limit for this turn before finishing "
            "({}). Ask me to continue and I'll pick up from here."
        ).format(self._max_iterations, reason)

    def _extract_text(self, content) -> str:
        return "\n".join(b["text"] for b in content if b["type"] == "text")

    # Emit one `reasoning` event per reasoning block so the viewer can show
    # the model's thinking as a first-class step. Empty, non-redacted blocks
    # are skipped to avoid noise (a redacted/omitted block still renders,
    # since it tells the viewer "the model thought here").
    def _log_reasoning(self, content) -> None:
        for block in content:
            if block.get("type") != "reasoning":
                continue

            redacted = block.get("redacted") is True
            text = str(block.get("text") or "")
            if not text.strip() and not redacted:
                continue

            self._logger.reasoning(text=text, redacted=redacted)

    def _handle_tool_calls(self, content, response) -> None:
        tool_calls = [b for b in content if b["type"] == "tool_use"]

        # Log any preamble text that accompanied the tool call (carries no
        # usage -- the placeholder below owns the turn's usage chip), then
        # the placeholder.
        preamble = self._extract_text(content)
        if preamble.strip():
            self._logger.plan(text=preamble)
        self._logger.response(
            text="(tool use — {} call{})".format(len(tool_calls), "" if len(tool_calls) == 1 else "s"),
            usage=self._normalize_usage(response), stop_reason="tool_use",
        )

        self._context.add_message("assistant", content)

        for block in tool_calls:
            name = block["name"]
            args = block["input"]
            use_id = block["id"]

            self._logger.tool_call(name=name, args=args)
            try:
                result = self._registry.dispatch(name, args)
                self._logger.tool_result(name=name, result=result, ok=True)
            except Exception as e:
                result = "ERROR: {}: {}".format(type(e).__name__, e)
                self._logger.tool_result(name=name, result=result, ok=False, error=str(e))
                self._logger.error(e, where="Agent._handle_tool_calls", operation="tool_dispatch:{}".format(name))

            self._context.add_message("tool_result", str(result), tool_use_id=use_id)
