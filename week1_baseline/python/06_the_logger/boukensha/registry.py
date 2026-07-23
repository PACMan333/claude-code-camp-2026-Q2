from typing import Any, Callable, Dict, Optional

from .errors import UnknownToolError
from .tool import Tool


class Registry:
    def __init__(self, context) -> None:
        self._context = context

    def tool(
        self,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
        block: Optional[Callable[..., Any]] = None,
    ) -> Tool:
        tool = Tool(name, description, parameters or {}, block)
        self._context.register_tool(tool)
        return tool

    def dispatch(self, name: str, args: Optional[Dict[str, Any]] = None) -> Any:
        tool = self._context.tools.get(name)
        if not tool:
            raise UnknownToolError("No tool registered as '{}'".format(name))

        return tool.block(**(args or {}))
