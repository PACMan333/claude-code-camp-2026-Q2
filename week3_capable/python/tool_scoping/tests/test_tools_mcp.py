"""Unit tests for boukensha.tools.mcp's per-tool filter/rename logic.

Uses an in-process fake MCP client double -- register_client only needs an
object with a `.tools` list of {"name":, "description":, "inputSchema":}
dicts and a `.call_tool(name, arguments)` method -- so this exercises the
filtering/renaming logic with no subprocess, no MUD, no network. The real
`mud-manager` daemon is only exercised by examples/mcp_mud_demo.py --dry.
"""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boukensha  # noqa: E402
from boukensha.tools import mcp as tools_mcp  # noqa: E402


class FakeClient:
    def __init__(self, tools):
        self.tools = tools
        self.calls = []

    def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments or {}))
        return {"error": False, "text": "you did: {} {}".format(name, arguments or {})}


def fake_tools(*names):
    return [
        {"name": n, "description": "desc for {}".format(n), "inputSchema": {"properties": {}}}
        for n in names
    ]


def new_registry():
    ctx = boukensha.Context(system="test")
    return ctx, boukensha.Registry(ctx)


class TestToolsMcp(unittest.TestCase):
    def test_none_registers_everything_unchanged(self):
        ctx, registry = new_registry()
        client = FakeClient(fake_tools("move", "examine", "look"))

        count = tools_mcp.register_client(registry, client, prefix="tbamud", tools=None)

        self.assertEqual(count, 3)
        self.assertEqual(set(ctx.tools.keys()), {"tbamud__move", "tbamud__examine", "tbamud__look"})

    def test_mixed_table_registers_only_enabled(self):
        ctx, registry = new_registry()
        client = FakeClient(fake_tools("move", "examine", "look", "attack"))
        spec = {
            "move": {"enabled": True, "as": None},
            "examine": {"enabled": True, "as": None},
            "look": {"enabled": False, "as": None},
            "attack": {"enabled": False, "as": None},
        }

        count = tools_mcp.register_client(registry, client, prefix="tbamud", tools=spec)

        self.assertEqual(count, 2)
        self.assertEqual(set(ctx.tools.keys()), {"tbamud__move", "tbamud__examine"})

    def test_all_off_table_registers_nothing(self):
        """The specific footgun: an all-disabled table must not silently
        fall back to "register everything" just because the collection of
        enabled flags is all-False (falsy)."""
        ctx, registry = new_registry()
        client = FakeClient(fake_tools("move", "examine", "look"))
        spec = {name: {"enabled": False, "as": None} for name in ("move", "examine", "look")}

        count = tools_mcp.register_client(registry, client, prefix="tbamud", tools=spec)

        self.assertEqual(count, 0)
        self.assertEqual(ctx.tools, {})

    def test_alias_renames_local_but_not_wire_call(self):
        ctx, registry = new_registry()
        client = FakeClient(fake_tools("move", "examine", "info_self"))
        spec = {
            "move": {"enabled": True, "as": None},
            "examine": {"enabled": True, "as": None},
            "info_self": {"enabled": True, "as": "check"},
        }

        tools_mcp.register_client(registry, client, prefix="tbamud", tools=spec)

        self.assertIn("tbamud__check", ctx.tools)
        self.assertNotIn("tbamud__info_self", ctx.tools)

        result = registry.dispatch("tbamud__check", {"kind": "exits"})
        self.assertIn("info_self", result)
        # Proves the closure calls the real remote name, not the alias.
        self.assertEqual(client.calls, [("info_self", {"kind": "exits"})])

    def test_unmatched_allowlist_entry_warns_but_does_not_raise(self):
        ctx, registry = new_registry()
        client = FakeClient(fake_tools("move"))
        spec = {
            "move": {"enabled": True, "as": None},
            "nonexistent_tool": {"enabled": True, "as": None},
        }

        buf = io.StringIO()
        with redirect_stdout(buf):
            count = tools_mcp.register_client(registry, client, prefix="tbamud", tools=spec)

        self.assertEqual(count, 1)
        self.assertIn("tbamud__move", ctx.tools)
        self.assertIn("nonexistent_tool", buf.getvalue())

    def test_collision_still_raises_with_filtering_and_aliasing(self):
        _ctx, registry = new_registry()
        client_a = FakeClient(fake_tools("attack"))
        spec_a = {"attack": {"enabled": True, "as": "move"}}
        tools_mcp.register_client(registry, client_a, prefix="tbamud", tools=spec_a)

        client_b = FakeClient(fake_tools("move"))
        spec_b = {"move": {"enabled": True, "as": None}}
        with self.assertRaises(tools_mcp.CollisionError):
            tools_mcp.register_client(registry, client_b, prefix="tbamud", tools=spec_b)

    def test_return_value_is_registered_count_not_advertised_count(self):
        _ctx, registry = new_registry()
        client = FakeClient(fake_tools("move", "examine", "look", "attack", "flee"))
        spec = {
            "move": {"enabled": True, "as": None},
            "examine": {"enabled": True, "as": None},
        }

        count = tools_mcp.register_client(registry, client, prefix="tbamud", tools=spec)

        self.assertEqual(count, 2)
        self.assertEqual(len(client.tools), 5)


if __name__ == "__main__":
    unittest.main()
