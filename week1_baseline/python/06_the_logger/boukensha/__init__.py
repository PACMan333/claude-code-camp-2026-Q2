from .backends.anthropic import Anthropic
from .backends.base import Base as BackendBase
from .backends.gemini import Gemini
from .backends.ollama import Ollama
from .backends.ollama_cloud import OllamaCloud
from .backends.openai import OpenAI
from .client import Client
from .config import Config
from .context import Context
from .errors import ApiError, UnknownToolError, UnsupportedModelError
from .message import Message
from .prompt_builder import PromptBuilder
from .registry import Registry
from .tasks.player import Player
from .tool import Tool

_quiet = False
_debug = False
_config = None


def current_config():
    global _config
    if _config is None:
        _config = Config()
    return _config


def quiet() -> None:
    global _quiet
    _quiet = True


def loud() -> None:
    global _quiet
    _quiet = False


def is_quiet() -> bool:
    return _quiet


def debug() -> None:
    global _debug
    _debug = True


def is_debug() -> bool:
    return _debug


from .agent import Agent  # noqa: E402
from .logger import Logger  # noqa: E402

__all__ = [
    "Config",
    "Player",
    "Tool",
    "Message",
    "Context",
    "Registry",
    "UnknownToolError",
    "UnsupportedModelError",
    "ApiError",
    "PromptBuilder",
    "Client",
    "Agent",
    "Logger",
    "BackendBase",
    "Anthropic",
    "Ollama",
    "OllamaCloud",
    "OpenAI",
    "Gemini",
    "current_config",
    "quiet",
    "loud",
    "is_quiet",
    "debug",
    "is_debug",
]
