"""Converts ANSI SGR escape sequences (as produced by CircleMUD over telnet)
into spans of HTML/CSS classes so raw tool output renders with color.

Ports week1_baseline/log_viz/lib/log_viz/ansi.rb.
"""
import re

CODES = {
    "1": "ansi-bold",
    "4": "ansi-underline",
    "30": "ansi-fg-black", "31": "ansi-fg-red", "32": "ansi-fg-green", "33": "ansi-fg-yellow",
    "34": "ansi-fg-blue", "35": "ansi-fg-magenta", "36": "ansi-fg-cyan", "37": "ansi-fg-white",
    "40": "ansi-bg-black", "41": "ansi-bg-red", "42": "ansi-bg-green", "43": "ansi-bg-yellow",
    "44": "ansi-bg-blue", "45": "ansi-bg-magenta", "46": "ansi-bg-cyan", "47": "ansi-bg-white",
    "90": "ansi-fg-bright-black", "91": "ansi-fg-bright-red", "92": "ansi-fg-bright-green",
    "93": "ansi-fg-bright-yellow", "94": "ansi-fg-bright-blue", "95": "ansi-fg-bright-magenta",
    "96": "ansi-fg-bright-cyan", "97": "ansi-fg-bright-white",
}

ESCAPE_RE = re.compile(r"\x1b\[([0-9;]*)m")


def escape_html(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _apply_codes(classes, code_str):
    codes = code_str.split(";") if code_str else ["0"]
    for code in codes:
        if code in ("0", ""):
            classes.clear()
        elif code == "39":
            classes[:] = [c for c in classes if not c.startswith("ansi-fg-")]
        elif code == "49":
            classes[:] = [c for c in classes if not c.startswith("ansi-bg-")]
        else:
            css_class = CODES.get(code)
            if not css_class:
                continue
            if css_class.startswith("ansi-fg-"):
                classes[:] = [c for c in classes if not c.startswith("ansi-fg-")]
            if css_class.startswith("ansi-bg-"):
                classes[:] = [c for c in classes if not c.startswith("ansi-bg-")]
            if css_class not in classes:
                classes.append(css_class)


def to_html(text):
    """Render a raw string (possibly containing ANSI color codes and CRLF
    line endings) as escaped HTML with <span> elements for color/style."""
    text = str(text or "").replace("\r\n", "\n")
    classes = []
    html = []
    pos = 0
    for m in ESCAPE_RE.finditer(text):
        segment = text[pos:m.start()]
        if segment:
            escaped = escape_html(segment)
            html.append('<span class="{}">{}</span>'.format(" ".join(classes), escaped) if classes else escaped)
        _apply_codes(classes, m.group(1))
        pos = m.end()
    tail = text[pos:]
    if tail:
        escaped = escape_html(tail)
        html.append('<span class="{}">{}</span>'.format(" ".join(classes), escaped) if classes else escaped)
    return "".join(html)
