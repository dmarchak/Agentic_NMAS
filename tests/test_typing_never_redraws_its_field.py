"""A field being typed in is never replaced by its own redraw (C573; the operator's walk,
2026-10-08: typing in Show commands' name filter lost the field, because the filter redrew the
whole card, its own input included; a paste, one request, seemed to work).

The shape, constrained rather than each member enumerated: in every v2 template, a text field
whose `hx-trigger` fires as it is typed in (`input`, `keyup`, `keydown`) must not target an
element that ENCLOSES it (or itself, swapped whole): its answer goes beside it. Parsed with the
template's element nesting, ids included; a planted case is found.
"""

import glob
import os
import re
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPING = re.compile(r"\b(input|keyup|keydown)\b")
VOID = {"input", "br", "img", "hr", "meta", "link", "source", "col", "wbr"}


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.found, self.fields = [], [], 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("input", "textarea") and a.get("type", "text") not in (
                "hidden", "checkbox", "radio", "submit", "button") \
                and TYPING.search(a.get("hx-trigger") or ""):
            self.fields += 1
            target = (a.get("hx-target") or "").strip()
            swap = (a.get("hx-swap") or "innerHTML").split()[0]
            enclosing = [i for _t, i in self.stack if i]
            if target.startswith("#") and target[1:] in enclosing:
                self.found.append(f"{a.get('name') or a.get('id')}: targets #{target[1:]}, "
                                  "which encloses it")
            elif target in ("", "this") and swap == "outerHTML":
                self.found.append(f"{a.get('name') or a.get('id')}: replaces itself")
        if tag not in VOID:
            self.stack.append((tag, a.get("id", "")))

    def handle_endtag(self, tag):
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k][0] == tag:
                del self.stack[k:]
                break


def scan(text: str):
    s = _Scan()
    s.feed(text)
    return s.found, s.fields


def test_no_v2_field_is_redrawn_by_its_own_typing():
    problems, fields = [], 0
    for path in sorted(glob.glob(os.path.join(ROOT, "templates", "v2", "**", "*.html"),
                                 recursive=True)):
        found, n = scan(open(path, encoding="utf-8").read())
        fields += n
        problems += [f"{os.path.relpath(path, ROOT)}: {f}" for f in found]
    assert fields >= 4, fields                      # a floor: the typed fields exist
    assert not problems, "\n".join(problems)


def test_the_scan_finds_the_walk_s_shape():
    """The control: the name filter as it was, targeting the card that holds it."""
    planted = ('<section id="sc-pick"><form><input type="search" name="q" '
               'hx-get="/x" hx-trigger="input changed delay:400ms" hx-target="#sc-pick" '
               'hx-swap="outerHTML"></form></section>')
    found, n = scan(planted)
    assert n == 1 and found == ["q: targets #sc-pick, which encloses it"]
    beside = planted.replace('hx-target="#sc-pick"', 'hx-target="#sc-devices"')
    assert scan(beside + '<div id="sc-devices"></div>')[0] == []
