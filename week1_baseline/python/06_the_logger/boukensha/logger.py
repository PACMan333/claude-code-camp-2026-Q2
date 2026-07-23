import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

import boukensha

_PROVIDER_NAME_OVERRIDES = {"OpenAI": "openai"}


class Logger:
    DEFAULT_SESSION_DIR = "sessions"

    def __init__(self, *, session_id=None, dir=None, log=None, snapshot=None) -> None:
        snapshot = snapshot or {}
        self._session_id = session_id or self._generate_session_id()
        self._path = log or str(Path(dir or self._default_dir()) / "{}.jsonl".format(self._session_id))

        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._log_io = open(self._path, "a")
        self._write_log({"phase": "session_start", **snapshot})

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def path(self) -> str:
        return self._path

    def iteration(self, *, n, max) -> None:
        self._write_log({"phase": "iteration", "n": n, "max": max})

    def limit_reached(self, *, kind, n, max) -> None:
        self._write_log({"phase": "limit_reached", "kind": kind, "n": n, "max": max})

    def turn_end(self, *, reason, iterations, tokens=None) -> None:
        self._write_log({
            "phase": "turn_end",
            "reason": reason,
            "iterations": iterations,
            "tokens": tokens,
        })

    def prompt(self, *, messages, tools) -> None:
        self._write_log({
            "phase": "prompt",
            "message_count": len(messages),
            "messages": [self._serialize_message(m) for m in messages],
            "tool_count": len(tools),
            "tools": list(tools.keys()),
        })

    def tool_call(self, *, name, args) -> None:
        self._write_log({"phase": "tool_call", "name": name, "args": args})

    def tool_result(self, *, name, result, ok=True, error=None) -> None:
        self._write_log({
            "phase": "tool_result",
            "name": name,
            "result": str(result),
            "ok": ok,
            "error": error,
        })

    def response(self, *, text, usage=None, stop_reason=None, task=None, backend=None) -> None:
        event = {
            "phase": "response",
            "text": str(text).strip(),
            "usage": usage,
            "stop_reason": stop_reason,
        }
        event.update(self._execution_metadata(task=task, backend=backend, usage=usage))
        self._write_log(event)

    def raw(self, *, data) -> None:
        if not boukensha.is_debug():
            return

        self._write_log({"phase": "raw", "data": data})

    def close(self) -> None:
        if self._log_io:
            self._log_io.close()

    # ---------- private -----------------------------------------------

    def _default_dir(self) -> str:
        return str(Path(boukensha.current_config().dir) / self.DEFAULT_SESSION_DIR)

    def _write_log(self, event) -> None:
        line = json.dumps({**event, "session_id": self._session_id, "at": self._iso_now()})
        self._log_io.write(line + "\n")
        self._log_io.flush()

    def _generate_session_id(self) -> str:
        return "{}-{}".format(
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), secrets.token_hex(4)
        )

    def _iso_now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _serialize_message(self, msg):
        return {"role": msg.role, "content": msg.content}

    def _execution_metadata(self, *, task, backend, usage):
        if not (task or backend or usage):
            return {}

        tokens = self._usage_tokens(usage)
        metadata = {
            "task": self._task_name(task),
            "provider": self._provider_name(backend),
            "model": backend.model if backend else None,
            "usage_unit": backend.usage_unit if backend and hasattr(backend, "usage_unit") else None,
            "usage_level": backend.usage_level if backend and hasattr(backend, "usage_level") else None,
            "input_tokens": tokens["input"],
            "output_tokens": tokens["output"],
            "cost_usd": self._estimate_cost(backend, tokens),
        }
        return {k: v for k, v in metadata.items() if v is not None}

    def _task_name(self, task):
        if task is None:
            return None
        return task.task_name() if hasattr(task, "task_name") else str(task)

    def _provider_name(self, backend):
        if backend is None:
            return None

        name = type(backend).__name__
        return _PROVIDER_NAME_OVERRIDES.get(
            name, re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name).lower()
        )

    def _usage_tokens(self, usage):
        usage = usage or {}
        return {
            "input": self._first_integer(
                usage, "input_tokens", "prompt_tokens", "promptTokenCount", "prompt_eval_count"
            ),
            "output": self._first_integer(
                usage, "output_tokens", "completion_tokens", "candidatesTokenCount", "eval_count"
            ),
        }

    def _first_integer(self, usage, *keys):
        try:
            for key in keys:
                value = usage.get(key)
                if value is not None:
                    return int(value)
            return None
        except (ValueError, TypeError):
            return None

    def _estimate_cost(self, backend, tokens):
        if backend is None or not hasattr(backend, "estimate_cost"):
            return None
        if tokens["input"] is None or tokens["output"] is None:
            return None

        return backend.estimate_cost(input_tokens=tokens["input"], output_tokens=tokens["output"])
