from ..mcp.client import Client

SEPARATOR = "__"


class CollisionError(ValueError):
    pass


def register(registry, *, command, args=None, env=None, prefix=None):
    """Makes boukensha an MCP host: point it at any MCP server and every tool
    that server advertises becomes a boukensha tool. It knows nothing about
    any particular server -- `command`/`args`/`env` is the standard stdio
    transport config, the same triple every other MCP host uses.

        boukensha.tools.mcp.register(
            registry, command="mud-manager", args=["--mcp"],
            env={"MUD_HOST": "localhost"}, prefix="tbamud",
        )

    `registry` is anything with the tool/tool_names surface -- a Registry or
    the RunDSL yielded to a run/repl block.

    prefix: scopes the discovered names ("tbamud" -> tbamud__look). The
    prefix is a property of the server entry, supplied by config; this
    function applies whatever it is given. Names are only prefixed
    agent-side -- the server still sees its own bare name on the wire.
    """
    import atexit

    client = Client.spawn(command=command, args=args or [], env=env or {})

    def _close():
        try:
            client.close()
        except Exception:
            pass

    atexit.register(_close)
    register_client(registry, client, prefix=prefix)
    return client


def register_client(registry, client, *, prefix=None):
    """Register an already-spawned client's tools. Returns the count."""
    taken = list(registry.tool_names()) if hasattr(registry, "tool_names") else []

    for tool in client.tools:
        remote = tool["name"]
        local = prefixed(remote, prefix)

        if local in taken:
            raise CollisionError(
                "boukensha: MCP tool name collision on '{}' — a tool by that "
                "name is already registered. Give this server a distinct `prefix:` "
                "in mcp_servers.".format(local)
            )
        taken.append(local)

        def block(_remote=remote, _client=client, **kwargs):
            # Boukensha hands us string-keyed kwargs already (unlike Ruby,
            # which needs a symbol->string transform_keys here); the server
            # wants string keys too, so no conversion is needed.
            result = _client.call_tool(_remote, kwargs)
            return "error: {}".format(result["text"]) if result["error"] else result["text"]

        registry.tool(
            local,
            description=str(tool.get("description") or ""),
            parameters=to_boukensha_params(tool.get("inputSchema")),
            block=block,
        )

    return len(client.tools)


def prefixed(name, prefix):
    p = (prefix or "").strip()
    return name if not p else "{}{}{}".format(p, SEPARATOR, name)


def to_boukensha_params(input_schema):
    """Convert an MCP inputSchema into boukensha's `parameters` shape
    ({name: {type:, description:}}). We list every property so the model can
    supply optional ones too (servers treat blanks as absent).
    """
    props = (input_schema or {}).get("properties") or {}
    out = {}
    for pname, schema in props.items():
        desc = str(schema.get("description") or "")
        if schema.get("enum"):
            desc = "{} (one of: {})".format(desc, ", ".join(schema["enum"])).strip()
        out[pname] = {"type": schema.get("type") or "string", "description": desc}
    return out
