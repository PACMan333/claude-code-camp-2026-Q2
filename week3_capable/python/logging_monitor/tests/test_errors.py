import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_monitor import errors  # noqa: E402


class TestErrors(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_missing_file_returns_empty_list_not_an_error(self):
        # No error has ever been logged for this BOUKENSHA_DIR -- errors.jsonl
        # doesn't exist yet. That's the common case, not a failure.
        self.assertEqual(errors.load_errors(self.tmpdir), [])

    def test_entries_come_back_newest_first(self):
        path = errors.errors_path(self.tmpdir)
        entries = [
            {"at": "2026-08-05T10:00:00.000000-04:00", "error_class": "First"},
            {"at": "2026-08-05T10:00:01.000000-04:00", "error_class": "Second"},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        loaded = errors.load_errors(self.tmpdir)
        self.assertEqual([e["error_class"] for e in loaded], ["Second", "First"])

    def test_malformed_line_is_skipped_not_fatal(self):
        path = errors.errors_path(self.tmpdir)
        with open(path, "w") as f:
            f.write("not json\n")
            f.write(json.dumps({"error_class": "Real", "at": "x"}) + "\n")

        loaded = errors.load_errors(self.tmpdir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["error_class"], "Real")

    def test_load_errors_tags_entries_as_boukensha_source(self):
        path = errors.errors_path(self.tmpdir)
        with open(path, "w") as f:
            f.write(json.dumps({"error_class": "ValueError", "at": "2026-08-05T10:00:00.000000-04:00"}) + "\n")

        loaded = errors.load_errors(self.tmpdir)
        self.assertEqual(loaded[0]["source"], "boukensha")


class TestLoadAll(unittest.TestCase):
    """load_all merges boukensha's errors.jsonl with mud_manager's genuine
    exceptions -- a bug is a bug regardless of which side of the MCP
    boundary it happened on (see mud_manager.jsonl's real-world motivating
    case: a `bank`/`move` ArgumentError only ever showed up on /mud, never
    on /errors, even though it's exactly the class of failure this page
    exists for).
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def write_boukensha_error(self, at, error_class):
        with open(errors.errors_path(self.tmpdir), "a") as f:
            f.write(json.dumps({
                "at": at, "where": "Agent._handle_tool_calls", "operation": None, "task": None,
                "session_id": "s1", "error_class": error_class, "error_message": "boom", "backtrace": ["l1"],
            }) + "\n")

    def write_mud_manager_entry(self, at, **kwargs):
        from logging_monitor import mud_log
        with open(mud_log.mud_log_path(self.tmpdir), "a") as f:
            f.write(json.dumps({"at": at, **kwargs}) + "\n")

    def test_a_normal_ok_command_is_never_treated_as_an_error(self):
        self.write_mud_manager_entry("2026-08-05T10:00:00.000000-04:00", tool="look", verb="look",
                                      response="A room", duration_ms=1.2)
        self.assertEqual(errors.load_all(self.tmpdir), [])

    def test_a_mud_manager_argument_error_shows_up_merged_in(self):
        self.write_mud_manager_entry("2026-08-05T10:00:00.000000-04:00", tool="bank",
                                      error_class="ArgumentError", error_message="invalid value for Integer()",
                                      backtrace=["l1", "l2"])
        merged = errors.load_all(self.tmpdir)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "mud_manager")
        self.assertEqual(merged[0]["operation"], "bank")
        self.assertEqual(merged[0]["error_class"], "ArgumentError")

    def test_a_fatal_run_level_crash_is_labeled_differently_than_call_tool(self):
        self.write_mud_manager_entry("2026-08-05T10:00:00.000000-04:00", fatal=True,
                                      error_class="NoMethodError", error_message="undefined method")
        merged = errors.load_all(self.tmpdir)
        self.assertEqual(merged[0]["where"], "mud_manager.run")

    def test_both_sources_merge_sorted_newest_first(self):
        self.write_boukensha_error("2026-08-05T10:00:00.000000-04:00", "ValueError")
        self.write_mud_manager_entry("2026-08-05T10:00:05.000000-04:00", tool="move",
                                      error_class="ArgumentError", error_message="bad direction")
        self.write_boukensha_error("2026-08-05T10:00:10.000000-04:00", "ApiError")

        merged = errors.load_all(self.tmpdir)
        self.assertEqual([e["error_class"] for e in merged], ["ApiError", "ArgumentError", "ValueError"])
        self.assertEqual([e["source"] for e in merged], ["boukensha", "mud_manager", "boukensha"])


if __name__ == "__main__":
    unittest.main()
