"""Stage 7.0 (4): the nine concepts, taught at the point of action.

NSOT_STAGE7_PLAN.md section 4. "Teach at the point of action" is an
acceptance criterion, not a principle: each concept has a named screen, the
screen marks its explanation with ``data-concept="<name>"`` (an attribute,
because a text search would match the concept's name in prose), and a test
EXECUTES the shipped renderer in duktape against a REAL payload and asserts
the marked element is present, non-empty and not hidden.

Four concepts have their screen in 7.0. The other five have theirs in later
steps, and wait in PENDING, which only shrinks: a pending concept whose
marker appears in the shipped source must leave it (no ghosts).

The nine names are read from the plan's own table as well, and must match:
a harness and a document that disagree about what is taught is the same
defect as a document asserting what the code no longer does. It already
happened once: the plan's `approval-binds-a-set` described approval scheme
2, and since P.5 an approval binds the TEMPLATE, never a device set.
"""

import json
import os
import re
from typing import NamedTuple

import dukpy
import pytest

from tests import payload_providers as P
from tests.payload_render import lift, shipped

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, "docs", "NSOT_STAGE7_PLAN.md")
GEN = os.path.join(ROOT, "static", "js", "gen")


class Screen(NamedTuple):
    #: fn(monkeypatch, tmp_path) -> the HTML the shipped renderer produces
    #: from a real payload.
    render: object
    where: str


def _run(file, names, call):
    src = shipped(file)
    return dukpy.evaljs("\n".join(lift(src, n) for n in names) + "\n" + call)


def _deploy_program(mp, tmp):
    """7.1: the deploy screen is the preview-confirm component, and each
    concept is drawn in the part it explains (merge-only in what will NOT
    happen, confirm-by-hash in confirm)."""
    from tests.payload_render import render_preview

    return render_preview(P.deploy_plan(mp)["preview"])


def _pending_banner(mp, tmp):
    data = P.onboard_pending(mp, tmp)
    return _run("partials__onboard_pending.1.js", ("pendingAgeText", "pendingBannerHtml"),
                f"pendingBannerHtml({json.dumps(data)})")


def _approval_badge(mp, tmp):
    """An APPROVED template's badge, from the route's real payload, built by
    the fixture test_template_library_renders already uses (an unapproved
    template's badge has no approval to explain)."""
    from tests.test_template_library_renders import \
        TestTheBadgeSaysWhatItCoversAndWhatItDoesNot as T

    payload = T()._payload(tmp, mp)
    assert payload["approved"] is True, payload
    return _run("partials__template_editor.1.js",
                ("_tEsc", "approvalEvidenceText", "approvalCellHtml"),
                f"approvalCellHtml({json.dumps(payload)})")


LIVE = {
    "confirm-by-hash": Screen(_deploy_program, "the deploy preview's confirm part"),
    "merge-only": Screen(_deploy_program, "the deploy preview's what-will-not-happen part"),
    "pending-vs-promoted": Screen(_pending_banner, "the pending-onboarding banner"),
    "approval-binds-the-template": Screen(_approval_badge,
                                          "the template library's approval badge"),
}

#: Concepts whose screen is a later step, with that step. Only shrinks.
PENDING = {
    "intent-vs-device": "the device Overview, 7.3",
    "golden-is-a-record": "device History and Versions, 7.3 and 7.5",
    "revert-is-forward": "the revert-intent preview, a curl-only route today; "
                         "Device, History, 7.3",
    "baseline-is-earned": "Versions, Baselines, 7.5",
    "provenance-limits-remove": "the NetBox removal preview exists; its harness "
                                "entry needs a real removal-preview payload, "
                                "which lands with 7.1's retrofit of Import and "
                                "Remove into the preview-confirm component (C8)",
}
PENDING_CEILING = 5


def _element(html: str, name: str):
    """(opening tag, text) of the element marked `data-concept="name"`, or
    (None, "") when absent. Depth-counted, so a marked element holding
    nested divs yields all of its text."""
    m = re.search(r'<(\w+)\b[^>]*\bdata-concept="%s"[^>]*>' % re.escape(name), html)
    if not m:
        return None, ""
    tag, depth, i = m.group(1), 1, m.end()
    for t in re.finditer(r"<(/?)(%s)\b[^>]*>" % tag, html[m.end():]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            inner = html[m.end():m.end() + t.start()]
            return m.group(0), re.sub(r"<[^>]+>", " ", inner)
    return m.group(0), ""


def _plan_concepts() -> list:
    text = open(PLAN, encoding="utf-8").read()
    section = text[text.index("## 4. The nine concepts"):text.index("## 5.")]
    return re.findall(r"^\|\s*`([a-z-]+)`\s*\|", section, re.M)


class TestTheNine:
    def test_nine_concepts_live_or_pending(self):
        assert len(LIVE) + len(PENDING) == 9
        assert not set(LIVE) & set(PENDING)

    def test_the_plan_names_the_same_nine(self):
        """Both directions, with the floor the table's size gives."""
        names = _plan_concepts()
        assert len(names) == 9, names
        assert set(names) == set(LIVE) | set(PENDING)

    def test_pending_only_shrinks(self):
        assert len(PENDING) == PENDING_CEILING


class TestEachLiveScreenTeachesIt:
    @pytest.mark.parametrize("name", sorted(LIVE))
    def test_marked_non_empty_and_visible(self, name, monkeypatch, tmp_path):
        html = LIVE[name].render(monkeypatch, tmp_path)
        tag, text = _element(html, name)
        assert tag, f"{LIVE[name].where} does not mark {name!r}"
        assert len(" ".join(text.split())) >= 40, (name, text)
        for hidden in ("d-none", "display:none", "display: none", " hidden"):
            assert hidden not in tag, (name, tag)

    def test_the_words_are_the_concepts(self, monkeypatch, tmp_path):
        """Not only present: saying the thing. A marker on the wrong sentence
        would pass the test above."""
        program = _deploy_program(monkeypatch, tmp_path)
        assert "refused" in _element(program, "confirm-by-hash")[1]
        assert "never removed" in _element(program, "merge-only")[1]
        banner = _pending_banner(monkeypatch, tmp_path)
        assert "not in the inventory" in " ".join(
            _element(banner, "pending-vs-promoted")[1].split())
        badge = " ".join(_element(_approval_badge(monkeypatch, tmp_path),
                                  "approval-binds-the-template")[1].split())
        from modules.nsot import approval
        assert approval.COVERS[:30] in badge and approval.DOES_NOT_COVER[:30] in badge


def _marked_names() -> set:
    """Every concept a shipped screen can mark. Two places: a marker written
    in a renderer (`data-concept="x"`), and, since 7.1, an explanation the
    preview-confirm builder puts in a preview's `explain` (`"concept": "x"`),
    which the one renderer marks the same way."""
    text = "\n".join(open(os.path.join(GEN, f), encoding="utf-8").read()
                     for f in os.listdir(GEN))
    for root, _, files in os.walk(os.path.join(ROOT, "templates")):
        for f in files:
            text += open(os.path.join(root, f), encoding="utf-8").read()
    names = set(re.findall(r'data-concept="([a-z-]+)"', text))
    builder = open(os.path.join(ROOT, "modules", "preview_confirm.py"), encoding="utf-8").read()
    return names | set(re.findall(r'"concept":\s*"([a-z-]+)"', builder))


class TestPendingHasNoGhosts:
    def test_a_pending_concept_with_a_marker_must_leave(self):
        ghosts = sorted(set(PENDING) & _marked_names())
        assert ghosts == [], f"marked now: move to LIVE with a real-payload render: {ghosts}"

    def test_every_live_marker_is_in_the_shipped_source(self):
        """The floor for the check above: the scan can find a marker, in
        both places it looks."""
        marked = _marked_names()
        assert set(LIVE) <= marked, sorted(set(LIVE) - marked)
        assert {"merge-only", "confirm-by-hash"} <= marked
        assert "pending-vs-promoted" in marked
