"""Unit tests for zone_nav/graph.py -- pure data structure tests against
the real committed data/zone_30.json. No MUD, no network, no fake double
needed: the data itself is static and already trustworthy once generated
(see scripts/crawl_zone.py + scripts/cross_reference.py).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zone_nav import graph as zone_graph  # noqa: E402
from zone_nav.tool import _current_room_name  # noqa: E402


class TestFindByName(unittest.TestCase):
    def setUp(self):
        self.graph = zone_graph.load_zone()

    def test_bakery_is_unique(self):
        matches = zone_graph.find_by_name(self.graph, "Bakery")
        self.assertEqual(len(matches), 1)
        self.assertIn("bakery", self.graph[matches[0]].name.lower())

    def test_exact_match_preferred_over_substring(self):
        # "Main Street" is a real duplicate name in zone 30 (several
        # segments) -- exact match should return every one of them, not
        # just the first substring hit.
        exact = zone_graph.find_by_name(self.graph, "Main Street")
        self.assertGreaterEqual(len(exact), 1)
        for room_id in exact:
            self.assertEqual(self.graph[room_id].name.lower(), "main street")

    def test_no_match_returns_empty(self):
        self.assertEqual(zone_graph.find_by_name(self.graph, "Nonexistent Room Xyz"), [])


class TestShortestPaths(unittest.TestCase):
    def setUp(self):
        self.graph = zone_graph.load_zone()

    def test_self_path_is_empty(self):
        start = next(iter(self.graph))
        distances, prev_direction, prev_id = zone_graph.shortest_paths_from(self.graph, start)
        self.assertEqual(zone_graph.reconstruct_path(prev_direction, prev_id, start, start), [])

    def test_paths_are_self_consistent(self):
        """The returned directions, replayed by hand against the graph's
        own exits starting at the source, must land exactly on the
        target -- stronger than hardcoding expected paths for specific
        room pairs, and doesn't need updating if the map is regenerated.
        """
        start = next(iter(self.graph))
        distances, prev_direction, prev_id = zone_graph.shortest_paths_from(self.graph, start)
        checked = 0
        for target in distances:
            directions = zone_graph.reconstruct_path(prev_direction, prev_id, start, target)
            self.assertIsNotNone(directions)
            node = start
            for direction in directions:
                node = self.graph[node].exits[direction]
            self.assertEqual(node, target)
            checked += 1
        self.assertGreater(checked, 1)  # sanity: the graph actually has more than one room

    def test_unreachable_target_returns_none(self):
        start = next(iter(self.graph))
        _, prev_direction, prev_id = zone_graph.shortest_paths_from(self.graph, start)
        fake_unreachable_id = max(self.graph) + 1000
        self.assertIsNone(zone_graph.reconstruct_path(prev_direction, prev_id, start, fake_unreachable_id))


class TestCurrentRoomName(unittest.TestCase):
    def test_strips_ansi(self):
        text = "\x1b[0;33mThe Bakery\x1b[0m\r\n   You are standing inside...\r\n[ Exits: s ]\r\n\r\n23H 100M 3V > "
        self.assertEqual(_current_room_name(text), "The Bakery")

    def test_empty_text_returns_none(self):
        self.assertIsNone(_current_room_name(""))


if __name__ == "__main__":
    unittest.main()
