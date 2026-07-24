class RunDSL:
    """The object passed into `register_tools` inside `boukensha.run(...)`.

    Exposes only `tool`, keeping the DSL surface intentionally small.
    """

    def __init__(self, registry) -> None:
        self._registry = registry

    def tool(self, name, description, parameters=None, block=None):
        return self._registry.tool(name, description, parameters, block)
