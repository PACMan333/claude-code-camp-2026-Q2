class RunDSL:
    """The object passed into `register_tools` inside `boukensha.run(...)`.

    Exposes `tool`/`tool_names`/`dispatch`, keeping the DSL surface small
    but letting a tool's own block call another already-registered tool
    (dispatch runs after MCP registration, so e.g. an MCP-provided `move`
    is already available -- see week3_capable/python/map_zone/zone_nav/tool.py's
    goto_room, which calls move/look internally to do its own navigation).
    """

    def __init__(self, registry) -> None:
        self._registry = registry

    def tool(self, name, description, parameters=None, block=None):
        return self._registry.tool(name, description, parameters, block)

    def tool_names(self):
        return self._registry.tool_names()

    def dispatch(self, name, args=None):
        return self._registry.dispatch(name, args)
