import os

from .backends.anthropic import Anthropic
from .backends.base import Base as BackendBase
from .backends.gemini import Gemini
from .backends.ollama import Ollama
from .backends.ollama_cloud import OllamaCloud
from .backends.openai import OpenAI
from .client import Client
from .config import PROMPTS_DIR, Config
from .context import Context
from .errors import ApiError, LoopError, UnknownToolError, UnsupportedModelError
from .message import Message
from . import models
from .prompt_builder import PromptBuilder
from .registry import Registry
from .tasks.player import Player
from .tool import Tool
from .version import VERSION

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
from .run_dsl import RunDSL  # noqa: E402
from .repl import Repl  # noqa: E402
from .tui import Tui  # noqa: E402
from .tools import mcp as tools_mcp  # noqa: E402


_API_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama_cloud": "OLLAMA_API_KEY",
}


def _register_mcp_servers(registry, cfg):
    """Register every server in settings.yaml's `mcp_servers:` block. This is
    the agent's ONLY source of tools -- boukensha ships none of its own.
    Nothing here knows what any particular server does; a MUD daemon and a
    filesystem server are registered by the identical code path.

    A server marked required=False that fails to spawn is a warning, not a
    fatal error -- the agent runs without its tools. A name collision is
    never excused that way: it means the config asks for two tools with one
    name, and answering by dropping one of them silently is the worst option
    available.

    Returns {server_name: tool_count} for the servers that came up.
    """
    summary = {}
    for name, entry in cfg.mcp_servers().items():
        try:
            before = set(registry.tool_names())
            tools_mcp.register(
                registry, command=entry["command"], args=entry["args"],
                env=entry["env"], prefix=entry["prefix"], tools=entry["tools"],
            )
            # The count of tools *this server* actually registered -- not
            # the server's raw advertised count (client.tools), which
            # diverges from what's usable the moment a tools: filter in
            # settings.yaml narrows the set.
            summary[name] = len(set(registry.tool_names()) - before)
        except tools_mcp.CollisionError:
            raise
        except Exception as e:
            from . import error_log
            error_log.log_error(e, where="_register_mcp_servers", operation="mcp_server_startup:{}".format(name))
            if entry["required"]:
                raise RuntimeError("boukensha: MCP server '{}' failed to start: {}".format(name, e)) from e
            print(
                "[boukensha] optional MCP server '{}' failed to start: {} — continuing without its tools".format(
                    name, e
                )
            )
    return summary


def run(
    *,
    task,
    system=None,
    model=None,
    backend=None,
    api_key=None,
    ollama_host="http://localhost:11434",
    log=None,
    context_window=None,
    max_output_tokens=None,
    working_dir=None,
    register_tools=None,
):
    """The top-level entry point. Wires together every primitive so the
    caller only has to describe *what* to do, not *how* to plumb it.

    The agent ships with NO tools of its own. Every tool it can call arrives
    over an MCP connection, declared in settings.yaml's `mcp_servers:` block
    (see Config.mcp_servers). Want file access? Point at a filesystem MCP
    server. Want to play a MUD? Point at `mud-manager --mcp`. Boukensha is
    the host; the servers own the tools.

    working_dir: recorded on the Context as the agent's notion of "where it
    is". It registers nothing -- an MCP server that touches the filesystem
    is rooted by its own spawn args.
    """
    cfg = current_config()  # loads .env; populates os.environ
    task_class = Player
    task_settings = cfg.tasks(task_class.task_name())
    if system is None:
        system = task_class.system_prompt(
            task_settings,
            user_prompts_dir=cfg.user_prompts_dir,
            default_prompts_dir=PROMPTS_DIR,
        )
    if model is None:
        model = task_class.model(task_settings)
    if backend is None:
        backend = task_class.provider(task_settings)
    if context_window is None:
        context_window = models.context_window(model)
    if api_key is None:
        env_var = _API_KEY_ENV_VARS.get(backend)
        api_key = os.environ.get(env_var) if env_var else None

    ctx = Context(
        system=system, context_window=context_window, working_dir=working_dir or os.getcwd(),
        compaction_threshold=cfg.agent_compaction_threshold(),
    )
    registry = Registry(ctx)

    _register_mcp_servers(registry, cfg)

    if register_tools is not None:
        register_tools(RunDSL(registry))

    if backend == "anthropic":
        be = Anthropic(api_key=api_key, model=model)
    elif backend == "openai":
        be = OpenAI(api_key=api_key, model=model)
    elif backend == "gemini":
        be = Gemini(api_key=api_key, model=model)
    elif backend == "ollama":
        be = Ollama(host=ollama_host, model=model)
    elif backend == "ollama_cloud":
        be = OllamaCloud(api_key=api_key, model=model)
    else:
        raise ValueError(
            "Unknown backend {!r}. Use \"anthropic\", \"openai\", \"gemini\", \"ollama\", "
            "or \"ollama_cloud\".".format(backend)
        )

    builder = PromptBuilder(ctx, be)
    client = Client(builder)
    effective_max_output_tokens = max_output_tokens if max_output_tokens is not None else cfg.agent_max_output_tokens()
    logger = None
    try:
        logger = Logger(log=log, snapshot={
            "max_iterations": cfg.agent_max_iterations(),
            "max_turn_tokens": cfg.agent_max_turn_tokens(),
            "max_output_tokens": effective_max_output_tokens,
            "context_window": context_window,
            "model": model,
            "provider": backend,
        })
        agent = Agent(
            context=ctx,
            registry=registry,
            builder=builder,
            client=client,
            logger=logger,
            max_iterations=cfg.agent_max_iterations(),
            max_turn_tokens=cfg.agent_max_turn_tokens(),
            max_output_tokens=effective_max_output_tokens,
        )

        ctx.add_message("user", task)
        return agent.run()
    finally:
        if logger is not None:
            logger.close()


def start_repl(
    *,
    system=None,
    model=None,
    backend=None,
    api_key=None,
    ollama_host="http://localhost:11434",
    log=None,
    context_window=None,
    max_output_tokens=None,
    working_dir=None,
    register_tools=None,
    tui=True,
):
    """Interactive REPL -- see `run` for full option documentation.

    tui: True (default) wraps the REPL in a Textual TUI. Pass tui=False or
    use the --no-tui CLI flag to fall back to the plain terminal REPL.
    """
    logger = None
    try:
        cfg = current_config()  # loads .env; populates os.environ
        task_class = Player
        task_settings = cfg.tasks(task_class.task_name())
        if system is None:
            system = task_class.system_prompt(
                task_settings,
                user_prompts_dir=cfg.user_prompts_dir,
                default_prompts_dir=PROMPTS_DIR,
            )
        if model is None:
            model = task_class.model(task_settings)
        if backend is None:
            backend = task_class.provider(task_settings)
        if context_window is None:
            context_window = models.context_window(model)
        if api_key is None:
            env_var = _API_KEY_ENV_VARS.get(backend)
            api_key = os.environ.get(env_var) if env_var else None

        ctx = Context(
            system=system, context_window=context_window, working_dir=working_dir or os.getcwd(),
            compaction_threshold=cfg.agent_compaction_threshold(),
        )
        registry = Registry(ctx)

        servers = _register_mcp_servers(registry, cfg)

        if register_tools is not None:
            register_tools(RunDSL(registry))

        if backend == "anthropic":
            be = Anthropic(api_key=api_key, model=model)
        elif backend == "openai":
            be = OpenAI(api_key=api_key, model=model)
        elif backend == "gemini":
            be = Gemini(api_key=api_key, model=model)
        elif backend == "ollama":
            be = Ollama(host=ollama_host, model=model)
        elif backend == "ollama_cloud":
            be = OllamaCloud(api_key=api_key, model=model)
        else:
            raise ValueError(
                "Unknown backend {!r}. Use \"anthropic\", \"openai\", \"gemini\", \"ollama\", "
                "or \"ollama_cloud\".".format(backend)
            )

        builder = PromptBuilder(ctx, be)
        client = Client(builder)
        effective_max_output_tokens = (
            max_output_tokens if max_output_tokens is not None else cfg.agent_max_output_tokens()
        )
        logger = Logger(log=log, snapshot={
            "max_iterations": cfg.agent_max_iterations(),
            "max_turn_tokens": cfg.agent_max_turn_tokens(),
            "max_output_tokens": effective_max_output_tokens,
            "context_window": context_window,
            "model": model,
            "provider": backend,
        })

        repl = Repl(
            context=ctx,
            registry=registry,
            builder=builder,
            client=client,
            logger=logger,
            max_iterations=cfg.agent_max_iterations(),
            max_turn_tokens=cfg.agent_max_turn_tokens(),
            max_output_tokens=effective_max_output_tokens,
            config_dir=cfg.dir,
            provider=backend,
            model=model,
            version=VERSION,
            api_key=api_key,
            servers=servers,
        )

        if tui:
            Tui(repl).run()
        else:
            repl.start()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if logger is not None:
            logger.close()


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
    "LoopError",
    "PromptBuilder",
    "Client",
    "Agent",
    "Logger",
    "RunDSL",
    "Repl",
    "Tui",
    "VERSION",
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
    "run",
    "start_repl",
]
