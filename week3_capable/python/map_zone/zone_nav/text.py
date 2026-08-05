"""Shared text-cleaning utilities for parsing tbaMUD responses.

Used by both the offline crawler (scripts/crawl_zone.py) and the live
`goto_room` tool (zone_nav/tool.py) -- the same stray-text problems that
corrupted the crawl's data can corrupt goto_room's runtime room
identification just as easily. Confirmed live: a login-triggered
realm-wide announcement landed as the first line of a `look` response
during an actual interactive session and made goto_room fail to recognize
the player's own current room ("current room ('A booming voice announces,
...') isn't recognized as part of the mapped zone"), even though the
crawler's own parsing had long since been hardened against exactly this.
Two independently-maintained copies of the same filtering logic can drift
out of sync that way; one shared module can't.
"""
import re

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
EXITS_LINE_RE = re.compile(r"^\[\s*exits:.*\]$", re.IGNORECASE)
# The vitals/prompt line tbaMUD ends every response with, e.g.
# "23H 100M 69V (news) (motd) > ". Confirmed live: this can end up as the
# *only* content of a read (the real room-description burst hadn't fully
# arrived yet), landing as the first line and getting misread as a room
# name -- the sentence-punctuation check below doesn't catch it, since it
# ends in ">", not "."/"!"/"?".
PROMPT_LINE_RE = re.compile(r"^\d+H\s+\d+M\s+\d+V\b.*>\s*$")
# Server text confirmed live to arrive asynchronously relative to whatever
# command is actually in flight, landing in the middle of an unrelated
# response and getting misread as room text: a login-triggered server-wide
# announcement, and the immortal teleport rescue's own confirmation to the
# target player. Filtered out at the single choke point every response
# passes through (clean_lines) rather than chased with settle delays.
BROADCAST_RE = re.compile(
    r"^(A booming voice announces,|Admin has teleported you!).*$", re.IGNORECASE | re.MULTILINE
)


def clean_lines(text):
    """ANSI-strip and broadcast-filter `text`, returning non-empty lines."""
    text = BROADCAST_RE.sub("", text)
    lines = [ANSI_RE.sub("", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


def has_exits_line(text):
    """True if `text` looks like room text (contains a "[ Exits: ... ]"
    line) rather than a failed-move message. Confirmed live: a blocked
    move (e.g. no exit that direction) returns a short message with no
    room text at all -- "Alas, you cannot go that way...\\r\\n\\r\\n23H
    100M 2V (news) (motd) > " -- so presence/absence of the exits line is
    a reliable, content-based way to tell "moved" from "didn't move"
    without hardcoding that one specific failure string.
    """
    return any(EXITS_LINE_RE.match(ln) for ln in clean_lines(text))


def is_noise_line(line):
    """True if `line` looks like a stray notification or a lone
    vitals/prompt line rather than a room name. Confirmed live, several
    *different* kinds of dynamic text can land as the first line of an
    otherwise-unrelated response (a realm-wide announcement, a teleport
    confirmation, a mob arrival/departure message, a zone-level warning,
    or just the trailing prompt with nothing else -- BROADCAST_RE only
    covers the first two, confirmed exact strings; chasing every possible
    message text one at a time doesn't scale). The general, well-evidenced
    signal used here instead: every real room name seen in this MUD
    (dozens, by now) is a short title with no trailing punctuation ("The
    Temple Of Midgaard", "Main Street"); every corrupted case observed was
    either a full sentence ending in `.`/`!`/`?` ("The green gelatinous
    blob has arrived.") or the vitals/prompt line itself.
    """
    return line.endswith((".", "!", "?")) or bool(PROMPT_LINE_RE.match(line))


def first_room_name_line(text):
    """Returns the first line of `text` that could plausibly be a room
    name, skipping any leading noise line (see is_noise_line). Returns
    None if nothing is left after filtering.
    """
    lines = clean_lines(text)
    while lines and is_noise_line(lines[0]):
        lines = lines[1:]
    return lines[0] if lines else None
