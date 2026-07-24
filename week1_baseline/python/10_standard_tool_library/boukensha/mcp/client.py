import json
import os
import subprocess

import boukensha


class Client:
    """A minimal MCP-over-stdio client: it spawns an MCP server as a
    subprocess, performs the initialize handshake, and lets you discover and
    call the tools it advertises. It knows nothing about any particular
    server -- command, args, and env are the standard stdio transport config.

        client = boukensha.mcp.Client.spawn(command="mud-manager", args=["--mcp"])
        for t in client.tools:
            print(t["name"])
        print(client.call_tool("look")["text"])
        client.close()
    """

    class Error(Exception):
        pass

    PROTOCOL_VERSION = "2025-06-18"

    @classmethod
    def spawn(cls, *, command, args=None, env=None):
        return cls(command=command, args=args, env=env)

    def __init__(self, *, command, args=None, env=None):
        cmd = [str(command)] + [str(a) for a in (args or [])]
        # A spawned server inherits this process's environment; `env` layers
        # extra/overriding keys on top -- matching Ruby's Open3.popen3(env, *cmd)
        # merge semantics, not a full environment replacement (Python's
        # subprocess.Popen(env=...) replaces wholesale unless we merge it
        # ourselves here).
        merged_env = dict(os.environ)
        merged_env.update({str(k): str(v) for k, v in (env or {}).items()})

        self._process = subprocess.Popen(
            cmd,
            env=merged_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._id = 0
        self._handshake()
        self.tools = self._fetch_tools()

    def call_tool(self, name, arguments=None):
        res = self._request("tools/call", {"name": str(name), "arguments": arguments or {}})
        result = res.get("result")
        if result is None:
            raise self.Error("tools/call error: {!r}".format(res.get("error")))
        text = "\n".join(
            c["text"] for c in (result.get("content") or []) if c.get("text") is not None
        )
        return {"text": text, "error": bool(result.get("isError"))}

    def close(self):
        try:
            self._process.stdin.close()
        except Exception:
            pass
        self._process.wait()
        try:
            self._process.stdout.close()
        except Exception:
            pass
        try:
            self._process.stderr.close()
        except Exception:
            pass

    # ---------- private -----------------------------------------------

    def _handshake(self):
        res = self._request("initialize", {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "boukensha", "version": boukensha.VERSION},
        })
        self.server_info = (res.get("result") or {}).get("serverInfo")
        self._notify("notifications/initialized")

    def _fetch_tools(self):
        return (self._request("tools/list").get("result") or {}).get("tools") or []

    def _request(self, method, params=None):
        self._id += 1
        request_id = self._id
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        return self._read_until(request_id)

    def _notify(self, method, params=None):
        self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _write(self, obj):
        self._process.stdin.write(json.dumps(obj) + "\n")
        self._process.stdin.flush()

    def _read_until(self, request_id):
        while True:
            line = self._process.stdout.readline()
            if line == "":
                raise self.Error("server closed the connection")
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("id") == request_id:
                return msg
            # ignore server-initiated notifications / mismatched ids
