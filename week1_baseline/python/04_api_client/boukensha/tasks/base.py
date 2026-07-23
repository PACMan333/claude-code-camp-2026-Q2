from pathlib import Path
from typing import Any, Dict, Optional


class Base:
    @classmethod
    def task_name(cls) -> str:
        raise NotImplementedError("{} must define task_name()".format(cls.__name__))

    @classmethod
    def provider(cls, settings: Dict[str, Any]) -> str:
        value = cls._fetch(settings, "provider")
        if not value:
            raise ValueError(
                "tasks.{}.provider is required in settings.yaml".format(cls.task_name())
            )
        return value

    @classmethod
    def model(cls, settings: Dict[str, Any]) -> str:
        value = cls._fetch(settings, "model")
        if not value:
            raise ValueError(
                "tasks.{}.model is required in settings.yaml".format(cls.task_name())
            )
        return value

    @classmethod
    def prompt_override(cls, settings: Dict[str, Any], prompt: str = "system") -> bool:
        node = cls._fetch(settings, "prompt_override")
        if not isinstance(node, dict):
            return False
        return node.get(prompt) is True

    @classmethod
    def prompt(
        cls,
        settings: Dict[str, Any],
        name: str = "system",
        user_prompts_dir: Optional[str] = None,
        default_prompts_dir: Optional[str] = None,
    ) -> Optional[str]:
        if cls.prompt_override(settings, name):
            text = cls._read_user_prompt(name, user_prompts_dir)
            if text is not None:
                return text

        return cls._read_default_prompt(name, default_prompts_dir)

    @classmethod
    def system_prompt(
        cls,
        settings: Dict[str, Any],
        user_prompts_dir: Optional[str] = None,
        default_prompts_dir: Optional[str] = None,
    ) -> Optional[str]:
        return cls.prompt(
            settings,
            "system",
            user_prompts_dir=user_prompts_dir,
            default_prompts_dir=default_prompts_dir,
        )

    # ---------- private ---------------------------------------------------

    @classmethod
    def _fetch(cls, settings: Dict[str, Any], key: str) -> Any:
        return settings.get(key) if isinstance(settings, dict) else None

    @classmethod
    def _read_user_prompt(cls, prompt_name: str, user_prompts_dir: Optional[str]) -> Optional[str]:
        if not user_prompts_dir:
            return None
        return cls._read_file(Path(user_prompts_dir) / cls.task_name() / "{}.md".format(prompt_name))

    @classmethod
    def _read_default_prompt(cls, prompt_name: str, default_prompts_dir: Optional[str]) -> Optional[str]:
        if not default_prompts_dir:
            return None
        return cls._read_file(Path(default_prompts_dir) / "{}.md".format(prompt_name))

    @staticmethod
    def _read_file(path: Path) -> Optional[str]:
        return path.read_text().strip() if path.exists() else None
