import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

# Default prompts shipped alongside this step.
PROMPTS_DIR = str((Path(__file__).resolve().parent.parent / "prompts"))

# The .boukensha config directory is resolved in this order:
#   1. BOUKENSHA_DIR environment variable (set before loading .env)
#   2. ~/.boukensha  (default)
DEFAULT_DIR = str(Path.home() / ".boukensha")


class Config:
    def __init__(self) -> None:
        self._dir = self._resolve_dir()
        self._load_env()
        self._settings = self._load_settings()

    # ---------- tasks -------------------------------------------------

    def tasks(self, name: Optional[str] = None) -> Any:
        all_tasks = self.dig("tasks") or {}
        if name is None:
            return all_tasks
        return all_tasks.get(name)

    @property
    def user_prompts_dir(self) -> str:
        return str(Path(self._dir) / "prompts")

    # ---------- provider ----------------------------------------------

    def provider_type(self) -> str:
        return self.dig("tasks", "player", "provider") or "anthropic"

    def model(self) -> str:
        return self.dig("tasks", "player", "model") or "claude-haiku-4-5"

    # ---------- MCP servers ------------------------------------------------

    # MCP servers to plug into the agent, keyed by name. This is where ALL of
    # the agent's tools come from -- boukensha ships none of its own:
    #
    #   mcp_servers:
    #     mud:
    #       command: mud-manager
    #       args:    [--mcp]
    #       prefix:  tbamud
    #       env:
    #         MUD_HOST: your.mud.host      # a stdio server's credentials
    #         MUD_NAME: Gandalf            # travel by environment
    #       tools:                         # optional -- omit to register
    #         move: on                     # every tool the server advertises
    #         look: off                    # (today's behavior, unchanged).
    #         info_self:                   # Present at all (even all-off)
    #           "on": true                 # switches to explicit mode: only
    #           as: check                  # tools listed AND on register;
    #                                       # anything else is off. `as:`
    #                                       # renames the tool the agent sees
    #                                       # without changing what's sent to
    #                                       # the server on the wire.
    #
    # Returns {"mud": {"command":, "args":, "env":, "prefix":, "required":,
    # "tools":}} with defaults applied. required=False lets a server fail to
    # spawn without taking the agent down with it. tools=None means
    # unfiltered (register everything); a dict means explicit per-tool
    # {"enabled":, "as":} specs -- see `_parse_tools`.
    def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        raw_servers = self.dig("mcp_servers") or {}
        out: Dict[str, Dict[str, Any]] = {}
        for name, raw in raw_servers.items():
            entry = raw if isinstance(raw, dict) else {}
            required = entry.get("required")
            raw_tools = entry.get("tools")
            out[str(name)] = {
                "command": str(entry.get("command") or ""),
                "args": [str(a) for a in (entry.get("args") or [])],
                "env": {str(k): str(v) for k, v in (entry.get("env") or {}).items()},
                "prefix": str(entry["prefix"]) if entry.get("prefix") else None,
                "required": True if required is None else bool(required),
                "tools": self._parse_tools(raw_tools) if isinstance(raw_tools, dict) else None,
            }
        return out

    # Turns settings.yaml's `tools:` mapping ({"move": on/off, "info_self":
    # {"on":, "as":}}) into {remote_name: {"enabled": bool, "as": str|None}}.
    # A `tools:` mapping present at all -- even empty, even all-off --
    # switches the server into explicit mode in the caller (see
    # tools/mcp.py's register_client): only entries with enabled=True are
    # registered, anything not mentioned in the table at all is off.
    #
    # spec.get(True, ...) below guards against a real YAML footgun: PyYAML's
    # implicit resolver turns a *bare* `on` into the boolean True even when
    # it's used as a mapping key (not just a value), so an unquoted
    # `info_self: {on: true, as: check}` parses as {True: True, "as": ...},
    # not {"on": True, ...}. settings.yaml quotes the key ("on": true) to
    # avoid this, but a future hand-edit that forgets to quote it should
    # still work rather than silently losing the flag.
    @staticmethod
    def _parse_tools(raw_tools: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for remote, spec in raw_tools.items():
            if isinstance(spec, dict):
                enabled = Config._truthy(spec.get("on", spec.get(True, True)))
                alias = str(spec["as"]) if spec.get("as") else None
            else:
                enabled, alias = Config._truthy(spec), None
            out[str(remote)] = {"enabled": enabled, "as": alias}
        return out

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("on", "true", "yes", "1")
        return bool(value)

    # ---------- agent limits --------------------------------------------
    # Static per-turn circuit breakers, read where the agent is constructed.
    # A value of 0 or None means "disabled" (no ceiling) -- useful for
    # debugging.

    def agent_max_iterations(self) -> int:
        v = self.dig("agent", "max_iterations")
        return 25 if v is None else int(v)

    def agent_max_output_tokens(self) -> int:
        v = self.dig("agent", "max_output_tokens")
        return 1024 if v is None else int(v)

    def agent_max_turn_tokens(self) -> int:
        v = self.dig("agent", "max_turn_tokens")
        return 60_000 if v is None else int(v)

    def agent_compaction_threshold(self) -> float:
        v = self.dig("agent", "compaction_threshold")
        return 0.85 if v is None else float(v)

    # ---------- low-level helpers ---------------------------------------

    def dig(self, *keys: str) -> Any:
        node: Any = self._settings
        for key in keys:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                return None
        return node

    @property
    def dir(self) -> str:
        return self._dir

    @property
    def settings(self) -> Dict[str, Any]:
        return self._settings

    def __repr__(self) -> str:
        return "<Boukensha.Config dir={} provider={} model={}>".format(
            self._dir, self.provider_type(), self.model()
        )

    # ---------- private ---------------------------------------------------

    def _resolve_dir(self) -> str:
        raw = os.environ.get("BOUKENSHA_DIR") or DEFAULT_DIR
        return str(Path(raw).expanduser().resolve())

    def _load_env(self) -> None:
        env_file = Path(self._dir) / ".env"
        if env_file.exists():
            load_dotenv(env_file)

    def _load_settings(self) -> Dict[str, Any]:
        settings_file = Path(self._dir) / "settings.yaml"
        if settings_file.exists():
            return yaml.safe_load(settings_file.read_text()) or {}
        return {}
