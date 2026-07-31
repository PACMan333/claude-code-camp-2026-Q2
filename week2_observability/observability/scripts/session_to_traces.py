#!/usr/bin/env python3
"""Convert one Boukensha .boukensha/sessions/*.jsonl session log into a
trace and ship it to the OTel Collector's OTLP/HTTP endpoint.

This is a standalone, on-demand companion to the filelog-based logs
pipeline (otel-collector-config.yaml) — it does NOT touch any of the
per-step Boukensha logger.rb/logger.py copies. It reads the same JSONL
files log_viz reads, after the fact, and reconstructs an approximate
trace: session -> turn -> iteration -> tool_call spans, with prompt/plan/
response events attached to the enclosing span. Span start/end times come
from consecutive log line timestamps, which only have second precision
and mark when an event was *logged*, not real span boundaries — this is
a best-effort reconstruction for browsing session shape in Tempo, not a
substitute for real live instrumentation.

Usage:
  python3 session_to_traces.py [path/to/session.jsonl] [--collector URL]

With no path, converts the most recently modified session in
.boukensha/sessions/ (repo root, three levels up from this script).

Stdlib only — no pip install required.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_SESSIONS_DIR = os.path.join(REPO_ROOT, ".boukensha", "sessions")
DEFAULT_COLLECTOR = "http://localhost:4318"

SPAN_KIND_INTERNAL = 1
STATUS_CODE_ERROR = 2


def to_unix_nanos(at: str) -> int:
    dt = datetime.fromisoformat(at)
    return int(dt.timestamp() * 1_000_000_000)


def attr(key, value):
    if isinstance(value, bool):
        v = {"boolValue": value}
    elif isinstance(value, int):
        v = {"intValue": str(value)}
    elif isinstance(value, float):
        v = {"doubleValue": value}
    else:
        v = {"stringValue": "" if value is None else str(value)}
    return {"key": key, "value": v}


class Span:
    def __init__(self, name, start_ns, parent_id=None):
        self.span_id = secrets.token_hex(8)
        self.parent_id = parent_id
        self.name = name
        self.start_ns = start_ns
        self.end_ns = start_ns
        self.attributes = {}
        self.events = []
        self.status_error = False

    def close(self, end_ns):
        self.end_ns = max(end_ns, self.start_ns + 1_000_000)  # min 1ms, source is second-precision

    def add_event(self, name, at_ns, attributes):
        self.events.append({
            "timeUnixNano": str(at_ns),
            "name": name,
            "attributes": [attr(k, v) for k, v in attributes.items() if v is not None],
        })

    def to_otlp(self, trace_id):
        span = {
            "traceId": trace_id,
            "spanId": self.span_id,
            "name": self.name,
            "kind": SPAN_KIND_INTERNAL,
            "startTimeUnixNano": str(self.start_ns),
            "endTimeUnixNano": str(self.end_ns),
            "attributes": [attr(k, v) for k, v in self.attributes.items() if v is not None],
            "events": self.events,
        }
        if self.parent_id:
            span["parentSpanId"] = self.parent_id
        if self.status_error:
            span["status"] = {"code": STATUS_CODE_ERROR}
        return span


def build_spans(lines: list[dict]) -> tuple[str, list[Span]]:
    trace_id = secrets.token_hex(16)
    spans: list[Span] = []
    session_id = lines[0].get("session_id", "unknown-session")

    session_span = None
    turn_span = None
    iteration_span = None
    pending_tool_calls: list[Span] = []
    last_ts = None

    def current_parent():
        return iteration_span or turn_span or session_span

    for entry in lines:
        phase = entry.get("phase")
        ts = to_unix_nanos(entry["at"])
        last_ts = ts

        if phase == "session_start":
            session_span = Span("session", ts)
            session_span.attributes.update({
                "session_id": session_id,
                "model": entry.get("model"),
                "provider": entry.get("provider"),
                "max_iterations": entry.get("max_iterations"),
                "context_window": entry.get("context_window"),
            })
            spans.append(session_span)

        elif phase == "turn":
            if turn_span:
                turn_span.close(ts)
            turn_span = Span(f"turn {entry.get('n')}", ts, parent_id=(session_span.span_id if session_span else None))
            spans.append(turn_span)
            iteration_span = None

        elif phase == "iteration":
            if iteration_span:
                iteration_span.close(ts)
            parent = turn_span or session_span
            iteration_span = Span(f"iteration {entry.get('n')}", ts, parent_id=(parent.span_id if parent else None))
            iteration_span.attributes["max_iterations"] = entry.get("max")
            spans.append(iteration_span)

        elif phase == "tool_call":
            parent = current_parent()
            tool_span = Span(f"tool_call {entry.get('name')}", ts, parent_id=(parent.span_id if parent else None))
            tool_span.attributes["tool.name"] = entry.get("name")
            tool_span.attributes["tool.args"] = json.dumps(entry.get("args"))[:2000]
            spans.append(tool_span)
            pending_tool_calls.append(tool_span)

        elif phase == "tool_result":
            tool_span = pending_tool_calls.pop(0) if pending_tool_calls else None
            if tool_span:
                tool_span.close(ts)
                ok = entry.get("ok", True)
                tool_span.attributes["tool.ok"] = ok
                tool_span.attributes["tool.error"] = entry.get("error")
                if not ok:
                    tool_span.status_error = True
            elif current_parent():
                current_parent().add_event("tool_result", ts, {
                    "name": entry.get("name"), "ok": entry.get("ok"), "error": entry.get("error"),
                })

        elif phase in ("plan", "prompt", "reasoning", "compaction", "limit_reached"):
            parent = current_parent()
            if parent:
                fields = {k: v for k, v in entry.items() if k not in ("phase", "session_id", "at")}
                parent.add_event(phase, ts, fields)

        elif phase == "response":
            parent = current_parent()
            if parent:
                parent.add_event("response", ts, {
                    "task": entry.get("task"),
                    "provider": entry.get("provider"),
                    "model": entry.get("model"),
                    "cost_usd": entry.get("cost_usd"),
                    "input_tokens": entry.get("input_tokens"),
                    "output_tokens": entry.get("output_tokens"),
                    "stop_reason": entry.get("stop_reason"),
                })

        elif phase == "turn_end":
            if iteration_span:
                iteration_span.close(ts)
                iteration_span = None
            if turn_span:
                turn_span.attributes.update({
                    "reason": entry.get("reason"),
                    "iterations": entry.get("iterations"),
                    "tokens": entry.get("tokens"),
                })
                turn_span.close(ts)
                turn_span = None

    for span in (iteration_span, turn_span):
        if span:
            span.close(last_ts)
    if session_span:
        session_span.close(last_ts)

    return trace_id, spans


def export(trace_id: str, spans: list[Span], session_id: str, collector: str) -> None:
    resource_spans = [{
        "resource": {
            "attributes": [attr("service.name", "boukensha"), attr("session_id", session_id)],
        },
        "scopeSpans": [{
            "scope": {"name": "session_to_traces.py"},
            "spans": [s.to_otlp(trace_id) for s in spans],
        }],
    }]
    body = json.dumps({"resourceSpans": resource_spans}).encode("utf-8")
    req = urllib.request.Request(
        f"{collector.rstrip('/')}/v1/traces",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"OTLP export failed: HTTP {resp.status}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_file", nargs="?", help="Path to a .boukensha/sessions/*.jsonl file")
    parser.add_argument("--collector", default=DEFAULT_COLLECTOR, help=f"OTLP/HTTP base URL (default: {DEFAULT_COLLECTOR})")
    args = parser.parse_args()

    path = args.session_file
    if not path:
        candidates = sorted(glob.glob(os.path.join(DEFAULT_SESSIONS_DIR, "*.jsonl")), key=os.path.getmtime)
        if not candidates:
            sys.exit(f"No session files found in {DEFAULT_SESSIONS_DIR}")
        path = candidates[-1]

    with open(path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    if not lines:
        sys.exit(f"{path}: empty session file")

    trace_id, spans = build_spans(lines)
    session_id = lines[0].get("session_id", "unknown-session")

    try:
        export(trace_id, spans, session_id, args.collector)
    except (urllib.error.URLError, RuntimeError) as e:
        sys.exit(f"Failed to export to {args.collector}: {e}")

    print(f"Exported {len(spans)} spans for session {session_id} (trace {trace_id}) to {args.collector}")
    print(f"View in Grafana (Tempo datasource): search by traceID {trace_id}")


if __name__ == "__main__":
    main()
