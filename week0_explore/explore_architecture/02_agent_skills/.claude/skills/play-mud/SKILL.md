---
name: play-mud
description: Play the local tbaMUD (CircleMUD-family) text MUD running on localhost:4000, logging in as the existing character "dummy", and pursue longer-term goals (like reaching a target level or hunting down a specific monster) across sessions using persistent memory files. Use this skill whenever the user asks to play, explore, fight, level up, grind, or otherwise interact with the MUD, the game on port 4000, "the dummy character", or gives in-game commands like "go north", "attack the rat", "check my inventory/score", or "log into the mud and look around" — even if they don't say "MUD" explicitly, as long as it's clearly about this text game. Also use it for goal-setting ("get dummy to level 7", "hunt down the orc king"), for checking progress toward a standing goal, or to check on or wrap up a session ("what's happening in the game", "log out of the mud").
---

# Playing tbaMUD

This skill drives a live telnet session against a tbaMUD server (a CircleMUD/DikuMUD-family MUD) at `127.0.0.1:4000`, using the existing character **dummy** / **helloworld**. It also maintains persistent memory across sessions in `data/player.md` and `data/world.md`, so long-running goals (reach level N, defeat a specific monster) can survive across separate conversations instead of resetting every time.

MUDs are real-time, stateful, and turn on side effects (combat rounds, other players, room state) — you can't just fire off a fresh connection per command. `scripts/mud.py` runs a small background daemon that holds the telnet connection open, handles telnet protocol negotiation and ANSI color codes for you, and lets you interact with it as a simple send-a-command / read-the-response loop.

## Commands

Run these from anywhere (the script resolves its own paths):

```
python3 scripts/mud.py start              # connect + log in as dummy; leaves session running
python3 scripts/mud.py send "<command>"   # send one game command, print the response
python3 scripts/mud.py read [--wait N]    # read output without sending anything (default wait 2s)
python3 scripts/mud.py status             # is a session currently running?
python3 scripts/mud.py stop               # quit the game and shut the session down
```

`start` is idempotent — if a session is already running it just reports that and does nothing. If a session was left connected from a previous conversation (character still "linked"), `start` reconnects to it and shows you where the character currently is, rather than erroring.

## Memory files

Two files under `data/` (relative to this skill's own directory, not the cwd) persist what's been learned across sessions:

- **`data/player.md`** — the character's stats, inventory, equipment, known skills, current location, and a **Goals** section (Active / Completed) that tracks any standing objective the user has set, like "reach level 7" or "defeat the orc king."
- **`data/world.md`** — a running map of rooms discovered so far (name, exits, notable NPCs/hazards), a monster table (name, location, rough difficulty), and shops/services. This is what lets the character go straight back to a known monster or shop instead of re-exploring Midgaard from scratch every time.

Read both files at the start of a session, right after `start`, so decisions are grounded in what's actually known rather than guessed. Treat them as a rough map, not gospel — the game world can have more than what's recorded, and status effects/inventory can be stale if it's been a while since the last update.

**When to write to them** — not after every single command (that's noisy and wastes effort chasing a moving target); update at natural checkpoints instead:
- Leveling up, or any other change to the Status block in `player.md`.
- Defeating, locating, or learning something new about a monster tied to an active goal.
- Discovering a room, shop, or monster not already in `world.md` — append it, don't rewrite the whole file.
- Whenever a goal's status changes (started, progressed meaningfully, completed) — update the Goals section in `player.md`.
- Right before calling `stop`, sync `player.md`'s Status block (`score`, `i`, current room) so the next session starts from accurate information.

## Goal-driven play

When the user sets a standing goal ("get to level 7", "hunt down and defeat the swamp troll"), add it to the **Active** goals list in `player.md` with whatever's known so far (target, current progress, any location info). From then on, that goal should persist across conversations until it's marked Completed or the user changes it — check `player.md` for existing active goals at the start of a session even if the user's current message doesn't mention one.

Working toward a goal:
- Act with reasonable autonomy on tactics — which room to move to, which weak monster to grind on, when to `flee` a losing fight, when to rest and let HP/mana regen. These are reversible, low-stakes decisions; don't stop to ask permission for each one.
- Check in with the user before higher-stakes strategic calls: heading into a notably dangerous area (see `world.md`'s Danger Notes) to chase a specific target, spending significant gold, or any point where the character's death or major setback is a real possibility.
- A single session won't grind out "level 1 to 7" in one sitting — that's expected. Make honest, visible progress (a few levels, or scouting a target monster's location), update the memory files, and report progress plainly (e.g. "now level 3, 400xp short of level 4; haven't located the orc king yet — `world.md` has no sighting recorded").
- If a goal target (a specific named monster) hasn't been located yet, exploring to find it and recording its location in `world.md`'s Monsters table is itself progress worth stopping on and reporting, not something to hide until it's defeated.

## Playing

1. Call `start` first. Read its output — it's the room the character is currently standing in (or the full login banner on a fresh login). Orient from that description before doing anything else. Then read `data/player.md` and `data/world.md` to recall stats, goals, and what's already known about the world.
2. Issue one command at a time via `send` and read the result before deciding the next command — treat it like you're actually playing, not scripting blind. Common commands: movement (`n`/`s`/`e`/`w`/`u`/`d`), `look`, `look <thing>`, `inventory` / `i`, `score` / `sc`, `kill <target>`, `get <item>`, `wear <item>`, `wield <item>`, `say <text>`, `who`.
3. Watch the status line at the end of most responses: `<HP>H <Mana>M <Move>V (news) (motd) >`. HP is hit points — if it's dropping fast in combat and getting low relative to the character's max (shown via `score`), retreat (flee or move away) rather than pushing on turns already in motion.
4. Some things happen without you sending a command — an NPC's attack lands on the next round, another player says something, movement/regen ticks. If you sent a command and the response seems incomplete, or you want to watch for something after a fight ends, use `read --wait 3` (or a longer wait) instead of guessing with another `send`.
5. When done, call `stop` to `quit` the character out cleanly. Before doing so, sync the memory files per the checkpoints above. If you don't quit, the character stays linked in the game world and the next `start` will simply reconnect to wherever it was left — that's fine for a short pause, but leaving combat mid-fight or in a dangerous room is a bad idea for the character.

## Notes

- The daemon strips ANSI color codes and telnet IAC negotiation bytes for you — what you see in `send`/`read` output is plain text.
- Only one session runs at a time (single character). Don't try to run `start` in parallel from multiple places.
- If `send`/`read`/`status` report no session running, call `start` again — the daemon may have exited (e.g. server restarted, connection dropped).
