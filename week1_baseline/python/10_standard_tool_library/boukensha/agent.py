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
        task_settings=None,
        max_iterations=None,
        max_output_tokens=None,
    ) -> None:
        self._context = context
        self._registry = registry
        self._builder = builder
        self._client = client
        self._logger = logger if logger is not None else Logger()
        self._max_iterations = self._resolve_max_iterations(task_settings, max_iterations)
        self._max_output_tokens = self._resolve_max_output_tokens(task_settings, max_output_tokens)
        self._iteration = 0

    def run(self):
        while True:
            # Limits are *trigger thresholds*, not hard caps: once we reach
            # one we stop starting new work iterations and make exactly one
            # terminal wind-down call instead of raising.
            if self._iteration_limit_reached():
                self._logger.limit_reached(
                    kind="max_iterations", n=self._iteration, max=self._max_iterations
                )
                return self._wrap_up("max_iterations")

            self._iteration += 1
            self._logger.iteration(n=self._iteration, max=self._max_iterations)
            self._logger.prompt(messages=self._context.messages, tools=self._context.tools)

            response = self._client.call(**self._call_opts())
            self._logger.raw(data=response)
            parsed = self._builder.parse_response(response)

            if parsed["stop_reason"] == "tool_use":
                self._handle_tool_calls(parsed["content"], response)
            else:
                text = self._extract_text(parsed["content"])
                self._log_response(text=text, response=response)
                self._logger.turn_end(reason="completed", iterations=self._iteration)
                self._context.add_message("assistant", text)
                return text

    # ---------- private -----------------------------------------------

    def _resolve_max_iterations(self, task_settings, explicit):
        if explicit is not None:
            return int(explicit)
        if task_settings and hasattr(self._context.task, "max_iterations"):
            return self._context.task.max_iterations(task_settings)
        return self.MAX_ITERATIONS

    def _resolve_max_output_tokens(self, task_settings, explicit):
        if explicit is not None:
            return explicit
        if task_settings and hasattr(self._context.task, "max_output_tokens"):
            return self._context.task.max_output_tokens(task_settings)
        return None

    def _iteration_limit_reached(self) -> bool:
        return self._max_iterations > 0 and self._iteration >= self._max_iterations

    # Per-call options shared by every model round-trip of the turn.
    def _call_opts(self):
        return {"max_output_tokens": self._max_output_tokens} if self._max_output_tokens else {}

    # One final, tools-disabled model call so the agent ends the turn in
    # character rather than aborting. Runs *outside* the counted loop: it
    # never re-checks the limits (so it cannot re-trigger) and does not
    # increment self._iteration. Falls back to a deterministic message if
    # the call fails.
    def _wrap_up(self, reason: str) -> str:
        self._context.add_message("user", self.WRAP_UP_DIRECTIVE)
        try:
            response = self._client.call(tools=[], max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS)
        except ApiError:
            msg = self._fallback_message(reason)
            self._logger.turn_end(reason=reason, iterations=self._iteration)
            self._context.add_message("assistant", msg)
            return msg

        text = self._extract_text(self._builder.parse_response(response)["content"])
        text = self._fallback_message(reason) if not text.strip() else text
        self._log_response(text=text, response=response)
        self._logger.turn_end(reason=reason, iterations=self._iteration)
        self._context.add_message("assistant", text)
        return text

    def _fallback_message(self, reason: str) -> str:
        return (
            "I reached my {}-action limit for this turn before finishing "
            "({}). Ask me to continue and I'll pick up from here."
        ).format(self._max_iterations, reason)

    def _extract_text(self, content) -> str:
        return "".join(b["text"] for b in content if b["type"] == "text")

    def _handle_tool_calls(self, content, response) -> None:
        tool_calls = [b for b in content if b["type"] == "tool_use"]

        reasoning = self._extract_text(content)
        placeholder = "(tool use — {} call{})".format(
            len(tool_calls), "" if len(tool_calls) == 1 else "s"
        )
        self._log_response(text=reasoning if reasoning.strip() else placeholder, response=response)

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

            self._context.add_message("tool_result", str(result), tool_use_id=use_id)

    def _log_response(self, *, text, response) -> None:
        self._logger.response(
            text=text,
            usage=self._normalized_usage(response),
            stop_reason=response.get("stop_reason"),
            task=self._context.task,
            backend=self._builder.backend(),
        )

    def _normalized_usage(self, response):
        if response.get("usage"):
            return response["usage"]
        if response.get("usageMetadata"):
            return response["usageMetadata"]

        usage = {}
        for key in ("prompt_eval_count", "eval_count"):
            if key in response:
                usage[key] = response[key]
        return usage or None
