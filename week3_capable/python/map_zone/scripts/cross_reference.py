#!/usr/bin/env python3
"""
Cross-references the live-crawled zone map (data/zone_30_crawl.json,
produced by scripts/crawl_zone.py by actually walking the MUD -- no world
files involved in that step at all) against the MUD's own world-file docs,
purely to look up each already-discovered room's real room number (vnum).

The world files never inform what the rooms are or how they connect --
only what number a given, already-identified room happens to have. Output,
data/zone_30.json, is the same room entries the crawl produced, each now
carrying one extra key: "vnum".

Several crawled rooms share a name with several real rooms (zone 30 has
genuine name-duplicates -- multiple "Main Street" segments, for instance),
so plain name matching alone can't resolve all of them. The fix is
constraint propagation using the graph the crawl already built: rooms with
a name unique in the docs resolve immediately; every other room resolves
once at least one of its already-resolved neighbors' real exits point at a
specific candidate. Anything still unresolved after that converges is left
without a "vnum" key and printed clearly -- never guessed.

Usage:
    python scripts/cross_reference.py [--crawl data/zone_30_crawl.json] [--out data/zone_30.json]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PARSER_ROOT = REPO_ROOT / "week0_explore" / "circlemud-world-parser"
WLD_PATH = REPO_ROOT / "week0_explore" / "infrastructure" / "lib" / "world" / "wld" / "30.wld"

DEFAULT_CRAWL = Path(__file__).resolve().parent.parent / "data" / "zone_30_crawl.json"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "zone_30.json"

# Same direction-code mapping as circlemud_world_parser/room.py's Exit.dir
# docstring (0=N, 1=E, 2=S, 3=W, 4=U, 5=D), converted to the same direction
# strings mud_manager's `move` tool and the crawl's own data use.
DIR_NAMES = {0: "north", 1: "east", 2: "south", 3: "west", 4: "up", 5: "down"}


def load_docs(wld_path=WLD_PATH):
    """Runs circlemud-world-parser fresh against the real .wld file (its
    own uv-managed project -- Python 3.14, separate from this repo's
    shared boukensha .venv on 3.12 -- invoked as a subprocess rather than
    imported) and returns {vnum: {"name":, "exits": {direction: vnum}}}.
    """
    raw = subprocess.run(
        ["uv", "run", "--project", str(PARSER_ROOT), "circlemud-parse", str(wld_path), "--dest", "/dev/stdout"],
        capture_output=True, text=True, check=True,
    ).stdout
    rooms = json.loads(raw)

    docs = {}
    for room in rooms:
        exits = {}
        for e in room["exits"]:
            direction = DIR_NAMES.get(e["dir"])
            if direction is None or e["room_linked"] == -1:
                continue
            exits[direction] = e["room_linked"]
        docs[room["id"]] = {"name": room["name"], "exits": exits}
    return docs


def cross_reference(crawled, docs):
    """crawled: {temp_id: {"name":, "desc":, "exits": {dir: temp_id|None}}}
    docs: {vnum: {"name":, "exits": {dir: vnum}}} (from load_docs)
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

    unresolved = sorted(t for t in crawled if t not in resolved)
    return resolved, unresolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crawl", default=str(DEFAULT_CRAWL))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    crawled_raw = json.loads(Path(args.crawl).read_text())
    crawled = {int(k): v for k, v in crawled_raw.items()}

    print("[cross-reference] parsing {} via circlemud-world-parser...".format(WLD_PATH))
    docs = load_docs()
    print("[cross-reference] docs: {} room(s) parsed from the real world file".format(len(docs)))

    resolved, unresolved = cross_reference(crawled, docs)
    print("[cross-reference] resolved {}/{} room(s)".format(len(resolved), len(crawled)))
    if unresolved:
        print(
            "[cross-reference] WARNING: {} room(s) left unresolved (no 'vnum' key) -- "
            "resolve manually if needed:".format(len(unresolved)),
            file=sys.stderr,
        )
        for temp_id in unresolved:
            print("  room {}: {}".format(temp_id, crawled[temp_id]["name"]), file=sys.stderr)

    out = {}
    for temp_id, room in sorted(crawled.items()):
        entry = dict(room)
        if temp_id in resolved:
            entry["vnum"] = resolved[temp_id]
        out[str(temp_id)] = entry

    out_path = Path(args.out)
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("[cross-reference] wrote {}".format(out_path))


if __name__ == "__main__":
    main()
