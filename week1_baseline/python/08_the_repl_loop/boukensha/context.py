from typing import Dict, List, Optional

from .message import Message
from .tool import Tool


class Context:
    def __init__(self, task=None, system: Optional[str] = None) -> None:
        self._task = task
        self._system = system
        self._messages: List[Message] = []
        self._tools: Dict[str, Tool] = {}

    @property
    def task(self):
        return self._task

    @property
    def system(self) -> Optional[str]:
        return self._system

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

    def clear_messages(self) -> None:
        self._messages = []

    def tool_count(self) -> int:
        return len(self._tools)

    def turn_count(self) -> int:
        return len(self._messages)

    def __str__(self) -> str:
        task_name = self._task.task_name() if self._task else None
        return "<Context task={} turns={} tools={}>".format(
            task_name, self.turn_count(), self.tool_count()
        )
