import json
import traceback
from datetime import datetime
from pathlib import Path

ERROR_LOG_NAME = "errors.jsonl"


def _iso_now_us() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def log_error(exc, *, where, operation=None, task=None, session_id=None, dir=None):
    """Appends one durable, structured entry for `exc` to
    <dir or current_config().dir>/errors.jsonl. Never raises -- a broken
    error logger must not mask the original failure.
    """
    import boukensha  # local import: avoids a hard circular dependency at module load time

    entry = {
        "at": _iso_now_us(),
        "where": where,
        "operation": operation,
        "task": task,
        "session_id": session_id,
        "error_class": type(exc).__name__,
        "error_message": str(exc),
        "backtrace": traceback.format_exception(type(exc), exc, exc.__traceback__),
    }
    try:
        root = Path(dir or boukensha.current_config().dir)
        root.mkdir(parents=True, exist_ok=True)
        with open(root / ERROR_LOG_NAME, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # logging a failure must never itself raise
