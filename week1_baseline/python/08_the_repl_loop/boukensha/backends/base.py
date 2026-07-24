from typing import Any, Dict, Optional

from ..errors import UnsupportedModelError


class Base:
    def __init__(self) -> None:
        self.model: Optional[str] = None
        self._model_info: Optional[Dict[str, Any]] = None

    @classmethod
    def models(cls) -> Dict[str, Dict[str, Any]]:
        table = getattr(cls, "MODELS", None)
        if table is None:
            raise NotImplementedError("{} must define MODELS".format(cls.__name__))
        return table

    @classmethod
    def model_info(cls, model: str) -> Optional[Dict[str, Any]]:
        return cls.models().get(str(model))

    @classmethod
    def validate_model(cls, model: str) -> str:
        model = str(model)
        if cls.model_info(model):
            return model

        supported = ", ".join(sorted(cls.models().keys()))
        raise UnsupportedModelError(
            "{} does not support model {!r}. Supported models: {}".format(
                cls.__name__, model, supported
            )
        )

    @property
    def current_model_info(self) -> Dict[str, Any]:
        return self._model_info

    @property
    def context_window(self) -> int:
        return self.current_model_info["context_window"]

    @property
    def input_token_cost_per_million(self) -> Optional[float]:
        return self.current_model_info["cost_per_million"]["input"]

    @property
    def output_token_cost_per_million(self) -> Optional[float]:
        return self.current_model_info["cost_per_million"]["output"]

    @property
    def usage_unit(self) -> str:
        return self.current_model_info["usage_unit"]

    @property
    def usage_level(self) -> Optional[str]:
        return self.current_model_info.get("usage_level")

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> Optional[float]:
        input_cost = self.input_token_cost_per_million
        output_cost = self.output_token_cost_per_million
        if input_cost is None or output_cost is None:
            return None

        return ((input_tokens * input_cost) + (output_tokens * output_cost)) / 1_000_000.0

    def configure_model(self, model: str) -> None:
        self.model = self.__class__.validate_model(model)
        self._model_info = self.__class__.model_info(self.model)
