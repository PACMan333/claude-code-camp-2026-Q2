"""In-memory graph + BFS pathfinding over a mapped zone.

58 rooms and roughly a hundred directed edges fit trivially in memory as a
plain dict; BFS over it is sub-millisecond. No database -- this data is
static (a map of the game world, not mutated at runtime) with exactly one
reader process at a time, so a dict loaded once from a small committed
JSON file already answers every lookup this needs.

The graph's keys are the discovery-order room numbers assigned by
scripts/crawl_zone.py (1, 2, 3, ...), not real MUD room numbers (vnums) --
`RoomInfo.vnum`, added by scripts/cross_reference.py, is carried purely as
a display/reference field. Pathfinding never needs to touch it: `exits`
already reference other rooms by the same discovery-order numbering the
graph itself is keyed by.
"""
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_ZONE_PATH = Path(__file__).resolve().parent.parent / "data" / "zone_30.json"


@dataclass(frozen=True)
class RoomInfo:
    id: int                    # discovery-order number -- the graph's actual key
    name: str
    exits: Dict[str, int]      # direction -> id (rooms with no exit that way are omitted)
    vnum: Optional[int] = None  # real MUD room number, informational only


def load_zone(path=None) -> Dict[int, RoomInfo]:
    raw = json.loads(Path(path or DEFAULT_ZONE_PATH).read_text())
    graph = {}
    for id_str, data in raw.items():
        # Only real room ids are routable edges -- `None` (no exit) and
        # "boundary" (a known cross-zone exit the crawl deliberately didn't
        # follow, see scripts/crawl_zone.py's BOUNDARY_EXITS) are both
        # non-navigable, excluded the same way.
        exits = {d: t for d, t in data["exits"].items() if isinstance(t, int)}
        graph[int(id_str)] = RoomInfo(int(id_str), data["name"], exits, data.get("vnum"))
    return graph


def shortest_paths_from(graph, start_id) -> Tuple[Dict[int, int], Dict[int, str], Dict[int, int]]:
    """Single-source BFS. Returns (distances, prev_direction, prev_id):
    prev_direction[id] is the direction taken to *arrive* at id on the
    shortest path from start_id; prev_id[id] is the room that move was
    taken from. Unreachable rooms are simply absent from all three dicts.
    """
    distances = {start_id: 0}
    prev_direction: Dict[int, str] = {}
    prev_id: Dict[int, int] = {}
    queue = deque([start_id])
    while queue:
        current = queue.popleft()
        room = graph.get(current)
        if room is None:
            continue
        for direction, target in room.exits.items():
            if target in distances:
                continue
            distances[target] = distances[current] + 1
            prev_direction[target] = direction
            prev_id[target] = current
            queue.append(target)
    return distances, prev_direction, prev_id


def reconstruct_path(prev_direction, prev_id, start_id, target_id) -> Optional[List[str]]:
    if target_id == start_id:
        return []
    if target_id not in prev_direction:
        return None  # unreachable
    directions = []
    node = target_id
    while node != start_id:
        directions.append(prev_direction[node])
        node = prev_id[node]
    directions.reverse()
    return directions


def find_by_name(graph, name) -> List[int]:
    """Case-insensitive lookup. Prefers exact full-name matches (handles
    zone 30's real duplicate room names -- several "Main Street"/"Wall
    Road"/etc. segments); falls back to substring matches (so "Bakery"
    finds "The Bakery"). Returns candidate ids -- zero, one, or many;
    disambiguating many is the caller's job (this module has no notion of
    "current position").
    """
    needle = name.strip().lower()
    exact = [i for i, r in graph.items() if r.name.lower() == needle]
    if exact:
        return exact
    return [i for i, r in graph.items() if needle in r.name.lower()]
