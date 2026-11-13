"""Where a rendered v2 response shows a person a time in UTC rather than in their own zone.

**Not a test module.** One time zone per screen (docs/UI_RULES.md; the operator, 2026-11-13,
C3290: "every time a person sees, in the page or in record details, goes through the viewer's
zone"). `scan` answers one question about one response body, and tests/v2_context.py's
measurement asks it of every HTML response its walk receives (every v2 page, every fragment
they ask for, and every provider's requests), so tests/test_no_utc_drawn.py reads the answer
for the whole interface from the one walk, as tests/people_drawn.py's identities are read.

**What a person sees** is every text node outside ``<script>``, ``<style>`` and every
attribute: a hover (``title``) is where a time's UTC instant belongs (`_macros.clock` puts it
there), and an attribute that is no hover is a machine's (``datetime``, ``data-*``, a form's
value). A record drawn closed is still read: a person opens it, and its words are the page's.

**A UTC time** is a recorded instant as a machine writes it (``2026-11-12T02:33:45Z``, with an
offset or none, or a log line's ``2026-11-12 02:33:45``, which the records keep in UTC), or a clock
time with "UTC" or "GMT" beside it (``14:02 UTC``, ``02:33:45 (UTC)``, ``UTC 14:02``). The walk
draws every time in a viewer zone that is not UTC (`WALK_ZONE`), so the clock's own words never
say UTC: one that does is a time some code worded itself.

**What is not Mercury's words, and is left:** an element that declares it quotes a source's
own text verbatim, ``data-verbatim="<whose text>"`` (a device's configuration, which says its
own clock's zone in its "Last configuration change at … UTC" line; a log line as the device
sent it): everything inside it is the source's, as a person must read it to check it.
"""

import re
from html.parser import HTMLParser

#: The zone the walk's viewer reads every screen in: not UTC, and neither the laptop's nor CI's
#: host zone, so a time in the viewer's zone never reads as UTC, and one in the host's zone
#: is not taken for the viewer's.
WALK_ZONE = "Asia/Kolkata"
#: The attribute by which an element declares it quotes a source's own text verbatim.
DECLARED = "data-verbatim"

#: A recorded instant as a machine writes it: an ISO time (``2026-11-12T02:33:45Z``, with an
#: offset or none) or a log line's ``2026-11-12 02:33:45``, which the records keep in UTC. The
#: clock never writes a time this way: its words are "Nov 12 08:03" in the viewer's zone.
ISO_Z = re.compile(r"\b\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?"
                   r"(?:Z|[+-]\d\d:?\d\d)?(?:\s*\(?(?:UTC|GMT)\b\)?)?(?![\w:])")
#: A clock time with "UTC" or "GMT" beside it (an offset zone, "UTC+05:45", is the clock's).
UTC_TIME = re.compile(
    r"\b\d{1,2}:\d\d(?::\d\d(?:\.\d+)?)?\s*\(?(?:UTC|GMT)\b(?![+-]\d)"
    r"|\b(?:UTC|GMT)\)?\s+\d{1,2}:\d\d\b")

_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                   "param", "source", "track", "wbr"})
#: Elements a person does not read as the page's words: a script, a style, and an SVG
#: element's ``<title>``, which is its hover.
_UNSEEN = frozenset({"script", "style"})


def utc_times(text: str) -> list:
    """``[(the UTC time, the words around it)]`` in *text*, each place once."""
    out, taken = [], []
    for rx in (ISO_Z, UTC_TIME):
        for m in rx.finditer(text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append(m.span())
            around = " ".join(text[max(0, m.start() - 50):m.end() + 20].split())
            out.append((m.group(0), around))
    return out


class _Seen(HTMLParser):
    """Every UTC time a body shows a person, with the element it is in."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.found = [], []
        # The words of a time element just closed: a "UTC" written after the clock's own words
        # ("08:03 IST UTC") is a time's suffix some code left there.
        self.after_time, self.words = "", ""

    def _left(self) -> bool:
        return any(kind for _tag, kind in self.stack)

    def _where(self) -> str:
        return " > ".join(tag for tag, _k in self.stack[-3:]) or "the body"

    def handle_starttag(self, tag, attrs):
        self.after_time = ""
        d = {k: v or "" for k, v in attrs}
        hover = tag == "title" and any(t == "svg" for t, _k in self.stack)
        kind = "unseen" if tag in _UNSEEN or hover else ("verbatim" if DECLARED in d else "")
        if tag not in _VOID:
            self.stack.append((tag, kind))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        self.after_time = ""
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                if tag == "time" and not self._left():
                    self.after_time = self.words
                return

    def handle_data(self, data):
        after, self.after_time = self.after_time, ""
        self.words = data
        if self._left():
            return
        suffix = re.match(r"\s*\(?(?:UTC|GMT)\b(?![+-]\d)", data) if after else None
        if suffix:
            self.found.append((f"{after.strip()}{suffix.group(0)}", self._where(),
                               " ".join((after + data[:40]).split())))
        if not re.search(r"\d:\d", data):
            return
        for time, around in utc_times(data):
            self.found.append((time, self._where(), around))


def scan(body: str) -> list:
    """``[(time, where, words)]``: every UTC time *body* shows a person, each with its element
    (its last three ancestors) and the words around it."""
    if not re.search(r"\d:\d", body):
        return []
    parser = _Seen()
    parser.feed(body)
    parser.close()
    return parser.found
