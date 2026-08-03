"""Static model -> capability table.

context_window is a known *model* fact -- the physical input ceiling -- not a
value the user sets. The agent looks it up from its configured model id; the
user never configures it in settings.yaml. Unknown models fall back to a
conservative default so an unrecognised id can't silently assume a huge
window.

Built from every backend's own MODELS constant rather than hand-maintained
separately, so a model added to a backend is automatically sized correctly
here too. Unlike Ruby's Models.table (a lazily memoized ||=, deliberately
avoiding a require-order hazard), this module builds its table once at
import time: __init__.py already imports every backend module, in order,
before anything in this package could call context_window(), so there is no
equivalent ordering hazard to guard against here.
"""
from .backends.anthropic import Anthropic
from .backends.gemini import Gemini
from .backends.ollama import Ollama
from .backends.ollama_cloud import OllamaCloud
from .backends.openai import OpenAI

DEFAULT_CONTEXT_WINDOW = 32_000

_BACKEND_CLASSES = [Anthropic, OpenAI, Gemini, Ollama, OllamaCloud]


def _build_table():
    table = {}
    for backend in _BACKEND_CLASSES:
        table.update(backend.MODELS)
    return table


_TABLE = _build_table()


def context_window(model) -> int:
    return _TABLE.get(str(model), {}).get("context_window", DEFAULT_CONTEXT_WINDOW)
