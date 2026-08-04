"""Offline end-to-end test for week3_capable/bin/reset.

Spawns a throwaway Ruby process hosting the extended MudManager::FakeMud
(dummy/admin accounts, teleport + look coordinating through shared room
state, hijack/"already in use" simulation on a second login for the same
name -- see week0_explore/mud_manager/lib/mud_manager/fake_mud.rb), then
runs the real week3_capable/bin/reset executable against it as a
subprocess. No live MUD, no network beyond localhost, no API key.
"""
import os
import socket
import subprocess
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MUD_MANAGER_ROOT = REPO_ROOT / "week0_explore" / "mud_manager"
RESET_BIN = Path(__file__).resolve().parents[1] / "bin" / "reset"

PLAYER_USERNAME = "dummy"
PLAYER_PASSWORD = "helloworld"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password"
START_ROOM = "3001"


def start_fake_mud(accounts):
    """Spawn a throwaway Ruby process hosting MudManager::FakeMud with the
    given {username: password} accounts, print its port, then block until
    this process's stdin is closed. Same spawn pattern as
    week3_capable/python/tool_scoping/examples/mcp_mud_demo.py's
    start_fake_mud() -- reused rather than reimplementing a fake MUD in
    Python, since the real one (used by this repo's Ruby side too) is one
    subprocess away.
    """
    accounts_literal = ", ".join(
        '"{}" => "{}"'.format(name, password) for name, password in accounts.items()
    )
    script = (
        "$LOAD_PATH.unshift '{lib}'\n"
        "require 'mud_manager/fake_mud'\n"
        "fake = MudManager::FakeMud.new(accounts: {{{accounts}}})\n"
        "STDOUT.puts(fake.port)\n"
        "STDOUT.flush\n"
        "STDIN.gets\n"
        "fake.stop\n"
    ).format(lib=MUD_MANAGER_ROOT / "lib", accounts=accounts_literal)

    proc = subprocess.Popen(
        ["ruby", "-e", script],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    port = int(proc.stdout.readline().strip())
    return proc, port


def stop_fake_mud(proc):
    try:
        proc.stdin.close()
    except (OSError, ValueError):
        pass
    proc.wait(timeout=5)
    proc.stdout.close()
    proc.stderr.close()


def run_reset(port):
    env = {
        **os.environ,
        "MUD_HOST": "127.0.0.1",
        "MUD_PORT": str(port),
        "PLAYER_USERNAME": PLAYER_USERNAME,
        "PLAYER_PASSWORD": PLAYER_PASSWORD,
        "ADMIN_USERNAME": ADMIN_USERNAME,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
        "START_ROOM": START_ROOM,
    }
    return subprocess.run(
        [str(RESET_BIN)], env=env, capture_output=True, text=True, timeout=30,
    )


class TestResetDry(unittest.TestCase):
    def setUp(self):
        self.fake_proc, self.fake_port = start_fake_mud(
            {PLAYER_USERNAME: PLAYER_PASSWORD, ADMIN_USERNAME: ADMIN_PASSWORD}
        )

    def tearDown(self):
        stop_fake_mud(self.fake_proc)

    def test_teleports_player_to_start_room(self):
        result = run_reset(self.fake_port)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("temple of midgaard", result.stdout.lower())

    def test_warns_on_hijacked_player_session(self):
        # Connect a throwaway third socket as the player first, so reset's
        # own player login has to take over an already-connected session --
        # exercises the hijack-warning path from the plan's Design section 2.
        interloper = socket.create_connection(("127.0.0.1", self.fake_port), timeout=5)
        try:
            interloper.sendall(b"dummy\r\n")
            time.sleep(0.2)
            interloper.sendall(b"helloworld\r\n")
            time.sleep(0.2)
            interloper.sendall(b"\r\n")
            time.sleep(0.2)
            interloper.sendall(b"1\r\n")
            time.sleep(0.3)
            interloper.recv(4096)  # drain the login banter, ignore content

            result = run_reset(self.fake_port)
        finally:
            interloper.close()

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("already connected elsewhere", result.stderr)


if __name__ == "__main__":
    unittest.main()
