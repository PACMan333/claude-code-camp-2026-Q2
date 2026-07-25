from pathlib import Path
from typing import Dict, List, Optional

from .message import Message
from .tool import Tool


class Context:
    def __init__(
        self,
        *,
        system: Optional[str] = None,
        context_window: int = 200_000,
        working_dir: Optional[str] = None,
        compaction_threshold: float = 0.85,
    ) -> None:
        self._system = system
        self._context_window = context_window
        self._working_dir = str(Path(working_dir).resolve()) if working_dir is not None else None
        self._compaction_threshold = compaction_threshold
        self._messages: List[Message] = []
        self._tools: Dict[str, Tool] = {}
        self.current_tokens = 0
        self._turn_tokens = 0

    @property
    def system(self) -> Optional[str]:
        return self._system

    @property
    def context_window(self) -> int:
        return self._context_window

    @property
    def working_dir(self) -> Optional[str]:
        return self._working_dir

    @property
    def compaction_threshold(self) -> float:
        return self._compaction_threshold

    @property
    def turn_tokens(self) -> int:
        return self._turn_tokens

    @property
    def messages(self) -> List[Message]:
        return self._messages

    @property
    def tools(self) -> Dict[str, Tool]:
        return self._tools

    def register_tool(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def add_message(self, role: str, content: str, tool_use_id: Optional[str] = None) -> None:
        self._messages.append(Message(role, content, tool_use_id))

    # Update the known context size from the last API response's input_tokens.
    def update_tokens(self, n) -> None:
        self.current_tokens = int(n or 0)

    # Reset the cumulative per-turn spend counter. Called at the top of a turn.
    def reset_turn_tokens(self) -> None:
        self._turn_tokens = 0

    # Add one API call's input+output tokens to the cumulative per-turn total.
    # This is the spend budget -- distinct from current_tokens (window pressure).
    def add_turn_tokens(self, input_tokens, output_tokens) -> None:
        self._turn_tokens += int(input_tokens or 0) + int(output_tokens or 0)

    # Fraction of the context window currently in use (0.0-1.0).
    def usage_fraction(self) -> float:
        return self.current_tokens / self._context_window if self._context_window > 0 else 0.0

    # Integer percentage (0-100).
    def usage_pct(self) -> int:
        return round(self.usage_fraction() * 100)

    # True when we should compact before the next API call. Defaults to the
    # configured compaction_threshold (a fraction of context_window).
    def needs_compaction(self, threshold: Optional[float] = None) -> bool:
        threshold = self._compaction_threshold if threshold is None else threshold
        return self.usage_fraction() >= threshold

    # Drop the oldest 40% of messages to free space, keeping at least 2.
    # Resets current_tokens to 0 (will be updated by the next API response).
    # Returns the number of messages dropped.
    def compact_messages(self, target_fraction: float = 0.60) -> int:
        drop_count = min(-(-len(self._messages) * 40 // 100), len(self._messages) - 2)
        drop_count = max(drop_count, 0)
        self._messages = self._messages[drop_count:]
        self.current_tokens = 0
        return drop_count

    # Drop all conversation history, keeping tools and system prompt intact.
    def clear_messages(self) -> None:
        self._messages = []
        self.current_tokens = 0

    def tool_count(self) -> int:
        return len(self._tools)

    def turn_count(self) -> int:
        return len(self._messages)

    def __str__(self) -> str:
        return "<Context turns={} tools={} window={} current={}>".format(
            self.turn_count(), self.tool_count(), self.context_window, self.current_tokens
        )
