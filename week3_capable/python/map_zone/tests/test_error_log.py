"""Unit tests for boukensha/error_log.py + Logger.error() -- verifies a
raised-and-caught exception ends up durably recorded, with full class/
message/backtrace, in both errors.jsonl (cross-session) and the per-session
JSONL (Logger.error's inline write) -- see docs/plans/capable/logging_monitor.md
Design 2.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boukensha  # noqa: E402
from boukensha import error_log  # noqa: E402
from boukensha.logger import Logger  # noqa: E402


class TestLogError(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_writes_class_message_and_nonempty_backtrace(self):
        try:
            raise ValueError("boom")
        except ValueError as e:
            error_log.log_error(e, where="test.site", operation="op1", task="task1", dir=self.tmpdir)

        path = os.path.join(self.tmpdir, error_log.ERROR_LOG_NAME)
        with open(path) as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 1)

        entry = json.loads(lines[0])
        self.assertEqual(entry["error_class"], "ValueError")
        self.assertEqual(entry["error_message"], "boom")
        self.assertEqual(entry["where"], "test.site")
        self.assertEqual(entry["operation"], "op1")
        self.assertEqual(entry["task"], "task1")
        self.assertGreater(len(entry["backtrace"]), 0)
        self.assertIn("T", entry["at"])  # ISO-8601 timestamp present

    def test_a_broken_error_logger_never_raises(self):
        # dir points at a location that cannot be created (a file, not a
        # directory, in its place) -- log_error must swallow the failure
        # rather than mask the original exception with a logging failure.
        blocked = os.path.join(self.tmpdir, "not_a_dir")
        open(blocked, "w").close()

        try:
            raise RuntimeError("original failure")
        except RuntimeError as e:
            try:
                error_log.log_error(e, where="test.site", dir=os.path.join(blocked, "nested"))
            except Exception as logging_exc:  # noqa: BLE001
                self.fail("log_error raised: {}".format(logging_exc))


class TestLoggerError(unittest.TestCase):
    # Logger.error() calls error_log.log_error without a dir= override, so
    # it falls back to boukensha.current_config().dir -- point that at an
    # isolated tmpdir via BOUKENSHA_DIR, or this test would write to (and
    # read from) the real ~/.boukensha.
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._prev_env = os.environ.get("BOUKENSHA_DIR")
        os.environ["BOUKENSHA_DIR"] = self.tmpdir
        boukensha._config = None

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("BOUKENSHA_DIR", None)
        else:
            os.environ["BOUKENSHA_DIR"] = self._prev_env
        boukensha._config = None

    def test_writes_to_both_errors_jsonl_and_the_session_log(self):
        logger = Logger(dir=self.tmpdir)
        try:
            raise ValueError("wrong number of arguments (given 1, expected 0)")
        except ValueError as e:
            logger.error(e, where="Agent._handle_tool_calls", operation="tool_dispatch:shop")
        logger.close()

        errors_path = os.path.join(self.tmpdir, error_log.ERROR_LOG_NAME)
        with open(errors_path) as f:
            error_entries = [json.loads(l) for l in f.read().splitlines()]
        self.assertEqual(len(error_entries), 1)
        self.assertEqual(error_entries[0]["session_id"], logger.session_id)
        self.assertEqual(error_entries[0]["operation"], "tool_dispatch:shop")

        with open(logger.path) as f:
            session_entries = [json.loads(l) for l in f.read().splitlines()]
        error_phase_entries = [e for e in session_entries if e["phase"] == "error"]
        self.assertEqual(len(error_phase_entries), 1)
        self.assertEqual(error_phase_entries[0]["error_class"], "ValueError")
        self.assertGreater(len(error_phase_entries[0]["backtrace"]), 0)


if __name__ == "__main__":
    unittest.main()
