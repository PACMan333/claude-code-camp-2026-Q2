import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

# Default prompts shipped alongside this step.
PROMPTS_DIR = str((Path(__file__).resolve().parent.parent / "prompts"))

# The .boukensha config directory is resolved in this order:
#   1. BOUKENSHA_DIR environment variable (set before loading .env)
#   2. .boukensha in the current working directory
#   3. ~/.boukensha  (default)
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

    # ---------- MUD connection -----------------------------------------

    def mud_host(self) -> str:
        return self.dig("mud", "host") or "localhost"

    def mud_port(self) -> int:
        return self.dig("mud", "port") or 4000

    def mud_username(self) -> Optional[str]:
        return self.dig("mud", "username")

    def mud_password(self) -> Optional[str]:
        return self.dig("mud", "password")

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
        # 1. Explicit override
        env_dir = os.environ.get("BOUKENSHA_DIR")
        if env_dir:
            return str(Path(env_dir).expanduser().resolve())

        # 2. .boukensha in the current working directory
        cwd_dir = Path.cwd() / ".boukensha"
        if cwd_dir.is_dir():
            return str(cwd_dir)

        # 3. ~/.boukensha default
        return str(Path(DEFAULT_DIR).expanduser().resolve())

    def _load_env(self) -> None:
        env_file = Path(self._dir) / ".env"
        if env_file.exists():
            load_dotenv(env_file)

    def _load_settings(self) -> Dict[str, Any]:
        settings_file = Path(self._dir) / "settings.yaml"
        if settings_file.exists():
            return yaml.safe_load(settings_file.read_text()) or {}
        return {}
