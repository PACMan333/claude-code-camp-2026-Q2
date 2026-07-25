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
    #
    # Returns {"mud": {"command":, "args":, "env":, "prefix":, "required":}}
    # with defaults applied. required=False lets a server fail to spawn
    # without taking the agent down with it.
    def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        raw_servers = self.dig("mcp_servers") or {}
        out: Dict[str, Dict[str, Any]] = {}
        for name, raw in raw_servers.items():
            entry = raw if isinstance(raw, dict) else {}
            required = entry.get("required")
            out[str(name)] = {
                "command": str(entry.get("command") or ""),
                "args": [str(a) for a in (entry.get("args") or [])],
                "env": {str(k): str(v) for k, v in (entry.get("env") or {}).items()},
                "prefix": str(entry["prefix"]) if entry.get("prefix") else None,
                "required": True if required is None else bool(required),
            }
        return out

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
        return "<Boukensha.Config dir={} tasks={}>".format(
            self._dir, ",".join(self.tasks().keys())
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
