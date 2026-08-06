import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_monitor import spans  # noqa: E402


MULTI_TURN_EVENTS = [
    {"phase": "session_start", "at": "2026-08-05T10:00:00.000000-04:00"},
    # Turn 1, iteration 1: api_call, then a failed tool_call linked to an error event.
    {"phase": "turn", "n": 1, "at": "2026-08-05T10:00:00.010000-04:00"},
    {"phase": "iteration", "n": 1, "at": "2026-08-05T10:00:00.020000-04:00"},
    {"phase": "prompt", "at": "2026-08-05T10:00:00.030000-04:00"},
    {"phase": "response", "usage": {"input_tokens": 1, "output_tokens": 1}, "stop_reason": "tool_use",
     "at": "2026-08-05T10:00:00.530000-04:00"},
    {"phase": "tool_call", "name": "shop", "args": {"op": "list"}, "at": "2026-08-05T10:00:00.540000-04:00"},
    {"phase": "tool_result", "name": "shop", "ok": False, "error": "bad", "at": "2026-08-05T10:00:00.640000-04:00"},
    {"phase": "error", "where": "Agent._handle_tool_calls", "operation": "tool_dispatch:shop",
     "error_class": "ArgumentError", "error_message": "bad", "backtrace": ["l1"],
     "at": "2026-08-05T10:00:00.645000-04:00"},
    # Turn 1, iteration 2: a compaction marker then a clean api_call ending the turn.
    {"phase": "iteration", "n": 2, "at": "2026-08-05T10:00:00.650000-04:00"},
    {"phase": "compaction", "before": 40, "dropped": 16, "at": "2026-08-05T10:00:00.655000-04:00"},
    {"phase": "prompt", "at": "2026-08-05T10:00:00.660000-04:00"},
    {"phase": "response", "usage": {"input_tokens": 2, "output_tokens": 2}, "stop_reason": "end_turn",
     "at": "2026-08-05T10:00:01.160000-04:00"},
    {"phase": "turn_end", "reason": "completed", "iterations": 2, "tokens": 6, "at": "2026-08-05T10:00:01.170000-04:00"},
]


class TestBuildSpans(unittest.TestCase):
    def setUp(self):
        self.result = spans.build_spans(MULTI_TURN_EVENTS)

    def test_one_top_level_turn_span(self):
        self.assertEqual(len(self.result["turns"]), 1)
        turn = self.result["turns"][0]
        self.assertEqual(turn["type"], "turn")
        self.assertEqual(turn["n"], 1)
        self.assertEqual(turn["reason"], "completed")

    def test_turn_nests_two_iterations_in_order(self):
        turn = self.result["turns"][0]
        self.assertEqual([c["type"] for c in turn["children"]], ["iteration", "iteration"])
        self.assertEqual([c["n"] for c in turn["children"]], [1, 2])

    def test_iteration_one_nests_api_call_then_failed_tool_call(self):
        iteration_1 = self.result["turns"][0]["children"][0]
        self.assertEqual([c["type"] for c in iteration_1["children"]], ["api_call", "tool_call"])

    def test_failed_tool_call_is_flagged_and_linked_to_its_error_event(self):
        tool_call = self.result["turns"][0]["children"][0]["children"][1]
        self.assertEqual(tool_call["type"], "tool_call")
        self.assertFalse(tool_call["ok"])
        self.assertEqual(tool_call["error_class"], "ArgumentError")
        self.assertEqual(tool_call["error_message"], "bad")
        self.assertEqual(tool_call["backtrace"], ["l1"])

    def test_successful_api_call_has_no_error_fields(self):
        api_call = self.result["turns"][0]["children"][0]["children"][0]
        self.assertTrue(api_call["ok"])
        self.assertNotIn("error_class", api_call)

    def test_iteration_two_nests_compaction_marker_then_api_call(self):
        iteration_2 = self.result["turns"][0]["children"][1]
        self.assertEqual([c["type"] for c in iteration_2["children"]], ["compaction", "api_call"])
        compaction = iteration_2["children"][0]
        self.assertEqual(compaction["duration_ms"], 0.0)
        self.assertEqual(compaction["dropped"], 16)

    def test_durations_match_hand_computed_deltas(self):
        turn = self.result["turns"][0]
        # turn: 10ms offset -> 1170ms offset = 1160ms duration.
        self.assertAlmostEqual(turn["start_offset_ms"], 10.0)
        self.assertAlmostEqual(turn["duration_ms"], 1160.0)

        api_call_1 = turn["children"][0]["children"][0]
        # prompt at 30ms, response (closing it) at 530ms.
        self.assertAlmostEqual(api_call_1["start_offset_ms"], 30.0)
        self.assertAlmostEqual(api_call_1["duration_ms"], 500.0)

        tool_call = turn["children"][0]["children"][1]
        # tool_call at 540ms, tool_result (closing it) at 640ms.
        self.assertAlmostEqual(tool_call["start_offset_ms"], 540.0)
        self.assertAlmostEqual(tool_call["duration_ms"], 100.0)

    def test_offsets_are_relative_to_session_start_not_epoch(self):
        turn = self.result["turns"][0]
        self.assertEqual(self.result["session_start_us"], spans._to_us("2026-08-05T10:00:00.000000-04:00"))
        self.assertLess(turn["start_offset_ms"], 20)  # a few ms, not an epoch-scale number


class TestRenderSvg(unittest.TestCase):
    def test_empty_session_renders_a_placeholder_not_an_exception(self):
        svg = spans.render_svg({"turns": []})
        self.assertIn("<svg", svg)
        self.assertIn("No turns recorded", svg)

    def test_failed_tool_call_gets_the_error_color(self):
        result = spans.build_spans(MULTI_TURN_EVENTS)
        svg = spans.render_svg(result)
        self.assertIn(spans.SVG_COLORS["tool_call_error"], svg)
        self.assertIn('class="wf-row wf-tool_call wf-error"', svg)


if __name__ == "__main__":
    unittest.main()
