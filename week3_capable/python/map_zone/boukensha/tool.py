from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    block: Callable[..., Any]

    def __str__(self) -> str:
        return "<Tool name={} description={} params={}>".format(
            self.name, str(self.description)[:41], list(self.parameters.keys())
        )
