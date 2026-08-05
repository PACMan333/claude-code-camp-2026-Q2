"""The `goto_room` boukensha tool: move directly to a named room within the
mapped zone (Northern Midgaard) using the shortest known path, instead of
wandering room to room.

Lives outside `boukensha/` on purpose -- boukensha ships no tools or
domain logic of its own (see `boukensha/__init__.py`); this is app-level
code that happens to use boukensha, the same relationship `examples/*.py`
already has.
"""
import time

from . import graph as zone_graph
from . import text as zone_text


def _current_room_name(look_text):
    """Delegates to zone_nav.text.first_room_name_line -- the same
    ANSI-stripping, broadcast-filtering, and noise-line-skipping logic
    scripts/crawl_zone.py's parsing relies on. Confirmed live this isn't
    optional here either: a login-triggered realm-wide announcement
    landing as the first line of `look`'s response once made goto_room
    fail to recognize the player's own current room."""
    return zone_text.first_room_name_line(look_text)


def _look_current_room_name(dsl, look_tool, retries=3, delay=0.5):
    """Dispatches `look` and extracts the room name, retrying (with a
    settle delay) if it comes back empty. Confirmed live: a `look` can
    occasionally return nothing recognizable as a room name at all --
    every candidate line filtered out as noise, e.g. an async server
    message straddling the read with nothing else in the buffer yet --
    even after zone_nav.text's filtering already rules out the specific
    known-bad strings. scripts/crawl_zone.py's Crawler.visit_current_room
    has carried the identical retry for the same reason since the crawl
    itself hit this; goto_room needs it just as much at runtime.
    """
    for attempt in range(retries + 1):
        name = _current_room_name(dsl.dispatch(look_tool, {}))
        if name:
            return name
        if attempt < retries:
            time.sleep(delay)
    return None


def register(dsl, *, move_tool="tbamud__move", look_tool="tbamud__look", zone_path=None):
    graph = zone_graph.load_zone(zone_path) if zone_path else zone_graph.load_zone()
    name_by_id = {i: r.name for i, r in graph.items()}

    def block(*, room_name):
        candidates = zone_graph.find_by_name(graph, room_name)
        if not candidates:
            return "error: no room matching '{}' in the mapped zone (Northern Midgaard)".format(room_name)

        current_name = _look_current_room_name(dsl, look_tool)
        if current_name is None:
            return (
                "error: couldn't determine the current room (no readable room text came back "
                "from `look`, even after retries) -- try again"
            )
        current_matches = [i for i, n in name_by_id.items() if n.lower() == current_name.lower()]
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
        # Nearest reachable candidate wins ties on duplicate room names (e.g.
        # zone 30's several "Main Street" segments) -- deterministic tie-break
        # on id, and directly serves "in the most efficient manner": a hard
        # ambiguity error would make goto_room("Main Street") never work.
        target_id = min(reachable, key=lambda i: (distances[i], i))

        if target_id == current_id:
            return "already at {}".format(name_by_id[target_id])

        directions = zone_graph.reconstruct_path(prev_direction, prev_id, current_id, target_id)
        for direction in directions:
            dsl.dispatch(move_tool, {"direction": direction})

        # One confirmation look at the end, not after every hop -- catches a
        # derailed path (blocked door, wandering mob) without doubling the
        # tool-call cost of every trip. Same warn-don't-silently-claim-success
        # pattern as week3_capable/bin/reset.
        confirm_name = _look_current_room_name(dsl, look_tool)
        arrived = (confirm_name or "").lower() == name_by_id[target_id].lower()
        status = "arrived at" if arrived else "expected to arrive at (unconfirmed, currently at '{}')".format(confirm_name)
        return "{} {} via {} move(s): {}".format(
            status, name_by_id[target_id], len(directions), " -> ".join(directions)
        )

    dsl.tool(
        "goto_room",
        description=(
            "Move directly to a named room within the mapped zone (Northern Midgaard) "
            "using the shortest known path, instead of wandering room to room."
        ),
        parameters={
            "room_name": {
                "type": "string",
                "description": "Room name or partial name, e.g. 'Bakery' or 'Main Street'",
            }
        },
        block=block,
    )
