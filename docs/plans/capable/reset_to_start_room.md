# Week 3 (Capable) Plan — Reset Player to Start Room

## Problem

The `dummy` player character can end up anywhere in the world after a play
session (dead, stuck, wandered off) with no in-game way for the *player*
alone to relocate to a known-good room. tbaMUD/CircleMUD only exposes room
teleportation as an immortal (god-level) command — `teleport <victim>
<room_vnum>` — which requires the *issuer* to be a logged-in immortal and
the *target* to already be online in the world (the command acts on a live
player object, not an offline character file).

There's no existing tool for this in the repo: `mud_manager`'s MCP
primitives (`week0_explore/mud_manager/lib/mud_manager/primitives.rb`) wrap
only regular-player commands, and neither `boukensha` nor the MCP layer
supports running two simultaneous authenticated sessions against the MUD
(one player + one immortal) from a single invocation.

## Goal

A standalone script, `week3_capable/bin/reset`, that:

1. Opens two independent telnet connections to the MUD.
2. Logs the **player** account in on one connection (guarantees the target
   of `teleport` is actually online — the command fails against an offline
   character).
3. Logs the **admin** (immortal) account in on the second connection.
4. From the admin connection, issues `teleport <player_username>
   <start_room>` (default `teleport dummy 3001` — room 3001 is *The Temple
   Of Midgaard*, tbaMUD's canonical starting room).
5. Confirms the player landed in the target room, then cleanly disconnects
   both sessions.

Usage (per the plan file spec):

```
week3_capable/bin/reset
```

or with overrides:

```
ADMIN_USERNAME=admin ADMIN_PASSWORD=password \
PLAYER_USERNAME=dummy PLAYER_PASSWORD=helloworld \
MUD_HOST=localhost MUD_PORT=4000 START_ROOM=3001 \
week3_capable/bin/reset
```

All config comes from environment variables with defaults matching the
repo's existing `dummy`/`helloworld` fixture (`.boukensha/settings.yaml`) —
no CLI flags, no config file, matching the plan file's usage example
exactly.

| Env var            | Default     |
|---------------------|-------------|
| `MUD_HOST`           | `localhost` |
| `MUD_PORT`           | `4000`      |
| `PLAYER_USERNAME`    | `dummy`     |
| `PLAYER_PASSWORD`    | `helloworld`|
| `ADMIN_USERNAME`     | `admin`     |
| `ADMIN_PASSWORD`     | `password`  |
| `START_ROOM`         | `3001`      |

## Where the new code lives

```
week3_capable/
├── bin/
│   └── reset            # new — standalone, executable, no wrapper needed
└── python/
    └── tool_scoping/     # unrelated, untouched by this plan
```

`reset` is **not** part of the `tool_scoping` boukensha package — it has no
dependency on `boukensha`, `Config`, MCP, or the Anthropic API. It's a
self-contained Python 3 stdlib script (`socket`, `threading`, `re`, `os`,
`sys`, `time` only — no venv, no `pip install`, no third-party deps), same
spirit as the standalone telnet client already in this repo at
`week0_explore/explore_architecture/02_agent_skills/.claude/skills/play-mud/scripts/mud.py`.
That script is the reference for the telnet/login mechanics below (IAC
stripping, the `By what name…` → password → menu → `1` login dance, and the
`Reconnecting`/`already in use` tolerant branch) — trimmed down here since
`reset` doesn't need mud.py's background-daemon/control-socket machinery.
It runs once, synchronously, start to finish, then exits.

## Design

### 1. Telnet plumbing (adapted from `play-mud/scripts/mud.py`)

Reuse, inline (not imported — different track, keep `reset` dependency-free
and single-file):

- `TelnetParser` — strips IAC negotiation + ANSI color codes, replies
  `WONT`/`DONT` to any `WILL`/`DO` so the server settles into plain text.
- A `Connection` class: opens the socket, runs a background reader thread
  into a buffered string, exposes `send_line(text)`, `wait_for(needles,
  timeout)`, and `take_new()` — same shape as `mud.py`'s `MudSession`,
  minus the Unix-socket daemon/control-plane parts (not needed for a
  script that just runs to completion once).

### 2. Login handshake

Both sessions use the same login sequence (mirrors `mud.py`'s `login()` /
`mud_manager/session.rb`'s `#login`):

```python
# Same sentinel mud_manager/session.rb's PROMPT_SENTINEL uses against the
# real tbaMUD -- every command response ends in "> ". Implementation found
# that mud.py's more specific "V (" vitals-bar marker (tuned for its own
# long-running daemon against the real MUD) never appears in FakeMud's
# plain "> " prompt, breaking the offline test entirely -- switched to this
# simpler, already-proven-safe sentinel so the same code path is exercised
# against both real and fake.
GAME_PROMPT_MARKER = "> "
```

**Resolved (user decision):** logging the player in here will *hijack* any
already-connected session for that same character (a running `boukensha`
play session, or a manual telnet session) — CircleMUD kicks the old
connection with "You take over your own body, already in use!" the moment
a second login for the same name succeeds. There's no way to check "is
this name currently online" *before* attempting login — the server's
response to the login attempt is itself the only signal — so `login()`
returns whether the transcript indicated a takeover (`"already in use"` or
`"Reconnecting"` present), and `main()` prints a clear warning to stderr
when it did, rather than either silently proceeding or trying to block the
hijack outright:

```python
def login(conn, username, password):
    """Mirrors mud_manager/session.rb's #login -- the field-proven
    implementation this repo already uses against the real tbaMUD -- rather
    than mud.py's more defensive "PRESS RETURN"/"Make your choice"
    conditional dance. Implementation found that dance assumes menu prompt
    text FakeMud never sends (it just blocks on two raw `gets` calls), which
    made login stall ~16s per session against the fake; session.rb's
    simpler shape (wait for "Welcome", then unconditionally send return + 1)
    matches both the fake and the real server, since the real server's
    reply here is also just "Welcome, name.\r\n" with no menu banner.
    Returns True if this login took over an already-connected session for
    the same name (a running boukensha play session, another telnet
    client, etc.) rather than starting fresh."""
    conn.wait_for(["By what name"])
    conn.send_line(username)
    conn.wait_for(["Password:"])
    conn.send_line(password)
    chunk = conn.wait_for(
        ["Welcome", "Reconnecting", "already in use", "Wrong password"],
        timeout=8,
    )
    if "Wrong password" in chunk:
        raise LoginError(f"{username}: wrong password")
    if "Reconnecting" in chunk or "already in use" in chunk:
        return True  # already in-world, dropped straight into the game
    conn.send_line("")   # press return past the banner, at the main menu
    conn.send_line("1")  # enter the game
    conn.wait_for([GAME_PROMPT_MARKER], timeout=8)
    return False
```

### 3. Main flow

```python
def main():
    cfg = read_config_from_env()  # dict, defaults per the table above

    player = Connection(cfg["host"], cfg["port"])
    print(f"[reset] connecting as player '{cfg['player_username']}'...")
    hijacked = login(player, cfg["player_username"], cfg["player_password"])
    if hijacked:
        print(f"[reset] WARNING: '{cfg['player_username']}' was already "
              "connected elsewhere — that session has just been "
              "disconnected/taken over.", file=sys.stderr)
    print("[reset] player online.")

    admin = Connection(cfg["host"], cfg["port"])
    print(f"[reset] connecting as admin '{cfg['admin_username']}'...")
    login(admin, cfg["admin_username"], cfg["admin_password"])
    print("[reset] admin online.")

    cmd = f"teleport {cfg['player_username']} {cfg['start_room']}"
    print(f"[reset] admin> {cmd}")
    admin.send_line(cmd)
    response = admin.wait_for([GAME_PROMPT_MARKER], timeout=8)
    print(response)

    player.send_line("look")
    look = player.wait_for([GAME_PROMPT_MARKER], timeout=8)
    print(look)
    if "temple of midgaard" not in look.lower() and cfg["start_room"] == "3001":
        print("[reset] WARNING: player's `look` output doesn't mention "
              "Temple Of Midgaard — check the transcript above.", file=sys.stderr)

    for conn, name in ((player, "player"), (admin, "admin")):
        conn.send_line("quit")
        conn.wait_for(["neither"], timeout=5)  # best-effort drain, ignore result
        conn.close()

    print("[reset] done.")

if __name__ == "__main__":
    main()
```

Notes on judgment calls baked into this design (flag for review, not
presented as already resolved with the user):

- **Success is reported by printing the raw transcript, not by pattern-
  matching an exact tbaMUD success string.** I don't have the tbaMUD
  `do_teleport` source in this repo to confirm its exact confirmation
  message (e.g. "Okay." vs. something else), so asserting on it risks a
  false failure on correct behavior. The script prints what the admin
  connection actually saw and follows up with a `look` from the player's
  own connection — checking for "Temple Of Midgaard" in *that* output is a
  much safer signal since the room's `look` text is world data already
  confirmed in `week0_explore/preview/web/public/data/rooms.json`/the
  parsed world files, not a guess about server source code. A mismatch
  prints a warning but doesn't fail the script outright — the user reviews
  the printed transcript either way.
- **Both sessions `quit` (not just socket-close) at the end**, so tbaMUD's
  normal quit path saves the character file with the new room position —
  otherwise a plain disconnect risks the position only being persisted on
  the *next* autosave tick or clean logout, not immediately.
- Exit code: non-zero only on a genuine connection/login failure for
  either account (refused connection, wrong password, timeout before the
  game prompt appears) — not on the room-name heuristic warning, since
  that's informational, not a confirmed failure.

### 4. Script header / permissions

```python
#!/usr/bin/env python3
"""
Reset the player character to a known starting room using an immortal
`teleport` command.

The player must be online for `teleport` to affect them, so this script
logs in two separate telnet sessions — the player account (to guarantee
they're in-world) and an admin/immortal account (to issue the god command)
— then disconnects both.

Usage:
    week3_capable/bin/reset

Env vars (all optional, defaults shown):
    MUD_HOST=localhost  MUD_PORT=4000
    PLAYER_USERNAME=dummy  PLAYER_PASSWORD=helloworld
    ADMIN_USERNAME=admin   ADMIN_PASSWORD=password
    START_ROOM=3001
"""
```

`chmod +x week3_capable/bin/reset` so the usage line (`week3_capable/bin/reset`,
no `python3` prefix) works as-is.

### 5. Offline test harness — extend `fake_mud.rb`

`week0_explore/mud_manager/lib/mud_manager/fake_mud.rb` today only knows one
hardcoded account (`Gandalf`/`secret`, shared by whoever connects) and a
generic `"You do: <line>"` echo — no second "immortal" identity, no
`teleport` verb, no per-player room state. `reset` needs two distinct
accounts (player + admin) and a `teleport`/`look` pair that actually
affects shared state, so this is a small, backward-compatible extension:

```ruby
class FakeMud
  DEFAULT_USERNAME = "Gandalf".freeze
  DEFAULT_PASSWORD = "secret".freeze
  ROOM_DESCRIPTIONS = Hash.new("A featureless void.").merge(
    "3001" => "The Temple Of Midgaard\r\nA huge open area with roads leading in all directions.",
  ).freeze

  def initialize(accounts: {DEFAULT_USERNAME => DEFAULT_PASSWORD})
    @accounts  = accounts
    @rooms     = Hash.new("0")   # username -> room vnum, shared across sessions
    @rooms_mu  = Mutex.new
    @active    = {}              # username -> socket currently logged in as that name
    @active_mu = Mutex.new
    ...
  end

  private

  def handle_client(sock)
    sock.write("By what name do you wish to be known? ")
    name = sock.gets&.strip
    return if name.nil?

    sock.write("\r\nPassword: ")
    password = sock.gets&.strip

    if @accounts[name] == password
      # A second login for a name that's already connected kicks the old
      # connection, same as real CircleMUD's "already in use" takeover --
      # added during implementation so the offline test could exercise the
      # hijack-warning path (Design section 2) without a live MUD at all.
      previous = @active_mu.synchronize { @active[name] }
      if previous
        previous.write("\r\nYou take over your own body, already in use!\r\n") rescue nil
        previous.close rescue nil
        sock.write("\r\nReconnecting. You take over your own body, already in use!\r\nYou materialize in the fake MUD.\r\n> ")
      else
        sock.write("\r\nWelcome, #{name}.\r\n")
        sock.gets  # <return> at the main menu
        sock.gets  # "1": enter the game
        sock.write("\r\nYou materialize in the fake MUD.\r\n> ")
      end
      @active_mu.synchronize { @active[name] = sock }
      echo_loop(sock, name)
    else
      sock.write("\r\nWrong password.\r\n")
    end
  ensure
    @active_mu.synchronize { @active.delete(name) if name && @active[name].equal?(sock) }
    sock.close rescue nil
  end

  def echo_loop(sock, name)
    loop do
      line = sock.gets&.strip
      break if line.nil?

      case line
      when /\Ateleport\s+(\S+)\s+(\S+)/i
        target, room = $1, $2
        @rooms_mu.synchronize { @rooms[target] = room }
        sock.write("Okay.\r\n> ")
      when /\Alook/i
        room = @rooms_mu.synchronize { @rooms[name] }
        sock.write("\r\n#{ROOM_DESCRIPTIONS[room]}\r\n> ")
      else
        sock.write("You do: #{line}\r\n> ")
      end
    end
  end
end
```

`accounts:` defaults to today's single-pair behavior, so every existing
zero-arg `MudManager::FakeMud.new` call site (`week1_baseline/ruby/*/test/helper.rb`,
every `examples/mcp_mud_demo.{py,rb}` across both language tracks) keeps
working unchanged — this is additive, not a breaking signature change.
The shared `@rooms` hash (mutex-guarded — `handle_client` runs each
connection on its own thread) is what makes the offline test genuinely
end-to-end: the admin session's `teleport` and the player session's `look`
are two different sockets, two different threads, coordinating through the
same in-memory state, the same way two real telnet sessions coordinate
through the live MUD's actual player-object table.

**Offline test:** `week3_capable/tests/test_reset_dry.py` (new), following
the same spawn pattern `mcp_mud_demo.py`'s `start_fake_mud()` already
establishes (a throwaway `ruby -e` subprocess hosting `FakeMud`, port
printed to stdout, blocks on stdin) — except this one passes
`accounts: {"dummy" => "helloworld", "admin" => "password"}` so the fake
matches `reset`'s own defaults exactly:

```python
script = (
    "$LOAD_PATH.unshift '{lib}'\n"
    "require 'mud_manager/fake_mud'\n"
    "fake = MudManager::FakeMud.new(accounts: {{\"dummy\" => \"helloworld\", \"admin\" => \"password\"}})\n"
    "STDOUT.puts(fake.port)\n"
    "STDOUT.flush\n"
    "STDIN.gets\n"
    "fake.stop\n"
).format(lib=MUD_MANAGER_ROOT / "lib")
```

Then run the *actual* `week3_capable/bin/reset` executable as a subprocess
(not a reimplementation, not an internal `--dry` branch inside `reset`
itself — the real shipped script, pointed at the fake via env vars):

```python
result = subprocess.run(
    ["week3_capable/bin/reset"],
    env={**os.environ, "MUD_HOST": "127.0.0.1", "MUD_PORT": str(fake_port),
         "PLAYER_USERNAME": "dummy", "PLAYER_PASSWORD": "helloworld",
         "ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "password",
         "START_ROOM": "3001"},
    capture_output=True, text=True, timeout=30,
)
assert "temple of midgaard" in result.stdout.lower()
assert result.returncode == 0
```

A second case connects a throwaway third socket as `dummy` *before*
running `reset`, to exercise the hijack-warning path from Design section 2
— asserts the "already connected elsewhere" warning shows up on stderr.

## Testing / Verification

1. **Offline, via the extended `fake_mud.rb`** (Design section 5) — run
   `week3_capable/tests/test_reset_dry.py`: no live MUD, no network
   dependency beyond localhost, exercises the full login → teleport →
   look round trip plus the hijack-warning path, entirely repeatable.
2. **Live, against the real local tbaMUD on `localhost:4000`** — the
   admin/immortal account already exists (confirmed), so no manual setup
   step is needed here:
   1. Move `dummy` away from room 3001 (walk a few rooms, or let it die).
   2. Run `week3_capable/bin/reset`, read the printed transcript.
   3. Separately reconnect as `dummy` (e.g. via the `play-mud` skill) and
      confirm `look` shows *The Temple Of Midgaard*.

## Task list

1. `mkdir -p week3_capable/bin`.
2. Write `week3_capable/bin/reset` per Design sections 1–4 (self-contained
   Python 3 stdlib script: `TelnetParser`, `Connection`, `login()` with
   hijack-detection return value, `main()`, env-var config with the
   defaults table above).
3. `chmod +x week3_capable/bin/reset`.
4. Extend `week0_explore/mud_manager/lib/mud_manager/fake_mud.rb` per
   Design section 5: `accounts:` kwarg (backward-compatible default),
   shared mutex-guarded `@rooms` state, `teleport`/`look` handling in
   `echo_loop`.
5. Write `week3_capable/tests/test_reset_dry.py` per Design section 5:
   spawn the extended fake, run the real `week3_capable/bin/reset` as a
   subprocess against it, assert success plus the hijack-warning case.
6. Run the offline test; fix forward until it passes.
7. Live smoke test: move `dummy` off room 3001, run the script against the
   real MUD, confirm via a separate session that `look` reports *The
   Temple Of Midgaard*.
8. Don't commit until the user reviews.

## Resolved decisions

1. **The `admin` immortal account already exists** on the local tbaMUD —
   no account-creation step needed before this can be exercised live.
2. **Hijacking an already-connected `dummy` session is allowed, but
   flagged** — `reset` proceeds (there's no way to check "is this name
   online" without attempting the login itself) and prints a clear warning
   to stderr when the login transcript shows a takeover occurred, per
   Design section 2.
3. **Offline testing via `fake_mud.rb` is in scope**, not deferred as
   optional — Design section 5 and Task list items 4–6.