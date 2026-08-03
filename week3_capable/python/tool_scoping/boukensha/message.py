from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    role: str
    content: str
    tool_use_id: Optional[str] = None

    def __str__(self) -> str:
        id_tag = " [{}]".format(self.tool_use_id) if self.tool_use_id else ""
        return "<Message role={}{} content={}...>".format(
            self.role, id_tag, str(self.content)[:61]
        )
