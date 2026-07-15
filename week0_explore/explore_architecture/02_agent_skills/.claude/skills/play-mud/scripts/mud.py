#!/usr/bin/env python3
"""
Telnet client/controller for a tbaMUD (CircleMUD-family) server.

Runs a small background daemon that holds the actual telnet connection open
(MUDs are stateful and time-sensitive — reconnecting per command would drop
you from the game and re-trigger login every time). The CLI talks to that
daemon over a local Unix socket to send commands and read output.

Subcommands:
    start                 connect, log in, and leave the session running
    send "<command>"      send one command line, return the game's response
    read [--wait SECS]    read any output that has arrived without sending
                           anything (useful for combat rounds, regen ticks,
                           other players' actions)
    status                report whether a session is currently running
    stop                  quit the game and shut the daemon down

Internal (used by `start`, not called directly):
    _daemon                run the connect+relay loop in the foreground
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4000
DEFAULT_USERNAME = "dummy"
DEFAULT_PASSWORD = "helloworld"

# AF_UNIX socket paths are capped at ~108 bytes on Linux, so runtime state
# lives in /tmp rather than next to the script (which may be nested deep
# inside a project directory).
RUNTIME_DIR = os.path.join(tempfile.gettempdir(), "play-mud-session")
SOCK_PATH = os.path.join(RUNTIME_DIR, "control.sock")
LOG_PATH = os.path.join(RUNTIME_DIR, "session.log")
DAEMON_STDOUT_PATH = os.path.join(RUNTIME_DIR, "daemon.out")

# --- Telnet protocol constants ---
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240

ANSI_RE = re.compile(rb"\x1b\[[0-9;]*[a-zA-Z]")


class TelnetParser:
    """Incrementally strips telnet IAC negotiation and ANSI color codes out
    of a raw byte stream, replying to option negotiation by refusing
    everything (IAC WONT/DONT) so the server settles into plain text mode."""

    def __init__(self):
        self._buf = b""

    def feed(self, data: bytes):
        self._buf += data
        buf = self._buf
        n = len(buf)
        text = bytearray()
        replies = bytearray()
        i = 0
        while i < n:
            b = buf[i]
            if b == IAC:
                if i + 1 >= n:
                    break  # wait for more bytes
                cmd = buf[i + 1]
                if cmd == IAC:
                    text.append(IAC)
                    i += 2
                    continue
                if cmd in (WILL, WONT, DO, DONT):
                    if i + 2 >= n:
                        break
                    opt = buf[i + 2]
                    if cmd == WILL:
                        replies += bytes([IAC, DONT, opt])
                    elif cmd == DO:
                        replies += bytes([IAC, WONT, opt])
                    i += 3
                    continue
                if cmd == SB:
                    se_idx = buf.find(bytes([IAC, SE]), i)
                    if se_idx == -1:
                        break  # wait for the rest of the subnegotiation
                    i = se_idx + 2
                    continue
                # GA, NOP, and other bare 2-byte commands: consume, ignore
                i += 2
                continue
            text.append(b)
            i += 1
        self._buf = buf[i:]
        clean = ANSI_RE.sub(b"", bytes(text))
        return clean.decode("latin-1", errors="replace"), bytes(replies)


class MudSession:
    def __init__(self, host, port, log_path):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(0.5)
        self.parser = TelnetParser()
        self.buffer = ""
        self.lock = threading.Lock()
        self.last_recv = time.time()
        self.alive = True
        self.log_file = open(log_path, "a", buffering=1)
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        while self.alive:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                self.alive = False
                break
            text, replies = self.parser.feed(chunk)
            if replies:
                try:
                    self.sock.sendall(replies)
                except OSError:
                    pass
            if text:
                with self.lock:
                    self.buffer += text
                    self.last_recv = time.time()
                self.log_file.write(text)

    def send_line(self, line):
        self.sock.sendall(line.encode("latin-1", errors="replace") + b"\r\n")

    def take_new(self):
        with self.lock:
            out, self.buffer = self.buffer, ""
        return out

    def wait_quiet(self, quiet=0.4, max_wait=5.0):
        start = time.time()
        while True:
            time.sleep(0.1)
            with self.lock:
                idle = time.time() - self.last_recv
            if idle >= quiet or time.time() - start >= max_wait or not self.alive:
                return

    def wait_for(self, needles, timeout=10):
        """Block until one of `needles` has appeared in freshly-received
        text, or timeout. Returns (and consumes) everything seen so far."""
        start = time.time()
        seen = ""
        while time.time() - start < timeout and self.alive:
            seen += self.take_new()
            if any(needle in seen for needle in needles):
                return seen
            time.sleep(0.1)
        return seen


GAME_PROMPT_MARKER = "V ("  # e.g. "21H 100M 83V (news) (motd) >" — appears once in game


def login(session, username, password):
    """Log in as `username`. Handles both a fresh login (name -> password ->
    press-return -> character menu -> "enter game") and reconnecting to a
    character that's already in-game from a previous, still-linked session
    (the server drops straight into the game with "Reconnecting.")."""
    transcript = ""
    transcript += session.wait_for(["By what name"])
    session.send_line(username)
    transcript += session.wait_for(["Password:"])
    session.send_line(password)
    chunk = session.wait_for(
        ["PRESS RETURN", "Make your choice", "Reconnecting", GAME_PROMPT_MARKER],
        timeout=8,
    )
    transcript += chunk
    if "Reconnecting" in chunk or GAME_PROMPT_MARKER in chunk:
        return transcript  # already back in the game, no menu shown
    if "Make your choice" not in chunk:
        session.send_line("")
        chunk = session.wait_for(
            ["Make your choice", "Reconnecting", GAME_PROMPT_MARKER], timeout=8
        )
        transcript += chunk
        if "Reconnecting" in chunk or GAME_PROMPT_MARKER in chunk:
            return transcript
    session.send_line("1")
    transcript += session.wait_for([GAME_PROMPT_MARKER], timeout=8)
    return transcript


# --- daemon-side control socket ---

def handle_conn(conn, session):
    try:
        conn.settimeout(10)
        data = b""
        while not data.endswith(b"\n"):
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        req = json.loads(data.decode("utf-8"))
        action = req.get("action")
        if action == "send":
            command = req.get("command", "")
            session.take_new()
            if command:
                session.send_line(command)
            session.wait_quiet()
            resp = {"ok": True, "output": session.take_new(), "alive": session.alive}
        elif action == "read":
            session.wait_quiet(quiet=0.3, max_wait=req.get("max_wait", 2.0))
            resp = {"ok": True, "output": session.take_new(), "alive": session.alive}
        elif action == "stop":
            resp = {"ok": True, "output": "", "alive": session.alive}
            conn.sendall((json.dumps(resp) + "\n").encode())
            conn.close()
            session.alive = False
            try:
                session.sock.close()
            except OSError:
                pass
            os._exit(0)
        else:
            resp = {"ok": False, "error": f"unknown action {action!r}"}
        conn.sendall((json.dumps(resp) + "\n").encode())
    except Exception as e:  # keep the daemon alive even if one request is malformed
        try:
            conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode())
        except OSError:
            pass
    finally:
        conn.close()


def serve_control(session, sock_path):
    if os.path.exists(sock_path):
        os.remove(sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(5)
    srv.settimeout(1.0)
    while session.alive:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=handle_conn, args=(conn, session), daemon=True).start()
    srv.close()
    if os.path.exists(sock_path):
        os.remove(sock_path)


def run_daemon(args):
    session = MudSession(args.host, args.port, LOG_PATH)
    login(session, args.username, args.password)
    if not session.alive:
        return
    serve_control(session, SOCK_PATH)


# --- CLI-side helpers ---

def ensure_runtime_dir():
    os.makedirs(RUNTIME_DIR, exist_ok=True)


def send_action(req, timeout=10):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
        c.settimeout(timeout)
        c.connect(SOCK_PATH)
        c.sendall((json.dumps(req) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = c.recv(4096)
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode("utf-8"))


def daemon_running():
    if not os.path.exists(SOCK_PATH):
        return False
    try:
        resp = send_action({"action": "read", "max_wait": 0.1}, timeout=3)
        return resp.get("ok", False)
    except (OSError, socket.timeout, ConnectionRefusedError, json.JSONDecodeError):
        return False


def cmd_start(args):
    ensure_runtime_dir()
    if daemon_running():
        print("[mud] Session already running.")
        return
    for p in (SOCK_PATH,):
        if os.path.exists(p):
            os.remove(p)
    open(LOG_PATH, "w").close()
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__),
         "--host", args.host, "--port", str(args.port),
         "--username", args.username, "--password", args.password,
         "_daemon"],
        stdout=open(DAEMON_STDOUT_PATH, "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 20
    while time.time() < deadline and not os.path.exists(SOCK_PATH):
        time.sleep(0.2)
    if not os.path.exists(SOCK_PATH):
        print("[mud] ERROR: daemon did not start in time. "
              f"Check {DAEMON_STDOUT_PATH}", file=sys.stderr)
        sys.exit(1)
    time.sleep(0.3)
    with open(LOG_PATH, "r", errors="replace") as f:
        print(f.read())


def cmd_send(args):
    if not daemon_running():
        print("[mud] No session running. Run `mud.py start` first.", file=sys.stderr)
        sys.exit(1)
    resp = send_action({"action": "send", "command": args.command}, timeout=args.wait + 5)
    print(resp.get("output", ""))
    if not resp.get("alive", True):
        print("[mud] (connection closed by server)", file=sys.stderr)


def cmd_read(args):
    if not daemon_running():
        print("[mud] No session running. Run `mud.py start` first.", file=sys.stderr)
        sys.exit(1)
    resp = send_action({"action": "read", "max_wait": args.wait}, timeout=args.wait + 5)
    print(resp.get("output", ""))


def cmd_status(args):
    print("[mud] Running." if daemon_running() else "[mud] Not running.")


def cmd_stop(args):
    if not daemon_running():
        print("[mud] Not running.")
        return
    try:
        send_action({"action": "send", "command": "quit"}, timeout=5)
    except (OSError, socket.timeout):
        pass
    try:
        send_action({"action": "stop"}, timeout=5)
    except (OSError, socket.timeout, ConnectionRefusedError):
        pass
    if os.path.exists(SOCK_PATH):
        os.remove(SOCK_PATH)
    print("[mud] Session stopped.")


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--username", default=DEFAULT_USERNAME)
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    sub = p.add_subparsers(dest="action", required=True)

    sub.add_parser("start", help="connect and log in, leaving the session running")

    sp = sub.add_parser("send", help="send one command and print the response")
    sp.add_argument("command", help="the command line to send, e.g. 'look' or 'n'")
    sp.add_argument("--wait", type=float, default=3.0,
                     help="max seconds to wait for output to settle (default 3)")

    rp = sub.add_parser("read", help="read output without sending a command")
    rp.add_argument("--wait", type=float, default=2.0,
                     help="max seconds to wait for new output (default 2)")

    sub.add_parser("status", help="report whether a session is running")
    sub.add_parser("stop", help="quit the game and shut the daemon down")
    sub.add_parser("_daemon", help=argparse.SUPPRESS)

    return p


def main():
    args = build_parser().parse_args()
    {
        "start": cmd_start,
        "send": cmd_send,
        "read": cmd_read,
        "status": cmd_status,
        "stop": cmd_stop,
        "_daemon": run_daemon,
    }[args.action](args)


if __name__ == "__main__":
    main()
