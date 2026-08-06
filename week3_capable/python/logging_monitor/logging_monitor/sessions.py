"""Parses a Boukensha session .jsonl log into an ordered list of transcript
entries, one per phase worth showing in the UI, each carrying `duration_ms`
-- the wall-clock gap since the previous JSONL line (any phase, not just
ones that render an entry), now meaningful because `at` is microsecond-
precision (see boukensha/logger.py's `_iso_now`).

Ports week1_baseline/log_viz/lib/log_viz/session.rb's parse pass, trimmed to
what logging_monitor's session page actually renders.
"""
import glob
import json
import os
from datetime import datetime

DEFAULT_SESSIONS_SUBDIR = "sessions"

# Phases rendered as a distinct row in the transcript.
RENDERED_PHASES = {
    "turn", "prompt", "compaction", "reasoning", "plan", "response",
    "tool_call", "tool_result", "turn_end", "error", "limit_reached",
}


def _parse_at(at):
    if not at:
        return None
    try:
        return datetime.fromisoformat(at)
    except ValueError:
        return None


def _duration_ms(prev_dt, cur_dt):
    if prev_dt is None or cur_dt is None:
        return None
    return round((cur_dt - prev_dt).total_seconds() * 1000, 3)


def _extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "tool_use":
                parts.append("[tool_use: {}]".format(block.get("name")))
            elif btype == "tool_result":
                parts.append("[tool_result]")
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content) if content is not None else ""


class Entry:
    __slots__ = (
        "type", "text", "usage", "turn", "iteration", "duration_ms", "at",
        "tool_name", "tool_args", "tool_result", "tool_ok", "tool_error",
        "stop_reason", "reason", "iterations", "tokens", "before", "dropped",
        "redacted", "task", "provider", "model", "input_tokens", "output_tokens",
        "cost_usd", "where", "operation", "error_class", "error_message", "backtrace",
        "kind", "n", "max",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self):
        return {slot: getattr(self, slot) for slot in self.__slots__}


class ParseState:
    """Mutable state threaded across one session's event stream. Split out
    from Session.parse() so the SSE tail endpoint (server.py) can share the
    exact same per-event logic incrementally, across polls, instead of
    re-parsing the whole file on every tick.
    """

    def __init__(self):
        self.current_turn = 0
        self.current_iteration = 0
        self.pending_calls = []
        self.prev_dt = None
        self.started_at = None
        self.snapshot = {}
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.has_cost = False


def parse_event(state, event):
    """Processes one already-JSON-parsed event dict against `state`
    in place, returning the rendered Entry for it, or None if this phase
    isn't one the transcript renders a row for.
    """
    cur_dt = _parse_at(event.get("at"))
    duration_ms = _duration_ms(state.prev_dt, cur_dt)
    state.prev_dt = cur_dt or state.prev_dt

    phase = event.get("phase")

    if phase == "session_start":
        state.started_at = event.get("at")
        state.snapshot = event
        return None
    if phase == "turn":
        state.current_turn = event.get("n")
    elif phase == "iteration":
        state.current_iteration = event.get("n")

    if phase not in RENDERED_PHASES:
        return None

    entry = Entry(
        type=phase, at=event.get("at"), duration_ms=duration_ms,
        turn=state.current_turn, iteration=state.current_iteration,
    )

    if phase == "turn":
        pass
    elif phase == "prompt":
        messages = event.get("messages") or []
        message = messages[-1] if messages else None
        if message and message.get("role") == "user":
            entry.type = "user"
            entry.text = _extract_text(message.get("content"))
        else:
            return None
    elif phase == "compaction":
        entry.before = event.get("before")
        entry.dropped = event.get("dropped")
    elif phase == "reasoning":
        entry.text = event.get("text")
        entry.redacted = event.get("redacted")
    elif phase == "plan":
        entry.text = event.get("text")
    elif phase == "response":
        usage = event.get("usage") or {}
        entry.type = "assistant"
        entry.text = event.get("text")
        entry.usage = event.get("usage")
        entry.stop_reason = event.get("stop_reason")
        entry.task = event.get("task")
        entry.provider = event.get("provider")
        entry.model = event.get("model")
        entry.input_tokens = event.get("input_tokens", usage.get("input_tokens"))
        entry.output_tokens = event.get("output_tokens", usage.get("output_tokens"))
        entry.cost_usd = event.get("cost_usd")
        if entry.input_tokens is not None:
            state.total_input_tokens += int(entry.input_tokens)
        if entry.output_tokens is not None:
            state.total_output_tokens += int(entry.output_tokens)
        if entry.cost_usd is not None:
            state.total_cost_usd += float(entry.cost_usd)
            state.has_cost = True
    elif phase == "tool_call":
        state.pending_calls.append({"name": event.get("name"), "args": event.get("args")})
        entry.type = "tool_call"
        entry.tool_name = event.get("name")
        entry.tool_args = event.get("args")
    elif phase == "tool_result":
        call = state.pending_calls.pop(0) if state.pending_calls else {}
        entry.type = "tool"
        entry.tool_name = event.get("name") or call.get("name")
        entry.tool_args = call.get("args")
        entry.tool_result = event.get("result")
        entry.tool_ok = event.get("ok", True)
        entry.tool_error = event.get("error")
    elif phase == "turn_end":
        entry.reason = event.get("reason")
        entry.iterations = event.get("iterations")
        entry.tokens = event.get("tokens")
    elif phase == "limit_reached":
        entry.kind = event.get("kind")
        entry.n = event.get("n")
        entry.max = event.get("max")
    elif phase == "error":
        entry.where = event.get("where")
        entry.operation = event.get("operation")
        entry.error_class = event.get("error_class")
        entry.error_message = event.get("error_message")
        entry.backtrace = event.get("backtrace")

    return entry


class Session:
    def __init__(self, path):
        self.path = path
        self.id = os.path.splitext(os.path.basename(path))[0]
        self.entries = []
        self._state = ParseState()

    @property
    def started_at(self):
        return self._state.started_at

    @property
    def snapshot(self):
        return self._state.snapshot

    @property
    def total_input_tokens(self):
        return self._state.total_input_tokens

    @property
    def total_output_tokens(self):
        return self._state.total_output_tokens

    def estimated_cost(self):
        # Sums the logger-emitted per-response cost_usd (see
        # boukensha/logger.py's Logger.response), same as log_viz/lib/
        # log_viz/session.rb's Session#estimated_cost. None means no
        # response in this session carried a trustworthy cost.
        return self._state.total_cost_usd if self._state.has_cost else None

    @classmethod
    def load(cls, path):
        session = cls(path)
        session.parse()
        return session

    def parse(self):
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry = parse_event(self._state, event)
                if entry is not None:
                    self.entries.append(entry)

    def turn_count(self):
        turns = [e.turn for e in self.entries if e.turn is not None]
        return (max(turns) + 1) if turns else 0

    def first_task(self):
        # The command/question that actually started the session -- the
        # first user turn, same as log_viz/lib/log_viz/session.rb's `task`.
        for e in self.entries:
            if e.type == "user":
                return e.text
        return None

    def final_response(self):
        for e in reversed(self.entries):
            if e.type == "assistant" and e.stop_reason != "tool_use" and not (e.text or "").startswith("(tool use"):
                return e.text
        return None

    def total_duration_ms(self):
        times = [_parse_at(e.at) for e in self.entries if e.at]
        times = [t for t in times if t]
        if len(times) < 2 and not self.started_at:
            return None
        start = _parse_at(self.started_at) or (times[0] if times else None)
        if not start or not times:
            return None
        return round((times[-1] - start).total_seconds() * 1000, 1)

    def to_summary(self):
        return {
            "id": self.id,
            "started_at": self.started_at,
            "task": self.first_task(),
            "model": self.snapshot.get("model"),
            "provider": self.snapshot.get("provider"),
            "turn_count": self.turn_count(),
            "tool_call_count": sum(1 for e in self.entries if e.type == "tool"),
            "error_count": sum(1 for e in self.entries if e.type == "error"),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "cost_usd": self.estimated_cost(),
            "total_duration_ms": self.total_duration_ms(),
            "final_response": self.final_response(),
        }


def sessions_dir(boukensha_dir):
    return os.path.join(boukensha_dir, DEFAULT_SESSIONS_SUBDIR)


def session_paths(boukensha_dir):
    return sorted(glob.glob(os.path.join(sessions_dir(boukensha_dir), "*.jsonl")), reverse=True)


def session_path(boukensha_dir, session_id):
    safe_id = os.path.basename(session_id)
    return os.path.join(sessions_dir(boukensha_dir), "{}.jsonl".format(safe_id))
