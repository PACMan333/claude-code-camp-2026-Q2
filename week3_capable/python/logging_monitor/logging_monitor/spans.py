"""Reconstructs turn -> iteration -> api_call/tool_call spans from a flat
session JSONL event sequence, for the waterfall view (session.html).

The JSONL log has no explicit span boundaries -- it's a flat sequence of
point-in-time events. This is the same reconstruction
week2_observability/observability/scripts/session_to_traces.py already
established for shipping to Tempo via OTLP (turn -> iteration -> tool_call
nesting), re-targeted here at inline SVG instead of an OTLP payload, and
extended with an explicit `api_call` span: a `prompt` event paired with the
`response` event that follows it, isolating LLM round-trip latency from
tool execution time -- the single most useful span for "where did the time
go." Requires microsecond-precision `at` fields (boukensha/logger.py's
`_iso_now`) -- with only second precision every span would round to zero
or a whole second, useless for a waterfall.
"""
import html
from datetime import datetime

SVG_COLORS = {
    "turn": "#546e7a",
    "iteration": "#78909c",
    "api_call": "#1d4ed8",
    "tool_call": "#2e7d32",
    "tool_call_error": "#c62828",
    "compaction": "#9c27b0",
}


def _to_us(at):
    dt = datetime.fromisoformat(at)
    return int(dt.timestamp() * 1_000_000)


def _span(type_, label, start_us, **attrs):
    span = {
        "type": type_, "label": label, "start_us": start_us, "end_us": start_us,
        "duration_ms": 0.0, "children": [], "ok": True,
    }
    span.update(attrs)
    return span


def _close(span, end_us):
    span["end_us"] = max(end_us, span["start_us"])
    span["duration_ms"] = round((span["end_us"] - span["start_us"]) / 1000.0, 3)


def build_spans(events):
    """events: list of parsed JSONL dicts (one session's worth, in order).
    Returns {"session_start_us": int|None, "turns": [turn_span, ...]}.
    Each span: {type, label, start_us, end_us, duration_ms, start_offset_ms,
    children, ok, ...type-specific attributes}. `type` is one of "turn",
    "iteration", "api_call", "tool_call", "compaction".
    """
    turns = []
    turn_span = None
    iteration_span = None
    pending_api_call = None
    pending_tool_calls = []  # FIFO of open tool_call spans, positional match to tool_result
    pending_tool_error_links = {}  # tool name -> FIFO of closed, failed tool_call spans awaiting an `error` event
    session_start_us = None
    last_us = None

    def current_container():
        return iteration_span["children"] if iteration_span else (turn_span["children"] if turn_span else None)

    for event in events:
        at = event.get("at")
        if not at:
            continue
        ts = _to_us(at)
        last_us = ts
        if session_start_us is None:
            session_start_us = ts
        phase = event.get("phase")

        if phase == "turn":
            if iteration_span:
                _close(iteration_span, ts)
                iteration_span = None
            if turn_span:
                _close(turn_span, ts)
            turn_span = _span("turn", "turn {}".format(event.get("n")), ts, n=event.get("n"))
            turns.append(turn_span)

        elif phase == "iteration":
            if iteration_span:
                _close(iteration_span, ts)
            if turn_span is None:
                continue
            iteration_span = _span("iteration", "iteration {}".format(event.get("n")), ts, n=event.get("n"))
            turn_span["children"].append(iteration_span)

        elif phase == "prompt":
            pending_api_call = _span("api_call", "api_call", ts)

        elif phase == "response":
            container = current_container()
            if pending_api_call is not None:
                _close(pending_api_call, ts)
                pending_api_call["task"] = event.get("task")
                pending_api_call["provider"] = event.get("provider")
                pending_api_call["model"] = event.get("model")
                pending_api_call["cost_usd"] = event.get("cost_usd")
                pending_api_call["stop_reason"] = event.get("stop_reason")
                if container is not None:
                    container.append(pending_api_call)
                pending_api_call = None

        elif phase == "tool_call":
            container = current_container()
            span = _span("tool_call", event.get("name"), ts, tool_name=event.get("name"), args=event.get("args"))
            if container is not None:
                container.append(span)
            pending_tool_calls.append(span)

        elif phase == "tool_result":
            span = pending_tool_calls.pop(0) if pending_tool_calls else None
            if span is not None:
                _close(span, ts)
                span["ok"] = event.get("ok", True)
                span["tool_error"] = event.get("error")
                if not span["ok"]:
                    name = span["tool_name"]
                    pending_tool_error_links.setdefault(name, []).append(span)

        elif phase == "compaction":
            container = current_container()
            span = _span("compaction", "compaction", ts, before=event.get("before"), dropped=event.get("dropped"))
            if container is not None:
                container.append(span)

        elif phase == "error":
            operation = event.get("operation") or ""
            if operation.startswith("tool_dispatch:"):
                name = operation.split(":", 1)[1]
                queue = pending_tool_error_links.get(name)
                if queue:
                    span = queue.pop(0)
                    span["error_class"] = event.get("error_class")
                    span["error_message"] = event.get("error_message")
                    span["backtrace"] = event.get("backtrace")

        elif phase == "turn_end":
            if iteration_span:
                _close(iteration_span, ts)
                iteration_span = None
            if turn_span:
                turn_span["reason"] = event.get("reason")
                turn_span["iterations"] = event.get("iterations")
                turn_span["tokens"] = event.get("tokens")
                _close(turn_span, ts)
                turn_span = None

    if last_us is not None:
        if iteration_span:
            _close(iteration_span, last_us)
        if turn_span:
            _close(turn_span, last_us)

    _annotate_offsets(turns, session_start_us or 0)
    return {"session_start_us": session_start_us, "turns": turns}


def _annotate_offsets(spans, session_start_us):
    for span in spans:
        span["start_offset_ms"] = round((span["start_us"] - session_start_us) / 1000.0, 3)
        _annotate_offsets(span["children"], session_start_us)


def render_svg(waterfall, width_px=900, row_height=22, indent_px=14):
    """Inline SVG, generated server-side -- no charting library, no CDN
    dependency. One <rect> per span (a <polygon> diamond marker for the
    zero-width compaction case), y = one row per nesting level (turn row,
    its iteration rows indented under it, each iteration's api_call/
    tool_call spans indented further), a <title> child for hover tooltips
    with exact numbers, a text label for bars wide enough to hold one.
    `data-turn` on every row lets a click handler (session.html) scroll the
    transcript below to that turn.
    """
    turns = waterfall.get("turns") or []
    if not turns:
        return '<svg class="waterfall" viewBox="0 0 100 30"><text x="8" y="18" class="wf-empty">No turns recorded yet.</text></svg>'

    total_ms = max((t["start_offset_ms"] + t["duration_ms"]) for t in turns)
    total_ms = total_ms if total_ms > 0 else 1.0
    scale = width_px / total_ms

    rows = []  # (span, level, turn_n)

    def walk(span, level, turn_n):
        rows.append((span, level, turn_n if turn_n is not None else span.get("n")))
        for child in span["children"]:
            walk(child, level + 1, turn_n if turn_n is not None else span.get("n"))

    for turn in turns:
        walk(turn, 0, None)

    height_px = len(rows) * row_height + 8
    parts = [
        '<svg class="waterfall" viewBox="0 0 {} {}" xmlns="http://www.w3.org/2000/svg" '
        'role="img" aria-label="turn/iteration/api-call/tool-call waterfall">'.format(width_px, height_px)
    ]
    for i, (span, level, turn_n) in enumerate(rows):
        y = i * row_height + 4
        x = span["start_offset_ms"] * scale + level * indent_px
        w = max(span["duration_ms"] * scale, 2)
        color = SVG_COLORS.get(span["type"], "#999")
        if span["type"] == "tool_call" and not span.get("ok", True):
            color = SVG_COLORS["tool_call_error"]

        label = html.escape(str(span.get("label", "")))
        title_bits = [
            "{}: {}".format(k, v) for k, v in span.items()
            if k not in ("children", "args") and v is not None
        ]
        title = html.escape(" | ".join(title_bits))
        row_class = "wf-row wf-{}".format(span["type"])
        if span["type"] == "tool_call" and not span.get("ok", True):
            row_class += " wf-error"

        if span["type"] == "compaction":
            cx, cy = x, y + row_height / 2 - 2
            parts.append(
                '<g class="{}" data-turn="{}"><polygon points="{:.1f},{:.1f} {:.1f},{:.1f} {:.1f},{:.1f} {:.1f},{:.1f}" '
                'fill="{}"><title>{}</title></polygon></g>'.format(
                    row_class, turn_n, cx, cy - 5, cx + 5, cy, cx, cy + 5, cx - 5, cy, color, title
                )
            )
        else:
            parts.append('<g class="{}" data-turn="{}">'.format(row_class, turn_n))
            parts.append(
                '<rect x="{:.1f}" y="{}" width="{:.1f}" height="{}" rx="3" fill="{}"><title>{}</title></rect>'.format(
                    x, y, w, row_height - 4, color, title
                )
            )
            if w > 28:
                parts.append('<text x="{:.1f}" y="{}" class="wf-label">{}</text>'.format(x + 4, y + row_height - 8, label))
            parts.append("</g>")

    parts.append("</svg>")
    return "".join(parts)
