"""Reads mud_manager's raw command log (<MUD_MANAGER_LOG_DIR>/mud_manager.jsonl,
see lib/mud_manager/jsonl_log.rb) into rows for the /mud page.
"""
import json
import os

MUD_LOG_NAME = "mud_manager.jsonl"


def mud_log_path(boukensha_dir):
    return os.path.join(boukensha_dir, MUD_LOG_NAME)


def load_entries(boukensha_dir):
    """Returns every entry in mud_manager.jsonl, newest first. Missing file
    (mud-manager never started, or MUD_MANAGER_LOG_DIR points elsewhere) is
    not an error -- an empty list."""
    path = mud_log_path(boukensha_dir)
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
    return entries


def load_error_entries(boukensha_dir):
    """Returns mud_manager.jsonl entries that are genuine code-level
    exceptions (bin/mud-manager's call_tool rescues, or the blanket rescue
    in run) -- never the routine `is_error: true` MUD responses a command
    like `move` returns for an ordinary game-logic rejection (e.g. "you
    can't go that way"), since those aren't exceptions at all and carry no
    `error_class`. Normalized into the same shape errors.py's entries use
    (every key present, even if None) so errors.html can render both
    sources through one template without a Jinja Undefined-vs-None bug --
    see mud.html's own fix for the same class of issue.
    """
    normalized = []
    for e in load_entries(boukensha_dir):
        if not e.get("error_class"):
            continue
        normalized.append({
            "at": e.get("at"),
            "source": "mud_manager",
            "where": "mud_manager.call_tool" if not e.get("fatal") else "mud_manager.run",
            "operation": e.get("tool"),
            "task": None,
            "session_id": None,
            "error_class": e.get("error_class"),
            "error_message": e.get("error_message"),
            "backtrace": e.get("backtrace"),
        })
    return normalized
