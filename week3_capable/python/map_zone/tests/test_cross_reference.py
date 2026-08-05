"""Unit tests for scripts/cross_reference.py's constraint-propagation
matching -- pure data structure logic, no MUD, no live parser subprocess.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from cross_reference import cross_reference  # noqa: E402


class TestCrossReference(unittest.TestCase):
    def test_unique_names_resolve_immediately(self):
        crawled = {
            1: {"name": "The Temple Of Midgaard", "desc": "d1", "exits": {"north": 2}},
            2: {"name": "The Bakery", "desc": "d2", "exits": {"south": 1}},
        }
        docs = {
            3001: {"name": "The Temple Of Midgaard", "exits": {"north": 3009}},
            3009: {"name": "The Bakery", "exits": {"south": 3001}},
        }
        resolved, unresolved = cross_reference(crawled, docs)
        self.assertEqual(resolved, {1: 3001, 2: 3009})
        self.assertEqual(unresolved, [])

    def test_duplicate_name_resolved_via_resolved_neighbor(self):
        # Two candidate vnums share the name "Main Street"; only one of
        # them has an exit back into the already-resolved Temple (3001).
        # This is the exact scenario zone 30 has for real (several
        # "Main Street" segments) -- name matching alone can't tell them
        # apart, but the already-known neighbor can.
        crawled = {
            1: {"name": "The Temple Of Midgaard", "desc": "d1", "exits": {"east": 2}},
            2: {"name": "Main Street", "desc": "d2", "exits": {"west": 1}},
        }
        docs = {
            3001: {"name": "The Temple Of Midgaard", "exits": {"east": 3012}},
            3012: {"name": "Main Street", "exits": {"west": 3001}},
            3013: {"name": "Main Street", "exits": {"west": 3099}},  # a different, unrelated Main Street
        }
        resolved, unresolved = cross_reference(crawled, docs)
        self.assertEqual(resolved[1], 3001)
        self.assertEqual(resolved[2], 3012)  # not 3013 -- 3013's west exit doesn't match
        self.assertEqual(unresolved, [])

    def test_genuinely_unresolvable_room_is_reported_not_guessed(self):
        # "Main Street" has two candidates and no resolved neighbor to
        # disambiguate with (its only neighbor, room 1, also shares a
        # duplicate name and never resolves either) -- must stay
        # unresolved, not silently guessed.
        crawled = {
            1: {"name": "Main Street", "desc": "d1", "exits": {"east": 2}},
            2: {"name": "Main Street", "desc": "d2", "exits": {"west": 1}},
        }
        docs = {
            3012: {"name": "Main Street", "exits": {"east": 3013}},
            3013: {"name": "Main Street", "exits": {"west": 3012}},
            3099: {"name": "Main Street", "exits": {}},
        }
        resolved, unresolved = cross_reference(crawled, docs)
        self.assertEqual(resolved, {})
        self.assertEqual(sorted(unresolved), [1, 2])

    def test_room_name_not_in_docs_at_all_is_unresolved(self):
        crawled = {1: {"name": "A Room The Parser Never Saw", "desc": "d", "exits": {}}}
        docs = {3001: {"name": "The Temple Of Midgaard", "exits": {}}}
        resolved, unresolved = cross_reference(crawled, docs)
        self.assertEqual(resolved, {})
        self.assertEqual(unresolved, [1])


if __name__ == "__main__":
    unittest.main()
