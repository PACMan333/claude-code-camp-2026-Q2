"""Reads the durable, cross-session <BOUKENSHA_DIR>/errors.jsonl (see
boukensha/error_log.py and lib/boukensha/error_log.rb) into rows for the
top-level Errors page.
"""
import json
import os

from . import mud_log

ERROR_LOG_NAME = "errors.jsonl"


def errors_path(boukensha_dir):
    return os.path.join(boukensha_dir, ERROR_LOG_NAME)


def load_errors(boukensha_dir):
    """Returns every entry in errors.jsonl, newest first. Missing file (no
    error has ever been logged) is not an error -- an empty list."""
    path = errors_path(boukensha_dir)
    if not os.path.exists(path):
        return []

    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    entries.reverse()
    for entry in entries:
        entry.setdefault("source", "boukensha")
    return entries


def load_all(boukensha_dir):
    """Errors from both durable logs -- boukensha's own errors.jsonl (MCP
    startup failures, tool-dispatch exceptions, REPL/TUI loop errors) and
    mud_manager's raw command log's genuine exceptions (bad arity, session
    errors) -- merged and sorted newest-first, so a real bug shows up here
    regardless of which side of the MCP boundary it happened on. The two
    logs stay physically separate (mud_manager has no dependency on
    boukensha, see lib/mud_manager/jsonl_log.rb's own docstring); this is
    a read-time merge, not a shared write path.
    """
    merged = load_errors(boukensha_dir) + mud_log.load_error_entries(boukensha_dir)
    merged.sort(key=lambda e: e.get("at") or "", reverse=True)
    return merged
