"""The `goto_room` boukensha tool: move directly to a named room within the
mapped zone (Northern Midgaard) using the shortest known path, instead of
wandering room to room.

Lives outside `boukensha/` on purpose -- boukensha ships no tools or
domain logic of its own (see `boukensha/__init__.py`); this is app-level
code that happens to use boukensha, the same relationship `examples/*.py`
already has.
"""
import re

from . import graph as zone_graph

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _current_room_name(look_text):
    """tbaMUD sends ANSI color codes around room names (confirmed in this
    repo's own raw telnet captures); mud_manager/session.rb strips telnet
    IAC negotiation bytes but never touches ANSI escapes, so they pass
    straight through `look`'s response. Strip them before matching."""
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
        confirm_name = _current_room_name(dsl.dispatch(look_tool, {}))
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
