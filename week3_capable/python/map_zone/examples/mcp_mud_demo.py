"""
Step 10 x mud-manager (MCP path), now demonstrating tool scoping.

boukensha has no MUD code at all. This points its generic MCP client at the
`mud-manager` daemon and registers whatever tools the daemon advertises --
exactly what the Ruby / Go / Rust / Java tracks do with their own SDKs.
Nothing in boukensha.tools.mcp knows what a MUD is; the daemon is just a
server, and this file is just a host.

Note the names: the daemon advertises `look`, but we pass prefix="tbamud",
so the agent sees `tbamud__look`. Prefixing is applied agent-side; the
daemon never hears about it. In a real run that prefix comes from config.

The --dry path below also exercises the `tools:` filter/rename mechanism
(week3_capable/python/tool_scoping/boukensha/tools/mcp.py) against the real
daemon -- the same table shipped in the repo's .boukensha/settings.yaml:
`move`/`examine` on as themselves, `info_self` on but renamed to `check`,
everything else off. This proves two things a fake-client unit test can't:
the real `mud-manager` process only advertises 55 tools total but the agent
only ever sees 3, and `tbamud__check` really does reach the daemon's
`info_self` handler on the wire.

  # Self-contained smoke test -- no API key, no live MUD (built-in fake MUD):
  python examples/mcp_mud_demo.py --dry

  # Full agent run -- needs ANTHROPIC_API_KEY and a reachable MUD via
  # .boukensha/settings.yaml's mcp_servers: mud: entry:
  python examples/mcp_mud_demo.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import boukensha  # noqa: E402

# The mud-manager daemon lives in the sibling week0_explore package -- it's
# an external MCP server subprocess, language-agnostic, not Python code we
# import. This is the same daemon the Ruby port's demo spawns.
MUD_MANAGER_ROOT = Path(__file__).resolve().parents[4] / "week0_explore" / "mud_manager"
MUD_MANAGER_BIN = MUD_MANAGER_ROOT / "bin" / "mud-manager"

dry = "--dry" in sys.argv


def start_fake_mud():
    """Spawn a throwaway Ruby process hosting MudManager::FakeMud, print its
    port, then block until this process's stdin is closed. Reused directly
    from the Ruby lib -- there's no reason to reimplement a fake MUD in
    Python when the real one (used by this same repo's Ruby test suite) is
    one subprocess away.
    """
    script = (
        "$LOAD_PATH.unshift '{lib}'\n"
        "require 'mud_manager/fake_mud'\n"
        "fake = MudManager::FakeMud.new\n"
        "STDOUT.puts(fake.port)\n"
        "STDOUT.flush\n"
        "STDIN.gets\n"
        "fake.stop\n"
    ).format(lib=MUD_MANAGER_ROOT / "lib")

    proc = subprocess.Popen(
        ["ruby", "-e", script],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    port = int(proc.stdout.readline().strip())
    return proc, port


if dry:
    fake_proc, fake_port = start_fake_mud()
    creds = {
        "MUD_HOST": "127.0.0.1", "MUD_PORT": str(fake_port),
        "MUD_NAME": "Gandalf", "MUD_PASSWORD": "secret",
    }

    ctx = boukensha.Context(system="demo")
    registry = boukensha.Registry(ctx)

    # Same shape Config._parse_tools produces from settings.yaml's tools:
    # table -- move/examine on as themselves, info_self on but renamed to
    # check. Everything else the daemon advertises is left out entirely, so
    # it's off (see the "tools: present at all -> explicit mode" rule).
    tool_scope = {
        "move": {"enabled": True, "as": None},
        "examine": {"enabled": True, "as": None},
        "info_self": {"enabled": True, "as": "check"},
    }

    client = boukensha.tools_mcp.register(
        registry, command="ruby", args=[str(MUD_MANAGER_BIN), "--mcp"],
        env=creds, prefix="tbamud", tools=tool_scope,
    )

    print("daemon: {}".format(client.server_info))
    print("daemon advertises: {} tools".format(len(client.tools)))
    print("agent registered:  {} — {}".format(len(ctx.tools), ", ".join(sorted(ctx.tools.keys()))))
    print()

    print("tbamud__move north     => {!r}".format(registry.dispatch("tbamud__move", {"direction": "north"})))
    print("tbamud__examine sword  => {!r}".format(registry.dispatch("tbamud__examine", {"target": "sword"})))
    # tbamud__check is a rename of the daemon's own info_self tool -- the
    # daemon itself was never told about "check"; this dispatch call still
    # sends {"name": "info_self", "arguments": {"kind": "exits"}} on the wire.
    print("tbamud__check exits    => {!r}".format(registry.dispatch("tbamud__check", {"kind": "exits"})))

    # Filtered out entirely -- never registered, so dispatch raises exactly
    # like calling any other unknown tool name would.
    try:
        registry.dispatch("tbamud__attack", {"target": "orc"})
        raise AssertionError("tbamud__attack should not have been registered")
    except boukensha.UnknownToolError:
        print("tbamud__attack         => correctly not registered (filtered off)")

    client.close()
    fake_proc.stdin.close()
    fake_proc.wait()
    print("\n[dry run OK -- daemon + step 10 generic MCP layer working]")
    sys.exit(0)

# --- full agent run ---------------------------------------------------------
boukensha.run(
    task="Look at your surroundings, check your score, then look at the exits "
         "and tell me what you see."
)
