#!/usr/bin/env python3
"""
Map zone 30 (Northern Midgaard) by actually walking the MUD -- no world
files are read anywhere in this script. Every newly-discovered room gets a
plain sequential number (1, 2, 3, ...) in the order it's first visited;
`scripts/cross_reference.py` is a separate, later step that looks up each
already-discovered room's real vnum against the MUD's own world-file docs.

Exploration is breadth-first, not depth-first: a room's neighbors are all
discovered before any of them get their own frontier explored. This
matters in practice -- zone 30's temple has an exit leading straight into
a large adjacent outdoor area ("The Great Field Of Midgaard") that isn't
part of the town at all. Depth-first exploration walks straight into that
field and never comes back to the temple's other exits. Breadth-first
exploration discovers the whole (small, tightly-clustered) town within the
first several waves out from the starting room, long before a single deep
branch like the field can dominate the run. A generous room-count safety
cap (`MAX_ROOMS`) is a second backstop, since there's still no live signal
for "you've left the target zone" -- room/zone numbers aren't visible
in-game at all (see the plan doc's Problem section).

Drives mud_manager's `move`/`look` MCP tools directly via boukensha's
Registry -- no Anthropic API call anywhere, so this costs nothing to run
and re-run. Since BFS needs to revisit rooms out of discovery order (a
frontier room dequeued later isn't necessarily adjacent to wherever the
character currently stands), the crawler navigates between frontier rooms
using the exact same BFS-pathfinding code `zone_nav/graph.py` exposes for
the finished map -- reused here against the map-in-progress.

A live run surfaced a real game mechanic worth documenting: `dummy`'s
movement points (max 83) drain from walking and were observed to stop
regenerating altogether while hungry/thirsty (confirmed live: 15 seconds
of resting produced zero regen) -- walking 50+ rooms burns through that
budget fast, after which every move fails with "You are too exhausted."
regardless of whether an exit actually exists. Rather than teach the
player character to eat and drink (a whole separate detour -- finding
food, having gold, knowing a shop), the crawler reuses the immortal
`restore <player>` command the same way `week3_capable/bin/reset` already
uses `teleport` -- a second, raw telnet admin connection (not MCP;
`mud_manager` doesn't wrap `restore`) that tops movement back up to full
whenever exhaustion is detected. `reset`'s own `Connection`/`login` code
is imported directly rather than reimplemented a third time in this repo.

A known list of cross-zone exits (BOUNDARY_EXITS below, supplied directly
rather than discovered) lets the crawl skip walking through them entirely
-- each is recorded as a "boundary" marker (a real exit that leads
somewhere, just not somewhere this crawl follows) instead of an actual
room id. This is the single biggest efficiency win available: every one
of these was, before this list existed, a place the crawl would wander
into unrelated, unmapped territory (another zone entirely) and have to
find its way back from -- exactly the class of problem the BFS ordering,
the room-count cap, and the teleport-rescue mechanism all exist to
contain. Knowing them up front means they're never walked at all.

For a clean, reproducible run, teleport `dummy` to a known room first:
    week3_capable/bin/reset
then run this script. If it raises CrawlStuckError partway through (a
one-way exit, or something moved the character mid-crawl -- e.g. a
wandering mob), re-run `week3_capable/bin/reset` and run this again --
by default it resumes from whatever --out already has (each already-known
room is recognized instantly via its name+description signature, and any
room with fewer than six directions probed goes back on the BFS queue), so
a re-run picks up where the previous one left off instead of rediscovering
everything from scratch. Pass --fresh to discard --out and start over.

Usage:
    python scripts/crawl_zone.py [--out data/zone_30_crawl.json] [--max-rooms 70] [--fresh]
"""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import boukensha  # noqa: E402
from boukensha.tools import mcp as tools_mcp  # noqa: E402
from zone_nav.graph import RoomInfo, shortest_paths_from, reconstruct_path  # noqa: E402
from zone_nav.text import EXITS_LINE_RE, clean_lines, has_exits_line, is_noise_line  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
MUD_MANAGER_ROOT = REPO_ROOT / "week0_explore" / "mud_manager"
MUD_MANAGER_BIN = MUD_MANAGER_ROOT / "bin" / "mud-manager"

# week3_capable/bin/reset has no .py suffix (it's meant to run directly as
# `week3_capable/bin/reset`), so it's loaded by file path via an explicit
# SourceFileLoader rather than a normal import -- reusing its
# Connection/login rather than a third reimplementation of the
# telnet/login dance in this repo.
_RESET_PATH = str(REPO_ROOT / "week3_capable" / "bin" / "reset")
_RESET_LOADER = importlib.machinery.SourceFileLoader("reset_script", _RESET_PATH)
_RESET_SPEC = importlib.util.spec_from_file_location("reset_script", _RESET_PATH, loader=_RESET_LOADER)
reset_script = importlib.util.module_from_spec(_RESET_SPEC)
_RESET_LOADER.exec_module(reset_script)

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "zone_30_crawl.json"
DEFAULT_MAX_ROOMS = 70  # zone 30's town is ~58 rooms; this is slack, not a hard fact relied on

EXHAUSTED_TEXT = "you are too exhausted"
RESCUE_ANCHOR_VNUM = "3001"  # The Temple Of Midgaard -- see _teleport_to_anchor

DIRECTIONS = ("north", "south", "east", "west", "up", "down")
# A heuristic guess only, tried first because it's usually right and cheap
# to verify -- never assumed. Confirmed live: a room reachable via two
# different directions (e.g. both `south` and `down` from the Temple lead
# to the same destination) isn't guaranteed to have the matching reverse
# pair (`north` *and* `up`) leading back -- only one of them might exist.
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}

# Known cross-zone exits, supplied directly rather than discovered -- real
# exits that lead to a different zone entirely, not part of Northern
# Midgaard. (room name, direction) -> skip walking it; recorded as
# BOUNDARY_MARKER instead of a room id. Matched case-insensitively against
# the room's own name; since several names in this zone are shared by
# multiple physical rooms (e.g. "The Great Field Of Midgaard"), this is
# necessarily a name-wide rule, not a specific-room one -- accepted
# tradeoff, supplied by the user from outside knowledge of the real map.
BOUNDARY_EXITS = {
    ("the great field of midgaard", "east"),
    ("the dirt path", "west"),
    ("outside the east gate of midgaard", "east"),
    ("the tournament and practice yard", "down"),
    ("the levee", "south"),
    ("the secret yard", "down"),
    ("the dump", "down"),
    ("on the bridge", "south"),
    ("outside the west gate of midgaard", "west"),
    ("the clerics' inner sanctum", "down"),
}
BOUNDARY_MARKER = "boundary"

# ANSI-stripping, exits-line detection, and stray-broadcast/vitals-line
# filtering all live in zone_nav/text.py now, shared with zone_nav/tool.py
# (goto_room) -- confirmed live that goto_room needs the identical
# protection this crawler already had, and two independently-maintained
# copies had already drifted out of sync once.


class CrawlStuckError(Exception):
    pass


def parse_look(text):
    """Splits room text into (name, static description), using
    zone_nav.text's shared ANSI-stripping/broadcast-filtering/noise-line
    heuristics (clean_lines, is_noise_line) so this crawler and the live
    goto_room tool can never drift back out of sync on what counts as
    "not actually a room name."

    Only the static part -- room name through the "[ Exits: ... ]" line --
    is used for room identity. Confirmed live (this repo, this crawl):
    everything after that line varies call to call even for the *same*
    physical room -- the trailing vitals/prompt line ("23H 100M 3V (news)
    (motd) >") changes on every call since movement points fluctuate,
    which made two visits to the Temple register as two different rooms
    before this fix. Room contents (mobs/players/items) would have the
    same problem if included. The exits line is a reliable boundary:
    everything through it is the room's fixed, hand-authored text;
    everything after is dynamic state that must not be part of the
    identity signature.
    """
    lines = clean_lines(text)
    while lines and is_noise_line(lines[0]):
        lines = lines[1:]
    name = lines[0] if lines else ""
    static_lines = []
    for ln in lines[1:]:
        static_lines.append(ln)
        if EXITS_LINE_RE.match(ln):
            break
    desc = "\n".join(static_lines)
    return name, desc


def _graph_view(rooms):
    """Adapts the crawl-in-progress `rooms` dict (exits may include
    explicit `None` for "no exit that way", or BOUNDARY_MARKER for a known
    cross-zone exit deliberately not followed) into the same RoomInfo shape
    zone_nav/graph.py's BFS pathfinding expects, so the crawler can reuse
    it verbatim to navigate between already-discovered rooms. Only actual
    room ids (ints) are real edges to route through.
    """
    return {
        rid: RoomInfo(rid, data["name"], {d: t for d, t in data["exits"].items() if isinstance(t, int)})
        for rid, data in rooms.items()
    }


class Crawler:
    def __init__(self, registry, max_rooms=DEFAULT_MAX_ROOMS, log=print,
                 host=None, port=None, player_username=None,
                 admin_username=None, admin_password=None, resume_from=None):
        self.registry = registry
        self.max_rooms = max_rooms
        self.log = log
        self.rooms = {}            # temp_id -> {"name":, "desc":, "exits": {dir: temp_id|None}}
        self.signature_to_id = {}  # (name, desc) -> temp_id
        self.next_id = 1
        self.current_id = None     # where the character actually is right now

        # Resume from a previous (possibly stuck/interrupted) run's output
        # instead of rediscovering everything from scratch -- a live crawl
        # of 50+ rooms can hit a CrawlStuckError partway through (a
        # transient server-side race, e.g.), and without this, every re-run
        # would have to re-walk and re-verify every already-known room
        # before reaching new territory. A room counts as "done" once all
        # six directions have been probed (each is either a room id or
        # None); anything less goes back on the BFS queue in `run`.
        if resume_from is not None and Path(resume_from).exists():
            existing = {int(k): v for k, v in json.loads(Path(resume_from).read_text()).items()}
            for temp_id, data in existing.items():
                self.rooms[temp_id] = {"name": data["name"], "desc": data["desc"], "exits": dict(data["exits"])}
                self.signature_to_id[(data["name"], data["desc"])] = temp_id
            if existing:
                self.next_id = max(existing) + 1
                self.log("[crawl] resuming from {}: {} room(s) already known".format(resume_from, len(existing)))

        # Admin connection for periodic `restore` calls (see module
        # docstring) -- opened lazily, on the first exhaustion, not
        # up front, since most short runs may never need it.
        self.host = host or os.environ.get("MUD_HOST", reset_script.DEFAULT_HOST)
        self.port = int(port or os.environ.get("MUD_PORT", reset_script.DEFAULT_PORT))
        self.player_username = player_username or os.environ.get("PLAYER_USERNAME", reset_script.DEFAULT_PLAYER_USERNAME)
        self.admin_username = admin_username or os.environ.get("ADMIN_USERNAME", reset_script.DEFAULT_ADMIN_USERNAME)
        self.admin_password = admin_password or os.environ.get("ADMIN_PASSWORD", reset_script.DEFAULT_ADMIN_PASSWORD)
        self._admin = None

    def _register_or_lookup(self, name, desc):
        sig = (name, desc)
        if sig in self.signature_to_id:
            return self.signature_to_id[sig], False
        temp_id = self.next_id
        self.next_id += 1
        self.signature_to_id[sig] = temp_id
        self.rooms[temp_id] = {"name": name, "desc": desc, "exits": {}}
        self.log("[crawl] discovered room {}: {}".format(temp_id, name))
        return temp_id, True

    def visit_current_room(self, retries=3, delay=0.5):
        """Only used at crawl start and after a rescue teleport -- there's
        no prior `move` response to read the room off of, so this issues
        `look` directly. Retries (with a settle delay) if the response
        strips down to nothing at all -- confirmed live, a `look` sent too
        soon after a teleport can catch only the trailing prompt line
        before the real room-description burst has arrived, which
        parse_look correctly refuses to treat as a room name (returning
        empty) rather than registering a bogus room."""
        for attempt in range(retries + 1):
            name, desc = parse_look(self.registry.dispatch("look", {}))
            if name:
                return self._register_or_lookup(name, desc)
            if attempt < retries:
                time.sleep(delay)
        raise CrawlStuckError("`look` kept returning no room content after {} retries".format(retries))

    def _ensure_admin(self):
        """Lazily opens the second, raw telnet admin connection used for
        `restore` and the teleport rescue (`mud_manager` doesn't wrap
        either as an MCP tool) -- the same approach
        week3_capable/bin/reset already uses, and its exact
        Connection/login code, reused directly rather than reimplemented.
        Opened on first need, not up front, since a short run may never
        need it.
        """
        if self._admin is None:
            self._admin = reset_script.Connection(self.host, self.port)
            reset_script.login(self._admin, self.admin_username, self.admin_password)

    def _restore_player(self):
        """Tops the player's hit/mana/movement back to full via the
        immortal `restore <player>` command, confirmed live to fully
        refill movement points (83/83) regardless of hunger/thirst status.
        """
        self._ensure_admin()
        self.log("[crawl] player exhausted -- restoring via admin 'restore {}'".format(self.player_username))
        self._admin.send_line("restore {}".format(self.player_username))
        self._admin.wait_for([reset_script.GAME_PROMPT_MARKER], timeout=8)

    def _teleport_to_anchor(self):
        """Last-resort recovery for _return_to: teleport back to the
        Temple (real vnum 3001, same default `week3_capable/bin/reset`
        uses) and re-orient from there. This is a rescue mechanism, not
        part of how the zone's topology is mapped (the crawl never reads
        or relies on real vnums anywhere else -- see the module
        docstring); it's only reached when local probing genuinely can't
        find any way back to a room, e.g. after a wrong guess wanders
        into the large adjacent field with no simple return path.
        """
        self._ensure_admin()
        self.log("[crawl] rescue: local probing exhausted -- teleporting back to the Temple (vnum {})".format(
            RESCUE_ANCHOR_VNUM
        ))
        self._admin.send_line("teleport {} {}".format(self.player_username, RESCUE_ANCHOR_VNUM))
        self._admin.wait_for([reset_script.GAME_PROMPT_MARKER], timeout=8)
        time.sleep(0.5)  # let the teleport's own visible effect settle before reading the room
        anchor_id, _ = self.visit_current_room()
        self.current_id = anchor_id
        return anchor_id

    def close(self):
        if self._admin is not None:
            self._admin.close()
            self._admin = None

    def _attempt_move(self, direction, authoritative=False):
        """Dispatches `move` and reads the room straight off *its own*
        response -- not a separate follow-up `look` call. Two back-to-back
        dispatches (move, then look) were confirmed live to occasionally
        desync: an async server broadcast (e.g. a login welcome banner)
        landing between the two calls left stale buffered text for the
        second one to read, misidentifying the room. `move`'s own response
        already contains the full destination room text on success
        (confirmed live), so there's no separate read to race against.

        Transparently retries once after a `restore` if the response is
        the exhaustion message -- exhaustion is never a legitimate "no
        exit" signal, so it's absorbed here rather than leaking out as a
        false negative to every caller (both the forward frontier probe,
        where a real "no exit" is an expected, common, legitimate result,
        and the backtrack/walk steps, where it isn't).

        On success, records the edge `from wherever we were standing` ->
        `direction` -> `room_id`. `authoritative` controls what happens if
        that direction already has a *different* recorded value:
        `_explore_frontier`'s deliberate forward probes (authoritative)
        always win, since that's the primary, intentional data-gathering
        pass. Every other caller here -- `_return_to`'s guesses/rescues,
        `_walk_to`'s hop-by-hop retraversal of already-known edges -- is
        incidental and never overwrites an existing value, only fills in
        ones that are still unset. Confirmed live this distinction
        matters: retraversing an already-correct edge during a rescue walk
        once silently overwrote it with a misread, corrupting previously-
        good data (the Temple's own `south`/`down` exits).

        Returns (moved: bool, room_id: int|None, is_new: bool). moved=False
        means the direction had no exit (or was blocked) -- room_id is
        None and nothing about the current room changes.
        """
        from_id = self.current_id
        text = self.registry.dispatch("move", {"direction": direction})
        if EXHAUSTED_TEXT in text.lower():
            self._restore_player()
            # `restore` itself likely triggers a visible effect broadcast to
            # the player (e.g. "You feel better!") -- a settle delay here
            # avoids that landing asynchronously in the middle of the
            # retried move's own response, the same class of stray-broadcast
            # race documented above for move-then-look.
            time.sleep(0.5)
            text = self.registry.dispatch("move", {"direction": direction})
        if not has_exits_line(text):
            return False, None, False
        name, desc = parse_look(text)
        room_id, is_new = self._register_or_lookup(name, desc)
        self.current_id = room_id
        if from_id is not None:
            existing = self.rooms[from_id]["exits"].get(direction)
            if existing is None:
                self.rooms[from_id]["exits"][direction] = room_id
            elif existing != room_id:
                if authoritative:
                    self.log(
                        "[crawl] WARNING: room {} direction {} was recorded as room {}, "
                        "an authoritative probe now observes room {} -- overwriting".format(
                            from_id, direction, existing, room_id
                        )
                    )
                    self.rooms[from_id]["exits"][direction] = room_id
                else:
                    self.log(
                        "[crawl] WARNING: room {} direction {} is recorded as room {}, but "
                        "an incidental retraversal just observed room {} -- keeping the "
                        "recorded value (only an authoritative forward probe can change it)".format(
                            from_id, direction, existing, room_id
                        )
                    )
        return True, room_id, is_new

    def _move_expecting_success(self, direction, retries=4, delay=0.6):
        """Like _attempt_move, but for call sites where the map discovered
        so far already says this move should work (walking to a BFS
        frontier room, or backtracking after a frontier probe). An
        unexpected failure there was confirmed live (this crawl) to
        sometimes be a stray async server broadcast landing between
        dispatches and getting misread as the move's response, not a real
        topology problem -- manually replaying the exact same move outside
        the crawler always succeeded. Retrying a couple of times with a
        short settle delay absorbs that without weakening genuine failure
        detection: a real one-way exit or blocked door fails the same way
        every time, retried or not, and still raises after retries are
        exhausted.
        """
        for attempt in range(retries + 1):
            moved, room_id, is_new = self._attempt_move(direction)
            if moved:
                return moved, room_id, is_new
            if attempt < retries:
                time.sleep(delay)
        return False, None, False

    def _walk_to(self, target_id):
        """Navigate from self.current_id to target_id using only the
        subgraph discovered so far (BFS pathfinding, same code the
        finished map uses). Raises CrawlStuckError if the walk doesn't
        land where expected.

        Used directly to move to the next BFS frontier room in `run`, and
        as `_return_to`'s fallback when the naive-opposite-direction guess
        doesn't land back where expected (a room reachable via two
        different directions, e.g. both `south` and `down` from the Temple
        leading to the Temple Square, isn't guaranteed to have a matching
        `north`-and-`up` pair of exits back -- only one of them might
        actually exist; the BFS path already known from the other probe
        finds the real way back in that case).
        """
        if target_id == self.current_id:
            return
        graph = _graph_view(self.rooms)
        distances, prev_direction, prev_id = shortest_paths_from(graph, self.current_id)
        directions = reconstruct_path(prev_direction, prev_id, self.current_id, target_id)
        if directions is None:
            raise CrawlStuckError(
                "no known path from room {} to room {} in the map discovered so far".format(
                    self.current_id, target_id
                )
            )
        start_id = self.current_id
        for direction in directions:
            moved, _, _ = self._move_expecting_success(direction)
            if not moved:
                raise CrawlStuckError(
                    "walking from room {} to room {}: the {} step failed (no exit / blocked) "
                    "even though the map discovered so far expected it to work, even after retries".format(
                        start_id, target_id, direction
                    )
                )
        if self.current_id != target_id:
            raise CrawlStuckError(
                "tried walking from room {} to room {} via {} but ended up in room {} -- "
                "a one-way exit somewhere on that path, or something moved us mid-crawl "
                "(a random encounter, e.g.)".format(start_id, target_id, directions, self.current_id)
            )

    def _return_to(self, room_id, direction_just_used):
        """Get back to room_id after a probe took us away from it. Four
        escalating attempts:

        1. The intuitive opposite of the direction just used (the common
           case -- cheap, and _attempt_move records it as real data the
           moment it succeeds).
        2. A full BFS walk over whatever's been discovered so far (handles
           the asymmetric-exit case -- see OPPOSITE's docstring note
           above -- *if* the room we're now in already has some other
           known way back).
        3. Confirmed live and genuinely possible: the guess can fail
           outright (no such exit at all -- e.g. a shop reachable only via
           one specific Main Street segment among several identically-
           named ones, whose own exit leads to a *different* Main Street
           instance, not the one we came from), leaving a brand-new room
           with no recorded edges for (2) to route through at all. Last
           resort: probe the room's other directions too, recording
           whatever's found, until one of them leaves us somewhere (2) can
           route home from.
        4. Also confirmed live: the guess can *succeed* but land somewhere
           that isn't room_id and has no quick way back either (e.g.
           wandering further into the large adjacent field, which has no
           short path back to the town) -- at that point local probing
           just wanders deeper rather than finding a way home. Rather than
           try to be cleverer about *which* direction to probe next from
           unfamiliar territory, teleport back to the Temple (a known-good
           anchor) and walk from there -- room_id is always reachable from
           the Temple via already-verified tree edges, since it was
           discovered by walking there from it in the first place.
        """
        guess = OPPOSITE.get(direction_just_used)
        if guess:
            moved, arrived_id, _ = self._attempt_move(guess)
            if moved and arrived_id == room_id:
                return
        try:
            self._walk_to(room_id)
            return
        except CrawlStuckError:
            pass
        for direction in DIRECTIONS:
            if direction == guess:
                continue  # already tried above
            moved, _, _ = self._attempt_move(direction)
            if not moved:
                continue
            try:
                self._walk_to(room_id)
                return
            except CrawlStuckError:
                continue
        self._walk_to_resilient(room_id)

    def _walk_to_resilient(self, target_id):
        """_walk_to, but falls back to the teleport anchor (see
        _teleport_to_anchor) and retries once if the direct walk fails --
        confirmed live to be necessary even for ordinary "move to the next
        BFS frontier room" hops, not just _return_to's backtracking, so
        both call it rather than the bare _walk_to."""
        try:
            self._walk_to(target_id)
        except CrawlStuckError:
            self._teleport_to_anchor()
            self._walk_to(target_id)  # let this raise CrawlStuckError if even this fails

    def _explore_frontier(self, room_id):
        """Try every not-yet-probed direction from room_id (we must
        already be standing there). Returns newly-discovered room ids, in
        the order found, for the BFS queue."""
        newly_discovered = []
        for direction in DIRECTIONS:
            if direction in self.rooms[room_id]["exits"]:
                continue
            if (self.rooms[room_id]["name"].lower(), direction) in BOUNDARY_EXITS:
                self.rooms[room_id]["exits"][direction] = BOUNDARY_MARKER
                self.log(
                    "[crawl]   room {} --{}--> (boundary: known to lead to another zone, not followed)".format(
                        room_id, direction
                    )
                )
                continue
            moved, after_id, is_new = self._attempt_move(direction, authoritative=True)
            if not moved:
                self.rooms[room_id]["exits"][direction] = None  # no exit that way (or blocked)
                continue
            self.log("[crawl]   room {} --{}--> room {}".format(room_id, direction, after_id))
            if is_new:
                newly_discovered.append(after_id)
            self._return_to(room_id, direction)
            if len(self.rooms) >= self.max_rooms:
                break
        return newly_discovered

    def run(self):
        start_id, _ = self.visit_current_room()
        self.current_id = start_id
        # Any room (including a resumed run's) with fewer than all six
        # directions probed still has work left; order by id to approximate
        # the original BFS discovery order.
        queue = deque(sorted(rid for rid, data in self.rooms.items() if len(data["exits"]) < len(DIRECTIONS)))
        queued = set(queue)
        while queue:
            if len(self.rooms) >= self.max_rooms:
                self.log(
                    "[crawl] hit the {}-room safety cap with {} room(s) still queued -- "
                    "stopping (raise --max-rooms to explore further)".format(
                        self.max_rooms, len(queue)
                    )
                )
                break
            room_id = queue.popleft()
            self._walk_to_resilient(room_id)
            for new_id in self._explore_frontier(room_id):
                if new_id not in queued:
                    queue.append(new_id)
                    queued.add(new_id)
        return self.rooms


def build_registry():
    ctx = boukensha.Context(system="zone crawl")
    registry = boukensha.Registry(ctx)
    tools_mcp.register(
        registry, command="ruby", args=[str(MUD_MANAGER_BIN), "--mcp"],
        env={
            "MUD_HOST": os.environ.get("MUD_HOST", "localhost"),
            "MUD_PORT": os.environ.get("MUD_PORT", "4000"),
            "MUD_NAME": os.environ.get("PLAYER_USERNAME", "dummy"),
            "MUD_PASSWORD": os.environ.get("PLAYER_PASSWORD", "helloworld"),
        },
        prefix=None,
        tools={"move": {"enabled": True, "as": None}, "look": {"enabled": True, "as": None}},
    )
    return registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--max-rooms", type=int, default=DEFAULT_MAX_ROOMS)
    parser.add_argument(
        "--fresh", action="store_true",
        help="Ignore any existing --out file and rediscover everything from scratch "
             "(default: resume from it, continuing wherever a previous run left off).",
    )
    args = parser.parse_args()
    out_path = Path(args.out)

    registry = build_registry()
    crawler = Crawler(registry, max_rooms=args.max_rooms, resume_from=None if args.fresh else out_path)
    try:
        rooms = crawler.run()
    finally:
        # Save whatever was discovered even if we got stuck partway through --
        # the crawl is idempotent, so partial progress isn't wasted.
        out_path.write_text(json.dumps(crawler.rooms, indent=2, sort_keys=True) + "\n")
        print("[crawl] wrote {} room(s) to {}".format(len(crawler.rooms), out_path))
        crawler.close()

    print("[crawl] done: {} room(s) discovered.".format(len(rooms)))


if __name__ == "__main__":
    main()
