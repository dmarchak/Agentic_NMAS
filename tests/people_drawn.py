"""Where a rendered v2 response draws a person's identity outside a collapsed record.

**Not a test module.** Board E2a (the operator, 2026-11-11): every person is drawn by their
display name, and the full verified identity stays only in a collapsed record. `addresses`
answers one question about one response body, and tests/v2_context.py's measurement asks it of
every response its walk receives (every v2 page, every fragment they ask for, and every
provider's requests), so tests/test_display_names_drawn.py reads the answer for the whole
interface from the one walk.

**A person's identity** here is an email-shaped word under a documentation domain
(`example.com`, `.example`, `.invalid`, `.test`): the only addresses a test may plant
(tests/test_nothing_personal_is_published.py refuses any other in the repository, a captured
device configuration's vendor text aside, pinned line by line), so every viewer and every
recorded actor the walk plants is one, and a captured configuration's own text is not.

**A collapsed record** is a ``<details>`` the server drew closed (no ``open``) carrying one of
`RECORD_CLASSES`: what is inside it, other than its own ``<summary>``, is the record, and is not
on the screen until a person opens it. Every other element is on the screen, a closed
``<details>`` of any other class included (a Needs attention row draws its people by display
name whether it is open or not), and so is every attribute's value (a hover, a form's value, a
link's address): the page carries it.

**An address that is a setting's value, not a person** (a notification's destination, which a
person must read whole to check it) is drawn by an element that says so, ``data-address="<what
it is>"``: that element's own attributes and everything inside it are not a person's identity.
"""

import re
from html.parser import HTMLParser

#: The ``<details>`` classes that are a record: a self-healing row's "Details for the record"
#: on History, "the identity as recorded" wherever a card keeps the full identity beside a
#: display name, and a folded part of an AI call's prompt or answer (exactly as it was sent).
RECORD_CLASSES = ("tl-record-d", "id-record", "hist-ai-part")
#: The attribute by which an element declares the address it draws is a setting's value.
DECLARED = "data-address"

_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                   "param", "source", "track", "wbr"})
#: An email-shaped word, as tests/test_nothing_personal_is_published.py reads one, and the
#: documentation domains (its `DOC_DOMAINS`).
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)")
DOC_DOMAINS = re.compile(r"(^|\.)(example\.(com|org|net)|example|invalid|test)$", re.I)


def identities(text: str) -> list:
    """``[(identity, the words around it)]``: each planted person's identity in *text*."""
    out = []
    for m in EMAIL.finditer(text):
        if DOC_DOMAINS.search(m.group(1)):
            around = " ".join(text[max(0, m.start() - 60):m.end() + 20].split())
            out.append((m.group(0), around))
    return out


class _Drawn(HTMLParser):
    """Every identity a body draws outside a collapsed record, with the element it is in."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.found, self.kept = [], [], []

    def _hidden(self) -> str:
        """"declared" inside an element that says its address is a setting's value, "record"
        inside a collapsed record (outside its summary), else ""."""
        for i, (_tag, kind) in enumerate(self.stack):
            if kind == "declared":
                return "declared"
            if kind == "record":
                after = self.stack[i + 1][1] if i + 1 < len(self.stack) else ""
                if after != "summary":
                    return "record"
        return ""

    def _where(self) -> str:
        return " > ".join(tag for tag, _k in self.stack[-3:]) or "the body"

    def handle_starttag(self, tag, attrs):
        attrs = [(k, v or "") for k, v in attrs]
        d = dict(attrs)
        kind = ""
        if DECLARED in d:
            kind = "declared"
        elif tag == "details" and "open" not in d and \
                set(d.get("class", "").split()) & set(RECORD_CLASSES):
            kind = "record"
        elif tag == "summary" and self.stack and self.stack[-1][1] == "record":
            kind = "summary"
        hidden = "declared" if kind == "declared" else self._hidden()
        if hidden != "declared":
            for name, value in attrs:
                for identity, around in identities(value):
                    (self.kept if hidden else self.found).append(
                        (identity, f"{self._where()} > {tag}[{name}]", around))
        if tag not in _VOID:
            self.stack.append((tag, kind))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        hidden = self._hidden() if "@" in data else "declared"
        if hidden != "declared":
            for identity, around in identities(data):
                (self.kept if hidden else self.found).append((identity, self._where(), around))


def scan(body: str) -> tuple:
    """``(drawn, kept)``, each ``[(identity, where, words)]``: every person's identity *body*
    draws outside a collapsed record, and every one it keeps inside one; each with the element
    (its last three ancestors, and the attribute when it is one) and the words around it."""
    if "@" not in body:
        return [], []
    parser = _Drawn()
    parser.feed(body)
    parser.close()
    return parser.found, parser.kept


def addresses(body: str) -> list:
    """`scan`'s first answer: the identities *body* draws outside a collapsed record."""
    return scan(body)[0]
