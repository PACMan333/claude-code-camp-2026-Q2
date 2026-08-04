#!/usr/bin/env python3
"""
Map zone 30 (Northern Midgaard) by actually walking the MUD -- no world
files are read anywhere in this script. Every newly-discovered room gets a
plain sequential number (1, 2, 3, ...) in the order it's first visited;
`scripts/cross_reference.py` is a separate, later step that looks up each
already-discovered room's real vnum against the MUD's own world-file docs.

Drives mud_manager's `move`/`look` MCP tools directly via boukensha's
Registry -- no Anthropic API call anywhere, so this costs nothing to run
and re-run.

For a clean, reproducible run, teleport `dummy` to a known room first:
    week3_capable/bin/reset
then run this script. If it raises CrawlStuckError partway through (a
one-way exit, or something moved the character mid-crawl -- e.g. a
wandering mob), re-run `week3_capable/bin/reset` and run this again; the
crawl is idempotent (already-discovered rooms are recognized instantly via
their name+description signature), so a re-run just fills in whatever
wasn't reached yet.

Usage:
    python scripts/crawl_zone.py [--out data/zone_30_crawl.json]
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import boukensha  # noqa: E402
from boukensha.tools import mcp as tools_mcp  # noqa: E402

MUD_MANAGER_ROOT = Path(__file__).resolve().parents[4] / "week0_explore" / "mud_manager"
MUD_MANAGER_BIN = MUD_MANAGER_ROOT / "bin" / "mud-manager"

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "zone_30_crawl.json"

DIRECTIONS = ("north", "south", "east", "west", "up", "down")
REVERSE = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


class CrawlStuckError(Exception):
    pass


def parse_look(text):
    lines = [ANSI_RE.sub("", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    name = lines[0] if lines else ""
    desc = "\n".join(lines[1:])  # includes exits/contents lines -- fine, part of the signature too
    return name, desc


class Crawler:
    def __init__(self, registry, log=print):
        self.registry = registry
        self.log = log
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
        self.log("[crawl] discovered room {}: {}".format(temp_id, name))
        return temp_id, True

    def explore(self, temp_id):
        for direction in DIRECTIONS:
            if direction in self.rooms[temp_id]["exits"]:
                continue
            self.registry.dispatch("move", {"direction": direction})
            after_id, is_new = self.visit_current_room()
            if after_id == temp_id:
                self.rooms[temp_id]["exits"][direction] = None  # no exit that way (or blocked)
                continue
            self.log("[crawl]   room {} --{}--> room {}".format(temp_id, direction, after_id))
            self.rooms[temp_id]["exits"][direction] = after_id
            if is_new:
                self.explore(after_id)
            self.registry.dispatch("move", {"direction": REVERSE[direction]})
            back_id, _ = self.visit_current_room()
            if back_id != temp_id:
                raise CrawlStuckError(
                    "room {}: moving {} then {} landed in room {}, not back in {} -- "
                    "a one-way exit or something moved us mid-crawl (a random encounter, "
                    "e.g.) -- stopping rather than recording a wrong map. Recover with "
                    "week3_capable/bin/reset and re-run; the crawl is idempotent.".format(
                        temp_id, direction, REVERSE[direction], back_id, temp_id
                    )
                )

    def run(self):
        start_id, _ = self.visit_current_room()
        self.explore(start_id)
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
    args = parser.parse_args()
    out_path = Path(args.out)

    registry = build_registry()
    crawler = Crawler(registry)
    try:
        rooms = crawler.run()
    finally:
        # Save whatever was discovered even if we got stuck partway through --
        # the crawl is idempotent, so partial progress isn't wasted.
        out_path.write_text(json.dumps(crawler.rooms, indent=2, sort_keys=True) + "\n")
        print("[crawl] wrote {} room(s) to {}".format(len(crawler.rooms), out_path))

    print("[crawl] done: {} room(s) discovered.".format(len(rooms)))


if __name__ == "__main__":
    main()
