# Week 3 (Capable) Plan — Map Zone 30 (Northern Midgaard) for Efficient Navigation

## Problem

Right now the only way `dummy` can reach a named location ("the Bakery") is
by wandering: issue `move` one direction at a time, `look` after each hop,
and let the agent guess. There's no map, so every trip costs however many
LLM turns it takes to stumble there, and there's no way to ask "how many
rooms away is X."

**Room numbers (vnums) are not exposed anywhere in-game.** Neither the raw
tbaMUD server nor any of `mud_manager`'s 55 primitives
(`week0_explore/mud_manager/lib/mud_manager/primitives.rb`) ever surfaces a
room's vnum to a connected player — `look`/`examine`/`where` give room
*names* and text descriptions only. This plan's mapping method (per
explicit instruction) works around that in two clearly separated phases:

1. **Build the map by actually walking the MUD** — no world files read
   during this phase at all. Each newly-discovered room is assigned a
   plain sequential number (1, 2, 3, ...) in the order it's first visited,
   the same way you'd draw a map on paper while exploring a building with
   the room numbers papered over.
2. **Afterward**, cross-reference the completed room-by-room dictionary
   against the MUD's own world-file docs (parsed via
   `week0_explore/circlemud-world-parser`, the only source of real vnums
   in this repo) purely to look up each already-discovered room's real
   room number, adding it as one more key on that room's existing entry.
   The world files never inform *what the rooms are or how they connect*
   — only what number a given, already-identified room happens to have.

## Goal

1. A `scripts/crawl_zone.py` that drives the real MUD (via `mud_manager`'s
   `move`/`look` MCP tools, no LLM involved — pure scripted control flow,
   so no API cost) and builds `data/zone_30_crawl.json`: every room
   reachable from the starting point, numbered in discovery order, with
   its name, description, and exits (direction → discovery-order number of
   the room on the other side, or `null` if that direction has no exit).
2. A `scripts/cross_reference.py` that reads that file plus a fresh parse
   of the real `.wld` world file, matches each discovered room to its real
   vnum by name (and, for the zone's several duplicate room names, by
   exit-topology matching against already-resolved neighbors — see Design
   section 4), and writes `data/zone_30.json`: the same room entries, each
   now carrying one extra key, `"vnum"`.
3. An in-memory graph + BFS shortest-path search over that data (58 rooms
   is small — no database needed; see Design section 5), and a `goto_room`
   tool wired into `boukensha` so "go to the Bakery" becomes a computed
   path + a sequence of `move` calls instead of wandering, reachable from
   the real interactive app (`bin/boukensha`), not just a demo script.

Per the task, all new Python code lives at `week3_capable/python/map_zone`.

## Design

### 1. The crawl: discovering rooms by walking, not by reading files

The crawl is a scripted depth-first walk, driven directly through
`mud_manager`'s MCP `move`/`look` tools (same `boukensha.tools.mcp.register`
path `examples/mcp_mud_demo.py` already uses) — no Anthropic API call
anywhere in this script, so it costs nothing to run and re-run:

- **Identity, without vnums:** a room is "the same room" if its `(name,
  description)` pair matches one already seen. Name alone isn't enough —
  Zone 30 is known (from separate, earlier inspection of this repo's data
  used only to sanity-check this design, not used as the mapping source)
  to have several genuinely different rooms sharing a name (e.g. multiple
  "Main Street" segments) — but each such room's full description text
  differs, since CircleMUD room text is hand-authored per room. `(name,
  description)` is treated as the room's signature.
- **Does a direction have an exit? Try it and look, don't parse the exits
  line.** Rather than parsing `look`'s `[ Exits: ... ]` line (fragile —
  its exact formatting/coloring isn't verified anywhere in this repo) the
  crawler just attempts `move` in all six directions
  (`north/south/east/west/up/down` — `mud_manager`'s full `DIRECTIONS`
  set) from every room and compares the room signature before and after:
  if it's unchanged, that direction has no exit (or is blocked); if it
  changed, the move succeeded and the new signature is looked up or
  registered as a new numbered room. This is slower (up to 6 attempts per
  room instead of ~2–4) but doesn't depend on guessing the exact
  success/failure wording the live server uses — content comparison is
  strictly more robust than string matching a response we haven't
  confirmed.
- **Backtracking:** after fully exploring a newly-discovered room's own
  frontier (recursively, depth-first), the crawler returns to whichever
  room it came from via the reverse direction
  (`north↔south`, `east↔west`, `up↔down`) so it can keep exploring that
  parent room's remaining directions. This assumes exits in this zone are
  bidirectional — true for ordinary town layouts, but not guaranteed by
  the MUD in general. If a return move ever fails, the script raises
  loudly (`CrawlStuckError`) rather than silently producing a wrong map;
  see Design section 3 for the recovery path.

```python
DIRECTIONS = ("north", "south", "east", "west", "up", "down")
REVERSE = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}


def parse_look(text):
    lines = [ANSI_RE.sub("", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    name = lines[0] if lines else ""
    desc = "\n".join(lines[1:])  # includes exits/contents lines -- fine, they're part of the signature too
    return name, desc


class Crawler:
    def __init__(self, registry):
        self.registry = registry
        self.rooms = {}            # temp_id -> {"name":, "desc":, "exits": {dir: temp_id|None}}
        self.signature_to_id = {}  # (name, desc) -> temp_id
        self.next_id = 1

    def visit_current_room(self):
        name, desc = parse_look(self.registry.dispatch("look", {}))
        sig = (name, desc)
        if sig in self.signature_to_id:
            return self.signature_to_id[sig], False
        temp_id = self.next_id
        self.next_id += 1
        self.signature_to_id[sig] = temp_id
        self.rooms[temp_id] = {"name": name, "desc": desc, "exits": {}}
        return temp_id, True

    def explore(self, temp_id):
        for direction in DIRECTIONS:
            if direction in self.rooms[temp_id]["exits"]:
                continue
            self.registry.dispatch("move", {"direction": direction})
            after_id, is_new = self.visit_current_room()
            if after_id == temp_id:
                self.rooms[temp_id]["exits"][direction] = None  # no exit that way
                continue
            self.rooms[temp_id]["exits"][direction] = after_id
            if is_new:
                self.explore(after_id)
            back_id, _ = (self.registry.dispatch("move", {"direction": REVERSE[direction]}), self.visit_current_room())[1]
            if back_id != temp_id:
                raise CrawlStuckError(
                    "room {}: moving {} then {} landed in room {}, not back in {} -- "
                    "a one-way exit or something moved us mid-crawl (a random encounter, "
                    "e.g.) -- stopping rather than recording a wrong map".format(
                        temp_id, direction, REVERSE[direction], back_id, temp_id
                    )
                )

    def run(self):
        start_id, _ = self.visit_current_room()
        self.explore(start_id)
        return self.rooms
```

### 2. Running the crawl against the real MUD

`scripts/crawl_zone.py` builds its own throwaway `Context`/`Registry` and
registers **only** `move` and `look` directly (bypassing
`.boukensha/settings.yaml` entirely — this is a one-off offline tool, not
part of the agent's runtime tool surface, so it doesn't need or want the
shared config's `tools:` filter):

```python
import boukensha
from boukensha.tools import mcp as tools_mcp

ctx = boukensha.Context(system="zone crawl")
registry = boukensha.Registry(ctx)
tools_mcp.register(
    registry, command="ruby",
    args=[str(MUD_MANAGER_BIN), "--mcp"],
    env={"MUD_HOST": "localhost", "MUD_PORT": "4000", "MUD_NAME": "dummy", "MUD_PASSWORD": "helloworld"},
    prefix=None,
    tools={"move": {"enabled": True, "as": None}, "look": {"enabled": True, "as": None}},
)

rooms = Crawler(registry).run()
Path("data/zone_30_crawl.json").write_text(json.dumps(rooms, indent=2, sort_keys=True) + "\n")
```

**Starting position:** the crawl starts wherever `dummy` already is when
launched — the script doesn't itself force a known starting room. For a
clean, reproducible run, the operator runs the already-built
`week3_capable/bin/reset` first (teleports `dummy` to room 3001, the
Temple) and then runs the crawler — composing the two existing tools
rather than re-implementing teleport-to-known-room logic a second time.

**If the crawler gets stuck** (`CrawlStuckError` — a one-way exit, or
something else moved the character mid-crawl, e.g. a wandering mob
encounter): `week3_capable/bin/reset` again is the documented recovery —
teleport back to 3001 and re-run. The crawl is naturally idempotent
(`signature_to_id` means already-discovered rooms are recognized again
instantly), so a re-run after a reset just continues filling in whatever
wasn't reached yet, rather than starting over.

### 3. Cross-referencing against the world-file docs

**Open question, flagged explicitly rather than assumed:** the task says
to cross-reference against "the docs" to recover real room numbers. The
only concrete source of real vnums anywhere in this repo is
`week0_explore/circlemud-world-parser`'s parse of the MUD's own `.wld`
file (`week0_explore/infrastructure/lib/world/wld/30.wld`) — there's no
separate hand-written room-number document. This plan assumes that's what
"the docs" refers to; see Open questions below to confirm.

`scripts/cross_reference.py` (separate script — the crawl script above
never touches this data):

```
cd week0_explore/circlemud-world-parser
uv run circlemud-parse ../infrastructure/lib/world/wld/30.wld --dest /tmp/zone_30_docs.json
```

(Same subprocess approach as before, and for the same reason: the parser
requires Python 3.14, the shared boukensha `.venv` runs 3.12.3, so it's
invoked via `uv run --project ...` rather than imported.)

The matching problem: several crawled rooms share a name with several real
rooms (Zone 30 has real name-duplicates — multiple "Main Street" segments,
for instance). Plain name matching alone can't tell which discovered
"Main Street" is which real "Main Street". The fix is **constraint
propagation using the graph the crawl already built**: rooms with a
name unique in the docs resolve immediately; every other room resolves
once at least one of its already-resolved neighbors' real exits point at
a specific candidate — i.e. "this discovered room's north exit leads to a
room we've already matched to vnum 3001; of this name's three candidate
vnums, only one of them has a real north exit into 3001, so it must be
that one."

```python
def cross_reference(crawled, docs):
    """crawled: temp_id -> {"name":, "desc":, "exits": {dir: temp_id|None}}
    docs: vnum -> {"name":, "exits": {dir: vnum}} (from the fresh parse)
    Returns (resolved: {temp_id: vnum}, unresolved: [temp_id]).
    """
    by_name = {}
    for vnum, room in docs.items():
        by_name.setdefault(room["name"].lower(), []).append(vnum)

    resolved = {}
    for temp_id, room in crawled.items():
        candidates = by_name.get(room["name"].lower(), [])
        if len(candidates) == 1:
            resolved[temp_id] = candidates[0]

    changed = True
    while changed:
        changed = False
        for temp_id, room in crawled.items():
            if temp_id in resolved:
                continue
            candidates = by_name.get(room["name"].lower(), [])
            consistent = []
            for vnum in candidates:
                doc_exits = docs[vnum]["exits"]
                ok = True
                for direction, neighbor_temp_id in room["exits"].items():
                    if not neighbor_temp_id or neighbor_temp_id not in resolved:
                        continue
                    if doc_exits.get(direction) != resolved[neighbor_temp_id]:
                        ok = False
                        break
                if ok:
                    consistent.append(vnum)
            if len(consistent) == 1:
                resolved[temp_id] = consistent[0]
                changed = True

    unresolved = [t for t in crawled if t not in resolved]
    return resolved, unresolved
```

Any room still unresolved after propagation converges is printed clearly
and left without a `"vnum"` key in the output — **never guessed** — so a
human can resolve the last few by hand if needed rather than the data
silently containing a wrong room number.

Output, `data/zone_30.json` — same shape as the crawl file, **each entry
keeps its original discovery-order key and all its original fields, with
one key added**, exactly as asked:

```json
{
  "1": {"name": "The Temple Of Midgaard", "desc": "...", "exits": {"north": 5, "east": 12, "south": null, "west": 3, "up": null, "down": 3}, "vnum": 3001},
  "2": {"name": "The Bakery", "desc": "...", "exits": {"south": 1, "north": null, "east": null, "west": null, "up": null, "down": null}, "vnum": 3009}
}
```

Both files are committed (small — 58 rooms).

### 4. Why the discovery-order numbers stay the graph's real keys

Downstream (BFS, name lookup, the `goto_room` tool), there is **no need to
switch to vnums at all** — the discovery-order number is just as valid a
graph key as a vnum, since `exits` already reference other rooms by that
same number. `vnum` is carried purely as a display/reference field, not
something pathfinding needs to touch. This keeps `zone_nav/graph.py`
simpler than re-keying everything by vnum after cross-referencing would
require, and it's a closer match to "add it as another key" than "replace
the keys."

```python
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ZONE_PATH = Path(__file__).resolve().parent.parent / "data" / "zone_30.json"


@dataclass(frozen=True)
class RoomInfo:
    id: int             # discovery-order number -- the graph's actual key
    name: str
    exits: dict          # direction -> id (may be missing/None for no exit)
    vnum: int | None     # real room number, informational only


def load_zone(path=DEFAULT_ZONE_PATH):
    raw = json.loads(Path(path).read_text())
    graph = {}
    for id_str, data in raw.items():
        exits = {d: t for d, t in data["exits"].items() if t is not None}
        graph[int(id_str)] = RoomInfo(int(id_str), data["name"], exits, data.get("vnum"))
    return graph


def shortest_paths_from(graph, start_id):
    distances = {start_id: 0}
    prev_direction, prev_id = {}, {}
    queue = deque([start_id])
    while queue:
        current = queue.popleft()
        for direction, target in graph[current].exits.items():
            if target in distances:
                continue
            distances[target] = distances[current] + 1
            prev_direction[target] = direction
            prev_id[target] = current
            queue.append(target)
    return distances, prev_direction, prev_id


def reconstruct_path(prev_direction, prev_id, start_id, target_id):
    if target_id == start_id:
        return []
    if target_id not in prev_direction:
        return None
    directions = []
    node = target_id
    while node != start_id:
        directions.append(prev_direction[node])
        node = prev_id[node]
    directions.reverse()
    return directions


def find_by_name(graph, name):
    needle = name.strip().lower()
    exact = [i for i, r in graph.items() if r.name.lower() == needle]
    if exact:
        return exact
    return [i for i, r in graph.items() if needle in r.name.lower()]
```

### 5. Why an in-memory dict, not a database

58 rooms and roughly a hundred directed edges fit trivially in memory as a
plain `dict[int, RoomInfo]`; BFS over it is sub-millisecond. A database
would add a schema, a query layer, and a connection to manage, to serve
lookups a dict loaded once from a small committed JSON file already
answers in O(1)/O(V+E). The data is static (a map of the game world, not
mutated at runtime) and has exactly one reader process at a time — nothing
here calls for persistence or concurrency beyond "read a JSON file at
import time." Revisit only if this ever grows to cover many zones at once.

### 6. `zone_nav/tool.py` — the `goto_room` tool

Unchanged in shape from the direction already validated for this feature —
current room is found by calling `look`, stripping ANSI color codes tbaMUD
sends (confirmed present in this repo's own raw telnet captures — e.g.
`week3_capable/bin/reset`'s live output showed literal `[0;33m...[0m`
sequences around room names; `mud_manager/session.rb` strips telnet IAC
bytes but never ANSI), and matching the first line against the graph's
names:

```python
import re
from . import graph as zone_graph

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _current_room_name(look_text):
    for line in look_text.splitlines():
        stripped = ANSI_RE.sub("", line).strip()
        if stripped:
            return stripped
    return None


def register(dsl, *, move_tool="tbamud__move", look_tool="tbamud__look", zone_path=None):
    graph = zone_graph.load_zone(zone_path) if zone_path else zone_graph.load_zone()
    name_by_id = {i: r.name for i, r in graph.items()}

    def block(*, room_name):
        candidates = zone_graph.find_by_name(graph, room_name)
        if not candidates:
            return "error: no room matching '{}' in the mapped zone (Northern Midgaard)".format(room_name)

        current_name = _current_room_name(dsl.dispatch(look_tool, {}))
        current_matches = [i for i, n in name_by_id.items() if n.lower() == (current_name or "").lower()]
        if not current_matches:
            return (
                "error: current room ('{}') isn't recognized as part of the mapped zone -- "
                "goto_room only knows Northern Midgaard (zone 30)".format(current_name)
            )
        current_id = current_matches[0]

        distances, prev_direction, prev_id = zone_graph.shortest_paths_from(graph, current_id)
        reachable = [i for i in candidates if i in distances]
        if not reachable:
            return "error: '{}' exists in the mapped zone but isn't reachable from here".format(room_name)
        target_id = min(reachable, key=lambda i: (distances[i], i))  # nearest; ties broken deterministically

        if target_id == current_id:
            return "already at {}".format(name_by_id[target_id])

        directions = zone_graph.reconstruct_path(prev_direction, prev_id, current_id, target_id)
        for direction in directions:
            dsl.dispatch(move_tool, {"direction": direction})

        confirm_name = _current_room_name(dsl.dispatch(look_tool, {}))
        arrived = (confirm_name or "").lower() == name_by_id[target_id].lower()
        status = "arrived at" if arrived else "expected to arrive at (unconfirmed, currently at '{}')".format(confirm_name)
        return "{} {} via {} move(s): {}".format(status, name_by_id[target_id], len(directions), " -> ".join(directions))

    dsl.tool(
        "goto_room",
        description=(
            "Move directly to a named room within the mapped zone (Northern Midgaard) "
            "using the shortest known path, instead of wandering room to room."
        ),
        parameters={
            "room_name": {"type": "string", "description": "Room name or partial name, e.g. 'Bakery' or 'Main Street'"}
        },
        block=block,
    )
```

- **Ambiguous names resolve to the nearest reachable match, not an
  error** — with real duplicate names in this zone, a hard failure would
  make `goto_room("Main Street")` never work; nearest-by-BFS-distance
  directly serves "in the most efficient manner."
- **Post-hoc verification, not blind trust** — one final `look` after
  executing the path, compared against the expected name, same
  warn-don't-silently-claim-success pattern as `week3_capable/bin/reset`.

### 7. `boukensha/run_dsl.py` needs `.dispatch()`

`register_tools` callbacks (the extension point `boukensha.run()` and
`boukensha.start_repl()` both support, invoked *after* MCP registration —
confirmed in `week3_capable/python/tool_scoping/boukensha/__init__.py`
lines 166-167 / 264-265) are only ever handed a `RunDSL`, which today
exposes just `.tool()`/`.tool_names()` — no way for `goto_room`'s block to
call the already-registered `move`/`look` tools. Small, direct addition:

```python
def dispatch(self, name, args=None):
    return self._registry.dispatch(name, args)
```

Flagged in Open questions — a real (if small) change to a `boukensha`
core file, same category `tool_scoping` already made to `config.py` and
`tools/mcp.py`.

### 8. Wiring into the actual app

`boukensha_loader.py`'s `load_and_start_repl()` currently calls bare
`boukensha.start_repl(tui=not no_tui)` — no `register_tools` at all.
Changed to:

```python
import zone_nav.tool as zone_nav_tool
...
boukensha.start_repl(tui=not no_tui, register_tools=zone_nav_tool.register)
```

### 9. Config: `look` needs to be turned on for the *agent's* copy of the tools

Separate from the crawl script (which registers its own unfiltered
`move`/`look`, bypassing config entirely — Design section 2), the
*interactive agent* still gets its tools from `.boukensha/settings.yaml`'s
`mcp_servers.mud.tools` table, which `tool_scoping` scoped down to `move`,
`examine`, `check` only. `goto_room` needs `tbamud__look` to detect the
current room, so `look: off` → `on` there too (same precedent: backup
copy first, edit the shared fixture in place). Real, flagged tradeoff:
takes the previously-curated "3 tools only" set to 4.

## Testing

1. **Unit tests, fully offline, no MUD** — `tests/test_cross_reference.py`:
   feed `cross_reference()` a small synthetic `crawled`/`docs` fixture with
   a deliberate name collision (two candidate vnums sharing a name) and
   confirm topology propagation resolves it correctly using a resolved
   neighbor; confirm a genuinely unresolvable room (no usable neighbor
   constraint) ends up in `unresolved`, not silently guessed.
2. **Unit tests, fully offline** — `tests/test_zone_nav.py`, against the
   real committed `data/zone_30.json` once generated: `find_by_name`
   exact/substring cases; BFS self-consistency (a returned path, replayed
   by hand against `graph[id].exits`, lands exactly on the target); ANSI
   stripping.
3. **Live crawl run** — the crawl and cross-reference scripts only make
   sense run against the real MUD (there's no fake-MUD zone topology to
   test them against, and building one would mean hand-authoring a whole
   fake 58-room zone — not worth it for a one-time offline tool). This
   moves `dummy` through the zone extensively and takes a while; ask
   before running it, same as any other live-MUD action in this repo.
4. **Live `goto_room` smoke test, no API cost** — `examples/goto_demo.py`:
   builds `Context`/`Registry` directly, registers real `move`+`look`
   (needs `look: on`) plus `zone_nav.tool`, then calls
   `registry.dispatch("goto_room", {"room_name": "Bakery"})` directly — no
   LLM turn, so it's free to run without spend approval.
5. **Live agent run, costs API** — only after the above passes and with
   explicit go-ahead: ask the agent in natural language to go to the
   Bakery via `bin/boukensha`, confirming it actually chooses to call
   `goto_room`.

## Task list

1. Copy `week3_capable/python/tool_scoping/` → `week3_capable/python/map_zone/`
   verbatim (excluding `__pycache__`/`boukensha.egg-info`).
2. Write `scripts/crawl_zone.py` per Design sections 1–2.
3. Ask before running it live; run it; commit `data/zone_30_crawl.json`.
4. Write `scripts/cross_reference.py` per Design section 3; run it against
   a fresh `circlemud-parse` output; commit `data/zone_30.json`.
5. Write `zone_nav/graph.py` per Design section 4.
6. Write `zone_nav/tool.py` per Design section 6.
7. Edit `boukensha/run_dsl.py`: add `.dispatch()` per Design section 7.
8. Edit `boukensha_loader.py`: wire `register_tools=` per Design section 8.
9. `cp .boukensha/settings.yaml .boukensha/settings.yaml.bak`; flip
   `mcp_servers.mud.tools.look` to `on` per Design section 9.
10. Write `tests/test_cross_reference.py` and `tests/test_zone_nav.py` per
    Testing sections 1–2; run them, fix forward until green.
11. Write `examples/goto_demo.py`; run it against the real MUD; confirm a
    clean "arrived at The Bakery" result.
12. Update `README.md` and `pyproject.toml`'s `description`.
13. Ask before running the paid live-agent verification (Testing
    section 5).
14. Don't commit until the user reviews.

## Open questions for the user

1. **What exactly are "the docs" for cross-referencing?** This plan
   assumes it means running `circlemud-world-parser` fresh against the
   real `.wld` file (the only source of real vnums found anywhere in this
   repo) — confirm, or point at a different source if one exists that
   wasn't found.
2. **Blind 6-direction probing vs. parsing the `[ Exits: ... ]` line** —
   this plan chose the slower-but-format-independent probing approach
   (Design section 1). Acceptable, or is minimizing MUD round-trips during
   the crawl worth the fragility of depending on exact exits-line text?
3. **`RunDSL.dispatch()`** is a small addition to a `boukensha` core file
   (Design section 7), not app-level code. Fine to extend, or should
   `goto_room` avoid it and only be wired up manually (meaning it would
   work from `examples/goto_demo.py` but *not* from `bin/boukensha`)?
4. **Editing the shared `.boukensha/settings.yaml` again** (`look: off` →
   `on`, Design section 9) takes `tool_scoping`'s curated "3 tools only"
   demo to 4 tools. Acceptable, same tradeoff already made once before?
5. **If the crawler gets stuck** (Design section 2's `CrawlStuckError`),
   this plan's answer is "use `week3_capable/bin/reset` to recover
   manually and re-run" rather than fully automated recovery. Enough, or
   should the crawler attempt automatic recovery (e.g. shelling out to
   `reset` itself) when it detects it's stuck?
