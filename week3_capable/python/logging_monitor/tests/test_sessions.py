import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_monitor import sessions  # noqa: E402


def write_jsonl(path, events):
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


class TestSessionParsing(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "s1.jsonl")

    def test_duration_ms_is_gap_since_previous_line_not_previous_rendered_entry(self):
        # Sub-second gaps only become meaningful once `at` is microsecond
        # precision (Design 1) -- assert the actual computed deltas, not
        # just "some number came back".
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {"phase": "turn", "n": 1, "at": "2026-08-05T10:00:00.100000-04:00"},
            {"phase": "tool_call", "name": "look", "args": {}, "at": "2026-08-05T10:00:00.150000-04:00"},
            {"phase": "tool_result", "name": "look", "result": "A room", "ok": True, "at": "2026-08-05T10:00:00.350000-04:00"},
        ]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        types_and_durations = [(e.type, e.duration_ms) for e in session.entries]
        self.assertEqual(types_and_durations, [("turn", 100.0), ("tool_call", 50.0), ("tool", 200.0)])

    def test_tool_call_and_tool_result_pair_positionally(self):
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {"phase": "tool_call", "name": "look", "args": {"x": 1}, "at": "2026-08-05T10:00:00.010000-04:00"},
            {"phase": "tool_result", "name": "look", "result": "ok", "ok": True, "at": "2026-08-05T10:00:00.020000-04:00"},
        ]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        tool_entry = [e for e in session.entries if e.type == "tool"][0]
        self.assertEqual(tool_entry.tool_name, "look")
        self.assertEqual(tool_entry.tool_args, {"x": 1})
        self.assertTrue(tool_entry.tool_ok)

    def test_failed_tool_result_is_flagged_not_ok(self):
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {"phase": "tool_call", "name": "shop", "args": {}, "at": "2026-08-05T10:00:00.010000-04:00"},
            {"phase": "tool_result", "name": "shop", "result": "ERROR: bad", "ok": False, "error": "bad", "at": "2026-08-05T10:00:00.020000-04:00"},
        ]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        tool_entry = [e for e in session.entries if e.type == "tool"][0]
        self.assertFalse(tool_entry.tool_ok)
        self.assertEqual(tool_entry.tool_error, "bad")

    def test_error_phase_is_rendered_with_full_detail(self):
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {
                "phase": "error", "where": "Agent._handle_tool_calls", "operation": "tool_dispatch:shop",
                "error_class": "ArgumentError", "error_message": "wrong number of arguments (given 1, expected 0)",
                "backtrace": ["line1", "line2"], "at": "2026-08-05T10:00:00.010000-04:00",
            },
        ]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        error_entry = [e for e in session.entries if e.type == "error"][0]
        self.assertEqual(error_entry.error_class, "ArgumentError")
        self.assertEqual(error_entry.backtrace, ["line1", "line2"])
        self.assertEqual(session.to_summary()["error_count"], 1)

    def test_token_totals_fall_back_to_nested_usage_dict(self):
        # logger.py's Logger.response only emits flattened input_tokens/
        # output_tokens when _execution_metadata has a task/backend to
        # attach -- always fall back to the nested `usage` dict, matching
        # log_viz/lib/log_viz/session.rb's `event["input_tokens"] ||
        # usage["input_tokens"]`.
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {"phase": "response", "text": "done", "usage": {"input_tokens": 10, "output_tokens": 5},
             "stop_reason": "end_turn", "at": "2026-08-05T10:00:00.010000-04:00"},
        ]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        summary = session.to_summary()
        self.assertEqual(summary["total_input_tokens"], 10)
        self.assertEqual(summary["total_output_tokens"], 5)

    def test_estimated_cost_sums_logger_emitted_cost_usd(self):
        # Matches log_viz/lib/log_viz/session.rb's Session#estimated_cost --
        # sums the logger-emitted per-response cost_usd rather than
        # recomputing rates locally.
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {"phase": "response", "text": "a", "usage": {"input_tokens": 10, "output_tokens": 5},
             "stop_reason": "end_turn", "cost_usd": 0.001, "at": "2026-08-05T10:00:00.010000-04:00"},
            {"phase": "response", "text": "b", "usage": {"input_tokens": 20, "output_tokens": 10},
             "stop_reason": "end_turn", "cost_usd": 0.002, "at": "2026-08-05T10:00:00.020000-04:00"},
        ]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        self.assertAlmostEqual(session.estimated_cost(), 0.003)
        self.assertAlmostEqual(session.to_summary()["cost_usd"], 0.003)

    def test_estimated_cost_is_none_when_no_response_carries_a_cost(self):
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {"phase": "response", "text": "a", "usage": {"input_tokens": 10, "output_tokens": 5},
             "stop_reason": "end_turn", "at": "2026-08-05T10:00:00.010000-04:00"},
        ]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        self.assertIsNone(session.estimated_cost())
        self.assertIsNone(session.to_summary()["cost_usd"])

    def test_first_task_is_the_first_user_turn_text(self):
        # The command/question that actually started the session -- shown
        # as a "Task" column on the session list and at the top of the
        # session detail page.
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {"phase": "turn", "n": 1, "at": "2026-08-05T10:00:00.005000-04:00"},
            {"phase": "prompt", "messages": [{"role": "user", "content": "where am i?"}],
             "tools": {}, "context_window": 1000, "at": "2026-08-05T10:00:00.010000-04:00"},
            {"phase": "response", "text": "You are in the Temple.", "usage": {}, "stop_reason": "end_turn",
             "at": "2026-08-05T10:00:00.020000-04:00"},
            {"phase": "turn", "n": 2, "at": "2026-08-05T10:00:00.030000-04:00"},
            {"phase": "prompt", "messages": [{"role": "user", "content": "goto the bakery"}],
             "tools": {}, "context_window": 1000, "at": "2026-08-05T10:00:00.040000-04:00"},
        ]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        self.assertEqual(session.first_task(), "where am i?")
        self.assertEqual(session.to_summary()["task"], "where am i?")

    def test_first_task_is_none_for_a_session_with_no_user_turn_yet(self):
        events = [{"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"}]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        self.assertIsNone(session.first_task())
        self.assertIsNone(session.to_summary()["task"])

    def test_final_response_skips_intermediate_tool_use_placeholders(self):
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {"phase": "response", "text": "(tool use — 1 call)", "usage": {}, "stop_reason": "tool_use",
             "at": "2026-08-05T10:00:00.010000-04:00"},
            {"phase": "response", "text": "All done.", "usage": {}, "stop_reason": "end_turn",
             "at": "2026-08-05T10:00:00.020000-04:00"},
        ]
        write_jsonl(self.path, events)
        session = sessions.Session.load(self.path)

        self.assertEqual(session.final_response(), "All done.")

    def test_incremental_parse_matches_full_parse(self):
        # sessions.py's SSE tail endpoint reuses ParseState/parse_event
        # incrementally across polls -- assert it produces the exact same
        # entries as a single full-file Session.parse() pass.
        events = [
            {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
            {"phase": "turn", "n": 1, "at": "2026-08-05T10:00:00.010000-04:00"},
            {"phase": "tool_call", "name": "look", "args": {}, "at": "2026-08-05T10:00:00.020000-04:00"},
            {"phase": "tool_result", "name": "look", "result": "ok", "ok": True, "at": "2026-08-05T10:00:00.030000-04:00"},
        ]
        write_jsonl(self.path, events)
        full = sessions.Session.load(self.path)

        state = sessions.ParseState()
        incremental = [sessions.parse_event(state, e) for e in events]
        incremental = [e for e in incremental if e is not None]

        self.assertEqual([e.type for e in full.entries], [e.type for e in incremental])
        self.assertEqual([e.duration_ms for e in full.entries], [e.duration_ms for e in incremental])


if __name__ == "__main__":
    unittest.main()
