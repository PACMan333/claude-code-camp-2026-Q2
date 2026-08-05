# Week 3 (Capable) · Map Zone

A full, self-contained copy of `week3_capable/python/tool_scoping`'s
`boukensha` package (same copy-forward-not-diff convention every step in
this repo uses), with one new capability: **a `goto_room` tool that moves
directly to a named room within Northern Midgaard (zone 30) using the
shortest known path**, instead of the agent wandering room to room.

The shipped map (`data/zone_30.json`) has 47 rooms discovered by actually
walking the live MUD — a complete crawl, zero rooms left with unexplored
directions, full connectivity confirmed from the Temple — 45 of them
cross-referenced to their real room number (81% of zone 30's full 58
rooms; the rest are name-duplicated rooms even neighbor-based constraint
propagation couldn't disambiguate, left unresolved rather than guessed).
Verified live end to end — `goto_room("Bakery")` finds *The Bakery* (real
vnum 3009) in 4 moves from the Temple, and `goto_room("Main Street")`
correctly picks the *nearest* of the zone's several same-named segments
rather than getting confused by the duplicates.

Everything from `tool_scoping` (the MCP `tools:` filter/rename mechanism,
context/token tracking, the Textual TUI, all five provider backends) is
unchanged in its fundamentals here — see
`week3_capable/python/tool_scoping/README.md` for that material. This
README covers only what this track adds.

## Setup

Uses the same shared repo-root `.venv` as the rest of this repo:

```bash
.venv/bin/pip install -r week3_capable/python/map_zone/requirements.txt
.venv/bin/pip install -e week3_capable/python/map_zone
```

No new third-party dependency.

## The problem this solves

There's no map. The only way `dummy` could reach a named location (e.g.
"the Bakery") was to `move` one direction at a time and `look` after each
hop — every trip cost however many turns it took to stumble there.

## How the map was built: by walking, not by reading world files

Per explicit instruction, this map was **not** derived from CircleMUD's
world-data files. It was built in two clearly separated phases:

1. **`scripts/crawl_zone.py`** actually walks the MUD (driving
   `mud_manager`'s real `move`/`look` MCP tools — no LLM call anywhere in
   this script, so it costs nothing to run) and discovers rooms by
   breadth-first exploration, numbering each newly-found room 1, 2, 3, ...
   in discovery order. No world files are read during this phase at all —
   only the room's name and description, observed live, are ever used to
   tell rooms apart.
2. **`scripts/cross_reference.py`** takes the finished discovery-order map
   and, separately, parses the real `.wld` world file (via
   `week0_explore/circlemud-world-parser`) purely to look up each
   already-identified room's real room number (vnum), adding it as one
   more key on that room's existing entry. The world file never informs
   *what the rooms are or how they connect* — only what number a given,
   already-discovered room happens to have.

Regenerate the map (only needed if the world data changes):

```bash
# Teleport dummy to a known starting room first:
week3_capable/bin/reset

# Walk the MUD and build data/zone_30_crawl.json (resumable -- re-run
# after a CrawlStuckError and it picks up where it left off):
python scripts/crawl_zone.py

# Cross-reference against the real world file to add "vnum" to each
# entry, writing the final data/zone_30.json:
python scripts/cross_reference.py
```

### Real complications the crawl had to handle

Mapping a live MUD by walking it surfaced several genuine issues no
world-file parse would ever hit:

- **Room identity without vnums.** A room is recognized as "the same
  room" by its `(name, static description)` signature — not name alone,
  since zone 30 has real duplicate names (several "Main Street" segments,
  for instance).
- **BFS, not DFS, exploration.** The Temple has an exit leading straight
  into a large adjacent outdoor area ("The Great Field Of Midgaard") that
  isn't part of the town. Depth-first exploration walks straight into it
  and never returns to the Temple's other exits; breadth-first exploration
  discovers the whole (small, tightly-clustered) town within the first
  several waves before a single deep branch can dominate the run. A
  generous room-count safety cap is a second backstop, since there's no
  live signal for "you've left the target zone."
- **Movement points are a real, exhaustible resource.** Walking dozens of
  rooms drains them, and they were observed to stop regenerating
  altogether while hungry/thirsty. The crawler detects "You are too
  exhausted." and tops the character back up via the immortal `restore`
  command over a second admin telnet connection (`mud_manager` doesn't
  wrap `restore`) — reusing `week3_capable/bin/reset`'s own
  `Connection`/`login` code directly.
- **Backtracking isn't always the naive opposite direction.** A room
  reachable via two different directions (both `south` and `down` from
  the Temple lead to the same destination, for instance) isn't guaranteed
  to have a matching pair of exits back. The crawler tries the intuitive
  guess first, falls back to a full BFS walk over what's known so far,
  then to probing the room's other directions, and finally to
  teleporting back to the Temple (a known-good anchor, via the same admin
  connection) and walking from there if truly stuck.
- **Stray server text can land mid-response and get misread as room
  content.** Confirmed live, repeatedly, in several different shapes: a
  login-triggered realm-wide announcement, the teleport rescue's own
  "Admin has teleported you!" confirmation, a mob arrival message, a
  zone-level warning, even a lone vitals/prompt line with no room text at
  all. Chasing each exact string doesn't scale, so `parse_look` uses a
  general, well-evidenced signal instead: every real room name observed in
  this MUD (dozens, by now) is a short title with no trailing punctuation;
  every corrupted case was either a full sentence (ending in `.`/`!`/`?`)
  or the vitals line itself. Any leading line matching either shape is
  skipped before a name is read off. A handful of exact known strings are
  still filtered as a first pass (`BROADCAST_RE`), but the punctuation/
  vitals-line heuristic is what actually generalized.
- **Retraversing a known-good edge can silently corrupt it.** Every hop
  the crawler takes gets recorded as data (see `_attempt_move`) — which is
  how a wrong early reading of a room's exit gets self-corrected the next
  time that direction is genuinely re-probed. But it also means a single
  bad read while merely *retraversing* an already-correct edge (walking to
  the next BFS frontier room, backtracking after a probe) can overwrite
  good data with a misread. Fixed with a confidence tier: only
  `_explore_frontier`'s deliberate forward probes are authoritative and
  can overwrite an existing value; every other caller (backtracking,
  walking to the next queued room) only fills in gaps, never overwrites,
  and logs a warning if it observes something different from what's
  already recorded.
- **Not every discovered room belongs to zone 30.** Real exits the crawl
  could legitimately walk into lead to *other* zones entirely — the Newbie
  Zone, the Field, a "Chessboard" area beyond it, and more. Early on this
  meant wasted time wandering into unrelated, unmapped territory and
  finding a way back; later, once a specific list of known cross-zone
  exits was supplied directly (room name + direction → "leads to another
  zone"), the crawl started skipping them outright — recorded as a
  `"boundary"` marker (`BOUNDARY_EXITS` in `scripts/crawl_zone.py`)
  instead of an actual room id, never walked at all. `zone_nav/graph.py`
  and `_graph_view` both treat `"boundary"` the same as "no exit" for
  pathfinding purposes — only real room ids are routable. Whatever still
  slips through despite the list (a duplicate-named room whose neighbor
  genuinely is in another zone) is handled the same way it always was:
  `cross_reference.py` reports it as unresolved (no `"vnum"` key) rather
  than guessing, since its name doesn't appear anywhere in zone 30's own
  `.wld` file. None of this blocks `goto_room`: pathfinding only ever
  needs the discovery-order graph, never the real vnums.
- **A room's own `[ Exits: ... ]` line is a source of ground truth worth
  cross-checking the crawl against.** After a "complete" run still had a
  handful of `CrawlStuckError`s clustered around the same few rooms,
  comparing each room's *recorded* exits against what its own stored
  description actually lists (a quick offline script, not part of the
  crawler itself) turned up real, fixable corruption the live retries
  alone hadn't caught: a room recorded with `up`/`down` exits that direct
  live testing confirmed don't exist at all (`"Alas, you cannot go that
  way..."` every time), an unlisted "bonus" exit that had seemed reliable
  across many runs but turned out not to be once pathfinding actually
  routed through it, and a couple of rooms only reachable via those since-
  corrected bad edges (genuinely orphaned once the bad edge was fixed --
  deleted and cleanly rediscovered via their real connections on the next
  run). The authoritative/incidental confidence tier above stops *new*
  corruption from creeping in; this check is what caught corruption that
  had already gotten in before that tier existed.

## `goto_room`

```python
dsl.tool("goto_room", ..., parameters={"room_name": "..."})
```

Given a room name (or partial name, e.g. `"Bakery"`), it: calls `look` to
find the current room, finds the target by name (preferring an exact
match; falling back to substring), computes the shortest path via BFS over
the mapped zone, executes it as a sequence of `move` calls, and confirms
arrival with one final `look`.

**Ambiguous names resolve to the nearest reachable match, not an error.**
With real duplicate names in this zone, a hard failure would make
`goto_room("Main Street")` never work; picking the closest candidate by
BFS distance directly serves "in the most efficient manner."

Room vnums are never needed for any of this — the discovery-order numbers
`crawl_zone.py` assigned are just as valid a graph key, since `exits`
already reference other rooms by that same numbering. `vnum`
(`cross_reference.py`'s contribution) is carried purely as a
display/reference field.

### Why an in-memory dict, not a database

Zone 30 is under 60 rooms and roughly a hundred directed edges — trivial
to hold as a plain `dict[int, RoomInfo]` in memory, with BFS over it
running in sub-millisecond time. A database would add a schema, a query
layer, and a connection to manage, to serve lookups a dict loaded once
from a small committed JSON file already answers in O(1)/O(V+E). The data
is static (a map of the game world, not mutated at runtime) with exactly
one reader process at a time.

## Wiring into the actual app

`RunDSL` (`boukensha/run_dsl.py`) gained a `.dispatch()` passthrough —
`goto_room`'s own implementation needs to call the already-registered
`move`/`look` tools internally, which the DSL previously had no way to do.
`boukensha_loader.py` now passes `register_tools=zone_nav.tool.register`
to `boukensha.start_repl(...)`, so `goto_room` is available from the real
interactive `bin/boukensha` app, not just a demo script.

`.boukensha/settings.yaml`'s `mcp_servers.mud.tools` table needed
`look: on` (previously `off`, per `tool_scoping`'s 3-tool scoping) --
`goto_room` depends on it to detect the current room.

## Run the demo

```bash
# Live, no API key needed -- dispatches goto_room directly (pure
# Python-to-MCP-to-MUD, no LLM turn), so it's free to run:
python examples/goto_demo.py "Bakery"

# One-shot demo against the real Anthropic API + real mud-manager daemon:
python examples/example.py
```

## Considerations

**The shared root `.boukensha/settings.yaml` fixture was edited again**
(backed up to `settings.yaml.bak.before-map_zone` — the pre-existing
`settings.yaml.bak` predates `tool_scoping`'s own edit and was left
untouched), taking `tool_scoping`'s curated "3 tools only" demo to 4.

**Tests.** `tests/test_cross_reference.py` unit-tests the constraint-
propagation name/vnum matching (including the duplicate-name case) against
synthetic fixtures — no MUD, no live parser subprocess.
`tests/test_zone_nav.py` tests `find_by_name`, BFS self-consistency, and
ANSI-stripping against the real committed `data/zone_30.json`. Neither the
crawl nor the cross-reference script has an offline test — there's no
fake-MUD zone topology to test them against, and hand-authoring one would
mean building a whole fake 58-room zone for a one-time tool; they're
verified live instead (see above).
