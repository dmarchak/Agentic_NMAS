"""An unmodelled block's children are children by structure (C2700, the operator, 2026-11-07).

r4's and s1's intent held ``unmodeled: [{line: archive, children: ["path bootflash:…"]}]``, the
child typed with no leading space. The shipped template emits children verbatim, so the
program sent was flat (``archive``, then a global ``path …``); IOS took ``path`` in archive mode
and printed it nested, and verify's read-back, keyed on (section, line), missed both lines.

The one shape (`hostvars.unmodelled_children`): each child carries one space per depth, the
shape the device prints and the parser writes; a child typed with no space, or with too many,
is given its depth by structure (at least 1, at most one deeper than the child before it). The
serialiser writes it, the renderer renders it (before the template, so a network's own copy of
`_common.j2` renders it too), the acknowledgements and the formatting check read it. A
document already holding indented children reads as it did, so nothing indents twice: the
expand half of expand-then-contract, with no store migration.

The real captures are tests/fixtures/configs/fleet/r4.cfg and s1.cfg with the two-line
``archive`` block each device's later capture holds (read masked from the committed goldens,
2026-11-07), spliced in where those captures hold it: the only edit.
"""

import os

import pytest

from modules.nsot import deploy, hostvars, roundtrip, verify_scope
from modules.nsot.parsers import get_parser
from modules.nsot.render_artifact import unmodeled_lines

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")

#: Each device's archive block as its committed golden holds it (read through
#: scripts/nmas-config-read, masked, 2026-11-07), and the line of the earlier capture it follows.
ARCHIVE = {
    "r4": {"platform": "cisco_iosxe", "path": "bootflash:mercury-arch",
           "after": "diagnostic bootup level minimal\n"},
    "s1": {"platform": "cisco_ios", "path": "flash0:mercury-arch",
           "after": "ipv6 cef\n!\n"},
}


def _capture(device: str) -> str:
    """The fleet fixture with the archive block spliced in where the later capture holds it."""
    with open(os.path.join(FLEET, f"{device}.cfg"), encoding="utf-8") as fh:
        text = fh.read()
    a = ARCHIVE[device]
    assert text.count(a["after"]) == 1, f"{device}: the splice point is not unique"
    block = f"archive\n path {a['path']}\n" + ("!\n" if device == "s1" else "")
    return text.replace(a["after"], a["after"] + block)


def _stored(device: str, flat: bool = False) -> dict:
    """The device's committed unmodelled block as the host holds it now (the leading space
    the operator typed, 2026-11-07), or as it was typed before (no space)."""
    child = f"path {ARCHIVE[device]['path']}"
    return {"line": "archive", "children": [child if flat else " " + child]}


def _intent(device: str, block: dict) -> dict:
    """The real capture's extraction with the archive block as *block*."""
    hv = get_parser(ARCHIVE[device]["platform"]).parse(_capture(device))
    assert [e["line"] for e in hv["unmodeled"]] == ["archive"], hv["unmodeled"]
    hv["unmodeled"] = [block]
    return hv


def _render(hv: dict) -> str:
    return roundtrip.render(hv, hv["platform"])


def _archive_stanza(text: str) -> list:
    lines = text.splitlines()
    i = lines.index("archive")
    out = [lines[i]]
    for line in lines[i + 1:]:
        if not line.startswith(" "):
            break
        out.append(line)
    return out


class TestTheOneShape:
    """`unmodelled_children`, the one reading of a child's depth."""

    def test_a_child_typed_flat_is_given_its_depth(self):
        assert hostvars.unmodelled_children(["path bootflash:a"]) == [" path bootflash:a"]

    def test_a_child_stored_indented_is_unchanged(self):
        assert hostvars.unmodelled_children([" path bootflash:a"]) == [" path bootflash:a"]

    def test_a_parsers_capture_of_a_deeper_block_is_unchanged(self):
        captured = [" key 1", "  key-string 7 <value>", " key 2", "  key-string 7 <value>"]
        assert hostvars.unmodelled_children(captured) == captured

    def test_too_much_typed_whitespace_is_bounded_by_structure(self):
        typed = ["    key 1", "      key-string x", "\tkey 2"]
        assert hostvars.unmodelled_children(typed) == [" key 1", "  key-string x", " key 2"]

    def test_it_is_its_own_fixed_point(self):
        for children in (["a", "b"], [" a", "  b", "   c", " d"], ["  a", "b", "    c"]):
            once = hostvars.unmodelled_children(children)
            assert hostvars.unmodelled_children(once) == once, children

    def test_a_blank_child_is_kept_as_it_stands(self):
        assert hostvars.unmodelled_children(["a", "", "b"]) == [" a", "", " b"]

    def test_the_serialiser_writes_it_and_a_flat_document_is_the_same_document(self):
        flat = {"hostname": "x", "unmodeled": [{"line": "archive", "children": ["path a"]}]}
        nested = {"hostname": "x", "unmodeled": [{"line": "archive", "children": [" path a"]}]}
        assert hostvars.to_yaml(flat) == hostvars.to_yaml(nested)
        assert "- ' path a'" in hostvars.to_yaml(flat)
        assert hostvars.same_document(flat, nested)
        assert not hostvars.round_trips("hostname: x\nsecret_refs: []\nunmodeled:\n"
                                        "- children:\n  - path a\n  line: archive\n"), \
            "a document holding a flat child is not in Mercury's own formatting"
        assert hostvars.round_trips(hostvars.to_yaml(nested))

    def test_an_acknowledgement_names_the_line_as_it_is_sent(self):
        flat = {"unmodeled": [{"line": "archive", "children": ["path a"]}]}
        assert unmodeled_lines(flat) == [" path a", "archive"]


@pytest.mark.parametrize("device", sorted(ARCHIVE))
class TestR4AndS1:
    """The operator's case: r4's and s1's committed blocks (each child stored with the leading
    space, 2026-11-07) render the same bytes as before this change, and the same block typed
    flat renders the same as the indented one."""

    def test_the_stored_block_renders_the_same_bytes_as_before(self, device, monkeypatch):
        hv = _intent(device, _stored(device))
        after = _render(hv)
        # Before: the renderer handed the template each child as stored.
        monkeypatch.setattr(hostvars, "normalise_unmodelled", lambda entries: list(entries))
        before = _render(hv)
        assert after == before
        assert _archive_stanza(after) == ["archive", f" path {ARCHIVE[device]['path']}"]

    def test_a_flat_typed_copy_renders_the_same_as_the_indented_one(self, device):
        nested = _render(_intent(device, _stored(device)))
        flat = _render(_intent(device, _stored(device, flat=True)))
        assert flat == nested
        assert _archive_stanza(flat) == ["archive", f" path {ARCHIVE[device]['path']}"], \
            "rendered once, never twice"

    def test_against_the_capture_there_is_nothing_to_send(self, device):
        capture = _capture(device)
        for flat in (False, True):
            rendered = _render(_intent(device, _stored(device, flat=flat)))
            program = deploy.merge_commands(rendered, capture)
            assert not [l for l in program if "archive" in l or "mercury-arch" in l], program


@pytest.mark.parametrize("device", sorted(ARCHIVE))
class TestTheRoundTrip:
    """A real capture holding an `archive` block: parsed, stored, rendered and read back, with
    no departure; and typed flat, its program is nested and verify reads it back."""

    def test_parse_store_render_compare(self, device):
        capture = _capture(device)
        hv = get_parser(ARCHIVE[device]["platform"]).parse(capture)
        assert hv["unmodeled"][0]["children"] == [f" path {ARCHIVE[device]['path']}"]
        stored = hostvars.from_yaml(hostvars.to_yaml(hv))
        stored["secrets"] = hv["secrets"]
        rendered = _render(stored)
        report = roundtrip.compare(capture, rendered, stored)
        moved = [str(x) for k in ("missing", "extra", "reordered")
                 for x in report["details"][k]]
        assert not [m for m in moved if "archive" in m or "mercury-arch" in m], moved

    def test_a_flat_intent_sends_a_nested_program_that_verify_reads_back(self, device):
        a = ARCHIVE[device]
        without = _capture(device).replace(f"archive\n path {a['path']}\n", "")
        rendered = _render(_intent(device, _stored(device, flat=True)))
        program = deploy.merge_commands(rendered, without)
        assert program[program.index("archive") + 1] == f" path {a['path']}", program
        # The device then prints it nested, as its capture does: every line is read back.
        assert verify_scope.read_back(program, _capture(device))["missing"] == []

    def test_the_flat_program_this_replaces_is_what_verify_could_not_find(self, device):
        """The control: the program the old renderer sent, read back against the same
        capture, misses its line, so the check above is able to fail."""
        a = ARCHIVE[device]
        flat = ["archive", f"path {a['path']}"]
        assert verify_scope.read_back(flat, _capture(device))["missing"], \
            "a flat `path` is read back as a global line and not found"


class TestTheProgramIsDrawnNested:
    """The deploy preview draws THE PROGRAM with a guide per level (C2700), the lines' bytes
    unchanged: what is drawn and copied is what is hashed and sent."""

    def _drawn(self, lines):
        import app as nmas

        with nmas.app.test_request_context("/v2/"):
            macros = nmas.app.jinja_env.get_template("v2/_macros.html").module
            return str(macros.program_lines(lines))

    def test_a_nested_line_carries_its_guide_and_its_own_bytes(self):
        import html
        import re

        lines = ["archive", " path bootflash:mercury-arch", "key chain K", " key 1",
                 "  key-string 7 <value>"]
        drawn = self._drawn(lines)
        assert '<span class="op-add">archive</span>' in drawn
        assert ('<span class="op-nest" data-depth="1" aria-hidden="true"'
                in drawn.split('<span class="op-add"> path bootflash:mercury-arch</span>')[0])
        assert 'data-depth="2"' in drawn
        text = html.unescape(re.sub(r"<[^>]+>", "", drawn))
        assert text == "\n".join(lines) + "\n", "the guide is generated content, never text"
        assert re.findall(r'<span class="op-add">(.*?)</span>', drawn) == \
            [html.escape(l) for l in lines]

    def test_a_flat_program_draws_no_guide(self):
        assert "op-nest" not in self._drawn(["archive", "path bootflash:mercury-arch"])

    def test_the_deploy_card_draws_its_program_through_it(self):
        with open(os.path.join(ROOT, "templates", "v2", "_deploy.html"), encoding="utf-8") as fh:
            text = fh.read()
        assert "{{ program_lines(c.sent) }}" in text
        assert '{% for l in c.sent %}<span class="op-add">' not in text

    def test_the_guide_is_drawn_by_the_stylesheet(self):
        with open(os.path.join(ROOT, "static", "css", "nmas-v2.css"), encoding="utf-8") as fh:
            css = fh.read()
        for depth in (1, 2, 3, 4):
            assert f'.op-diff .op-nest[data-depth="{depth}"]::before' in css, depth
