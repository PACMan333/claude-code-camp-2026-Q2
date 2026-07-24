from pathlib import Path

import boukensha
from .agent import Agent
from .errors import ApiError, LoopError


class Repl:
    """The interactive session loop.

    It wraps the same primitives as a single boukensha.run call, but instead
    of running once it stays alive: it reads a task from the user, runs the
    agent, prints the reply, and loops back to the prompt.

    The Context is shared across every turn so conversation history
    accumulates naturally -- the agent sees the full transcript each time it
    is called.

    Built-in commands (not sent to the agent):
      /help    print the command list
      /quiet   suppress detailed logging
      /loud    re-enable logging
      /clear   wipe conversation history (tools stay registered)
      /exit    leave the REPL
      /quit    alias for /exit
    """

    PROMPT = "boukensha> "

    HELP = (
        "Commands:\n"
        "  /quiet   suppress logging output\n"
        "  /loud    re-enable logging output\n"
        "  /clear   wipe conversation history (tools stay)\n"
        "  /exit    leave the REPL\n"
        "  /help    show this message"
    )

    def __init__(
        self,
        *,
        context,
        registry,
        builder,
        client,
        logger,
        config_dir=None,
        provider=None,
        model=None,
        version=None,
        api_key=None,
        servers=None,
        task_settings=None,
        max_iterations=None,
        max_output_tokens=None,
    ) -> None:
        self._context = context
        self._registry = registry
        self._builder = builder
        self._client = client
        self._logger = logger
        self._task_settings = task_settings
        self._max_iterations = max_iterations
        self._max_output_tokens = max_output_tokens
        self._config_dir = config_dir
        self._provider = provider
        self._model = model
        self._version = version
        self._api_key = api_key
        self._servers = servers
        self._turn = 0

    def start(self) -> None:
        print(self._banner())

        while True:
            try:
                line = input(self.PROMPT)
            except EOFError:  # Ctrl-D
                break

            line = line.strip()
            if not line:
                continue

            if line in ("/exit", "/quit"):
                print("Goodbye.")
                break
            elif line == "/help":
                print(self.HELP)
                continue
            elif line == "/quiet":
                boukensha.quiet()
                print("(logging suppressed — type /loud to re-enable)")
                continue
            elif line == "/loud":
                boukensha.loud()
                print("(logging enabled)")
                continue
            elif line == "/clear":
                self._context.clear_messages()
                self._turn = 0
                print("(conversation history cleared)")
                continue

            self._run_turn(line)

    # ---------- private -----------------------------------------------

    def _banner(self) -> str:
        key_status = "✗ API key not set" if not self._api_key or not self._api_key.strip() else "✓ API key set"
        provider_line = "{} ({})  {}".format(self._provider or "default", self._model or "default", key_status)
        config_exists = self._config_dir is not None and Path(self._config_dir).is_dir()
        config_line = self._config_dir if config_exists else "{}  ✗ directory not found".format(self._config_dir or "(default)")
        ver = self._version or "?.?.?"
        servers_stat = self._servers_status_string()

        return (
            "\n"
            "╔════════════════════════════════════════╗\n"
            "║  BOUKENSHA MUD Assistant (v{}){}  ║\n"
            "╚════════════════════════════════════════╝\n"
            "  config:    {}\n"
            "  provider:  {}\n"
            "  servers:   {}\n"
            "\n"
            "  /quiet or /loud   toggle logging\n"
            "  /clear           reset conversation history\n"
            "  /exit or /quit    leave the REPL\n"
        ).format(ver, " " * (9 - len(ver)), config_line, provider_line, servers_stat)

    # Build the MCP servers line shown in the banner. Every tool the agent has
    # came from one of these, so this doubles as "what can I actually do?".
    # No probing needed: a server that answers tools/list is already
    # connected, and one that didn't is either absent here or took the agent
    # down at boot.
    def _servers_status_string(self) -> str:
        if not self._servers:
            return "(none configured — the agent has no tools)"

        return "  ".join("{} ({})".format(name, count) for name, count in self._servers.items())

    def _run_turn(self, input_text: str) -> None:
        try:
            self._turn += 1
            self._logger.turn(n=self._turn)

            self._context.add_message("user", input_text)

            agent = Agent(
                context=self._context,
                registry=self._registry,
                builder=self._builder,
                client=self._client,
                logger=self._logger,
                task_settings=self._task_settings,
                max_iterations=self._max_iterations,
                max_output_tokens=self._max_output_tokens,
            )
            result = agent.run()

            # Print the final response outside of the logger so it is always
            # visible, even when boukensha.quiet() is active.
            print()
            print(result)
        except LoopError as e:
            print("\n[error] {}".format(e))
        except ApiError as e:
            print("\n[error] API call failed: {}".format(e))
