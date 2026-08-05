"""
Live smoke test for the `goto_room` tool (zone_nav/tool.py) -- no Anthropic
API call anywhere in this script, so it's free to run without spend
approval. Builds a Context/Registry directly (same shape
examples/mcp_mud_demo.py uses), registers the real `mud-manager` MCP
tools (`move` and `look`, prefixed "tbamud" to match the shared
.boukensha/settings.yaml convention) plus the local `goto_room` tool, then
dispatches "goto_room" directly -- pure Python-to-MCP-to-MUD, exactly what
`bin/boukensha`'s interactive REPL does when an agent calls the tool,
minus the LLM turn that would decide to call it.

Usage:
    python examples/goto_demo.py ["Room Name"]

Defaults to "Bakery" if no room name is given -- the example from the
plan's own task prompt.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import boukensha  # noqa: E402
from boukensha.tools import mcp as tools_mcp  # noqa: E402
import zone_nav.tool as zone_nav_tool  # noqa: E402

MUD_MANAGER_ROOT = Path(__file__).resolve().parents[4] / "week0_explore" / "mud_manager"
MUD_MANAGER_BIN = MUD_MANAGER_ROOT / "bin" / "mud-manager"

room_name = sys.argv[1] if len(sys.argv) > 1 else "Bakery"

ctx = boukensha.Context(system="goto_room demo")
registry = boukensha.Registry(ctx)

tools_mcp.register(
    registry, command="ruby", args=[str(MUD_MANAGER_BIN), "--mcp"],
    env={"MUD_HOST": "localhost", "MUD_PORT": "4000", "MUD_NAME": "dummy", "MUD_PASSWORD": "helloworld"},
    prefix="tbamud",
    tools={"move": {"enabled": True, "as": None}, "look": {"enabled": True, "as": None}},
)

# A raw Registry already exposes .tool()/.dispatch() -- the same surface
# zone_nav.tool.register expects from a RunDSL, so no wrapping needed here.
zone_nav_tool.register(registry)

print("registered tools: {}".format(", ".join(sorted(registry.tool_names()))))
print()
print("goto_room({!r}) => {}".format(room_name, registry.dispatch("goto_room", {"room_name": room_name})))
